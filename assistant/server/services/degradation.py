"""Graceful degradation service for handling API failures and degraded modes.

This service provides:
- API fallback: Automatically switch between Claude and OpenAI on failures
- Network detection: Check online/offline status
- Rate limit handling: Queue requests when rate limited
- Cached tool results: Store web_fetch results for offline access
- Status tracking: Monitor and report degraded mode status
"""
import asyncio
import logging
import time
import socket
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Optional, Dict, List, Callable, Any
from collections import deque

logger = logging.getLogger(__name__)


class DegradationMode(Enum):
    """Current degradation mode of the system."""
    NORMAL = auto()           # All services working normally
    CLAUDE_UNAVAILABLE = auto()   # Claude API down, using OpenAI fallback
    OPENAI_UNAVAILABLE = auto()   # OpenAI API down, using Claude fallback
    CLOUD_UNAVAILABLE = auto()    # Both cloud APIs down, using Ollama fallback
    RATE_LIMITED = auto()     # Currently rate limited, queuing requests
    OFFLINE = auto()          # Network unavailable, using cached responses
    LOCAL_ONLY = auto()       # User requested local-only mode (Ollama only)
    DEGRADED = auto()         # Some services impaired but functional


@dataclass
class APIHealth:
    """Health status of an API endpoint."""
    name: str
    available: bool = True
    last_success: Optional[datetime] = None
    last_failure: Optional[datetime] = None
    consecutive_failures: int = 0
    rate_limited_until: Optional[datetime] = None
    total_requests: int = 0
    total_failures: int = 0

    @property
    def failure_rate(self) -> float:
        """Calculate failure rate as percentage."""
        if self.total_requests == 0:
            return 0.0
        return (self.total_failures / self.total_requests) * 100

    @property
    def is_rate_limited(self) -> bool:
        """Check if currently rate limited."""
        if self.rate_limited_until is None:
            return False
        return datetime.now() < self.rate_limited_until

    def record_success(self):
        """Record a successful API call."""
        self.total_requests += 1
        self.last_success = datetime.now()
        self.consecutive_failures = 0
        self.available = True

    def record_failure(self, is_rate_limit: bool = False, retry_after: Optional[int] = None):
        """Record a failed API call."""
        self.total_requests += 1
        self.total_failures += 1
        self.last_failure = datetime.now()
        self.consecutive_failures += 1

        # Mark unavailable after 3 consecutive failures
        if self.consecutive_failures >= 3:
            self.available = False
            logger.warning(f"API {self.name} marked unavailable after {self.consecutive_failures} failures")

        # Handle rate limiting
        if is_rate_limit:
            # Default to 60 seconds if retry_after not provided
            wait_seconds = retry_after or 60
            self.rate_limited_until = datetime.now() + timedelta(seconds=wait_seconds)
            logger.warning(f"API {self.name} rate limited until {self.rate_limited_until}")

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "name": self.name,
            "available": self.available,
            "is_rate_limited": self.is_rate_limited,
            "consecutive_failures": self.consecutive_failures,
            "failure_rate_percent": round(self.failure_rate, 2),
            "last_success": self.last_success.isoformat() if self.last_success else None,
            "last_failure": self.last_failure.isoformat() if self.last_failure else None,
            "rate_limited_until": self.rate_limited_until.isoformat() if self.rate_limited_until else None,
        }


@dataclass
class QueuedRequest:
    """A request waiting to be processed."""
    id: str
    created_at: datetime
    callback: Callable
    args: tuple
    kwargs: dict
    priority: int = 0  # Higher = more important


class DegradationService:
    """Service for managing graceful degradation and API fallback."""

    # Circuit breaker settings
    FAILURE_THRESHOLD = 3  # Failures before marking API unavailable
    RECOVERY_TIME = 60  # Seconds before trying failed API again

    # Rate limit queue settings
    MAX_QUEUE_SIZE = 100
    QUEUE_TIMEOUT = 300  # 5 minutes max wait

    def __init__(self):
        self._api_health: Dict[str, APIHealth] = {
            "claude": APIHealth(name="claude"),
            "openai": APIHealth(name="openai"),
            "ollama": APIHealth(name="ollama"),
        }
        self._local_only_mode: bool = False
        self._request_queue: deque[QueuedRequest] = deque(maxlen=self.MAX_QUEUE_SIZE)
        self._last_network_check: Optional[datetime] = None
        self._network_available: bool = True
        self._mode: DegradationMode = DegradationMode.NORMAL
        self._mode_changed_at: datetime = datetime.now()
        self._lock = asyncio.Lock()
        self._queue_processor_running: bool = False

        # Cache for tool results (especially web_fetch)
        self._tool_cache: Dict[str, dict] = {}
        self._cache_max_age = timedelta(hours=24)

    @property
    def mode(self) -> DegradationMode:
        """Current degradation mode."""
        return self._mode

    @property
    def is_degraded(self) -> bool:
        """Check if system is in any degraded state."""
        return self._mode != DegradationMode.NORMAL

    def _update_mode(self):
        """Update the current degradation mode based on API health."""
        old_mode = self._mode

        claude_health = self._api_health["claude"]
        openai_health = self._api_health["openai"]
        ollama_health = self._api_health["ollama"]

        if self._local_only_mode:
            self._mode = DegradationMode.LOCAL_ONLY
        elif not self._network_available:
            # Network down - check if Ollama is available locally
            if ollama_health.available:
                self._mode = DegradationMode.OFFLINE  # Can use Ollama offline
            else:
                self._mode = DegradationMode.OFFLINE
        elif claude_health.is_rate_limited or openai_health.is_rate_limited:
            self._mode = DegradationMode.RATE_LIMITED
        elif not claude_health.available and not openai_health.available:
            # Both cloud APIs down - use Ollama if available
            if ollama_health.available:
                self._mode = DegradationMode.CLOUD_UNAVAILABLE
            else:
                self._mode = DegradationMode.OFFLINE
        elif not claude_health.available:
            self._mode = DegradationMode.CLAUDE_UNAVAILABLE
        elif not openai_health.available:
            self._mode = DegradationMode.OPENAI_UNAVAILABLE
        elif claude_health.consecutive_failures > 0 or openai_health.consecutive_failures > 0:
            self._mode = DegradationMode.DEGRADED
        else:
            self._mode = DegradationMode.NORMAL

        if old_mode != self._mode:
            self._mode_changed_at = datetime.now()
            logger.info(f"Degradation mode changed: {old_mode.name} -> {self._mode.name}")

    def get_api_health(self, api_name: str) -> APIHealth:
        """Get health status for a specific API."""
        return self._api_health.get(api_name, APIHealth(name=api_name))

    def record_success(self, api_name: str):
        """Record a successful API call."""
        if api_name in self._api_health:
            self._api_health[api_name].record_success()
            self._update_mode()

    def record_failure(self, api_name: str, is_rate_limit: bool = False, retry_after: Optional[int] = None):
        """Record a failed API call."""
        if api_name in self._api_health:
            self._api_health[api_name].record_failure(is_rate_limit, retry_after)
            self._update_mode()

    def should_use_fallback(self, primary_api: str) -> bool:
        """Check if we should use fallback API instead of primary."""
        primary_health = self._api_health.get(primary_api)
        if not primary_health:
            return False

        # Use fallback if primary is unavailable or rate limited
        return not primary_health.available or primary_health.is_rate_limited

    def get_preferred_api(self, preferred: str = "claude") -> str:
        """Get the best available API to use.

        Fallback order: preferred -> other cloud API -> ollama
        In local_only_mode, always returns "ollama".
        """
        # If local-only mode is enabled, always use Ollama
        if self._local_only_mode:
            return "ollama"

        if not self.should_use_fallback(preferred):
            return preferred

        # Try cloud fallback
        fallback = "openai" if preferred == "claude" else "claude"
        if not self.should_use_fallback(fallback):
            return fallback

        # Both cloud APIs unavailable - try Ollama
        ollama_health = self._api_health["ollama"]
        if ollama_health.available and not ollama_health.is_rate_limited:
            logger.info("Cloud APIs unavailable, falling back to Ollama")
            return "ollama"

        # Try recovery for cloud APIs
        primary_health = self._api_health[preferred]
        fallback_health = self._api_health[fallback]

        # Check if either might have recovered
        recovery_time = timedelta(seconds=self.RECOVERY_TIME)
        now = datetime.now()

        if primary_health.last_failure:
            if now - primary_health.last_failure > recovery_time:
                # Reset and try again
                primary_health.available = True
                return preferred

        if fallback_health.last_failure:
            if now - fallback_health.last_failure > recovery_time:
                fallback_health.available = True
                return fallback

        # Both still failing, return whichever failed less recently
        if not primary_health.last_failure:
            return preferred
        if not fallback_health.last_failure:
            return fallback

        return preferred if primary_health.last_failure > fallback_health.last_failure else fallback

    def set_local_only_mode(self, enabled: bool):
        """Enable or disable local-only mode (Ollama only)."""
        self._local_only_mode = enabled
        self._update_mode()
        logger.info(f"Local-only mode {'enabled' if enabled else 'disabled'}")

    @property
    def is_local_only(self) -> bool:
        """Check if local-only mode is enabled."""
        return self._local_only_mode

    async def check_network(self, force: bool = False) -> bool:
        """Check if network is available.

        Uses DNS lookup to check connectivity. Results are cached for 30 seconds.
        """
        # Use cached result if recent
        if not force and self._last_network_check:
            if datetime.now() - self._last_network_check < timedelta(seconds=30):
                return self._network_available

        try:
            # Try to resolve a reliable DNS name
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                socket.gethostbyname,
                "dns.google"
            )
            self._network_available = True
        except (socket.gaierror, socket.timeout, OSError):
            self._network_available = False
            logger.warning("Network check failed - appears to be offline")

        self._last_network_check = datetime.now()
        self._update_mode()
        return self._network_available

    # =========================================================================
    # Tool Result Caching
    # =========================================================================

    def cache_tool_result(self, tool_name: str, args_hash: str, result: Any):
        """Cache a tool result for offline access."""
        cache_key = f"{tool_name}:{args_hash}"
        self._tool_cache[cache_key] = {
            "result": result,
            "cached_at": datetime.now(),
        }
        logger.debug(f"Cached result for {tool_name}")

    def get_cached_tool_result(self, tool_name: str, args_hash: str) -> Optional[dict]:
        """Get a cached tool result if available and not expired."""
        cache_key = f"{tool_name}:{args_hash}"
        cached = self._tool_cache.get(cache_key)

        if not cached:
            return None

        # Check if expired
        if datetime.now() - cached["cached_at"] > self._cache_max_age:
            del self._tool_cache[cache_key]
            return None

        return {
            "result": cached["result"],
            "cached": True,
            "cached_at": cached["cached_at"].isoformat(),
        }

    def clear_cache(self):
        """Clear all cached tool results."""
        self._tool_cache.clear()

    # =========================================================================
    # Request Queue (for rate limit handling)
    # =========================================================================

    async def queue_request(
        self,
        request_id: str,
        callback: Callable,
        *args,
        priority: int = 0,
        **kwargs
    ) -> bool:
        """Queue a request for later processing when rate limited.

        Returns True if queued successfully, False if queue is full.
        """
        async with self._lock:
            if len(self._request_queue) >= self.MAX_QUEUE_SIZE:
                logger.warning(f"Request queue full, rejecting {request_id}")
                return False

            self._request_queue.append(QueuedRequest(
                id=request_id,
                created_at=datetime.now(),
                callback=callback,
                args=args,
                kwargs=kwargs,
                priority=priority,
            ))
            logger.info(f"Queued request {request_id}, queue size: {len(self._request_queue)}")
            return True

    def get_queue_size(self) -> int:
        """Get current queue size."""
        return len(self._request_queue)

    def get_queue_wait_time(self) -> Optional[int]:
        """Get estimated wait time in seconds, or None if not rate limited."""
        for api_name, health in self._api_health.items():
            if health.is_rate_limited and health.rate_limited_until:
                remaining = (health.rate_limited_until - datetime.now()).total_seconds()
                return max(0, int(remaining))
        return None

    def is_any_api_rate_limited(self) -> bool:
        """Check if any API is currently rate limited."""
        return any(health.is_rate_limited for health in self._api_health.values())

    def get_next_available_time(self) -> Optional[datetime]:
        """Get the earliest time an API will become available.

        Returns None if no APIs are rate limited.
        """
        rate_limit_times = [
            health.rate_limited_until
            for health in self._api_health.values()
            if health.is_rate_limited and health.rate_limited_until
        ]
        if not rate_limit_times:
            return None
        return min(rate_limit_times)

    async def process_queue(self) -> List[dict]:
        """Process queued requests that can now be executed.

        This method should be called periodically or after rate limits expire.
        It processes requests in priority order (highest first), removing
        timed-out requests and executing those that can now proceed.

        Returns:
            List of result dicts with request_id, success, result/error
        """
        results = []
        now = datetime.now()

        async with self._lock:
            # Can't process if still rate limited on all APIs
            if self.is_any_api_rate_limited():
                # Check if at least one API is available
                available_api = None
                for api_name, health in self._api_health.items():
                    if health.available and not health.is_rate_limited:
                        available_api = api_name
                        break

                if not available_api:
                    logger.debug("All APIs still rate limited, queue processing deferred")
                    return results

            if not self._request_queue:
                return results

            # Sort by priority (descending) then by creation time (ascending)
            sorted_queue = sorted(
                self._request_queue,
                key=lambda r: (-r.priority, r.created_at)
            )

            # Process requests
            processed_ids = []
            for request in sorted_queue:
                # Check if request has timed out
                age_seconds = (now - request.created_at).total_seconds()
                if age_seconds > self.QUEUE_TIMEOUT:
                    logger.warning(f"Request {request.id} timed out after {age_seconds:.0f}s")
                    results.append({
                        "request_id": request.id,
                        "success": False,
                        "error": "Request timed out in queue",
                        "age_seconds": age_seconds,
                    })
                    processed_ids.append(request.id)
                    continue

                # Try to execute the callback
                try:
                    logger.info(f"Processing queued request {request.id}")
                    if asyncio.iscoroutinefunction(request.callback):
                        result = await request.callback(*request.args, **request.kwargs)
                    else:
                        result = request.callback(*request.args, **request.kwargs)

                    results.append({
                        "request_id": request.id,
                        "success": True,
                        "result": result,
                        "queue_time_seconds": age_seconds,
                    })
                    processed_ids.append(request.id)
                except Exception as e:
                    logger.error(f"Error processing queued request {request.id}: {e}")
                    # Check if it's a rate limit error - if so, stop processing
                    if "rate" in str(e).lower() or "429" in str(e):
                        logger.warning("Hit rate limit again while processing queue")
                        results.append({
                            "request_id": request.id,
                            "success": False,
                            "error": str(e),
                            "requeued": True,
                        })
                        break  # Stop processing, leave remaining in queue
                    else:
                        results.append({
                            "request_id": request.id,
                            "success": False,
                            "error": str(e),
                        })
                        processed_ids.append(request.id)

            # Remove processed requests from queue
            self._request_queue = deque(
                (r for r in self._request_queue if r.id not in processed_ids),
                maxlen=self.MAX_QUEUE_SIZE
            )

        if results:
            logger.info(f"Processed {len(processed_ids)} queued requests, {len(self._request_queue)} remaining")

        return results

    async def start_queue_processor(self, check_interval: float = 5.0):
        """Start background task to periodically process the queue.

        This runs indefinitely and checks the queue every check_interval seconds.
        Should be started when the server starts.

        Args:
            check_interval: Seconds between queue checks (default 5.0)
        """
        logger.info(f"Starting queue processor with {check_interval}s interval")
        self._queue_processor_running = True

        while self._queue_processor_running:
            try:
                # Only process if we have items and rate limit may have expired
                if self._request_queue:
                    wait_time = self.get_queue_wait_time()
                    if wait_time is None or wait_time <= 0:
                        await self.process_queue()

                await asyncio.sleep(check_interval)
            except asyncio.CancelledError:
                logger.info("Queue processor cancelled")
                break
            except Exception as e:
                logger.error(f"Queue processor error: {e}")
                await asyncio.sleep(check_interval)

        logger.info("Queue processor stopped")

    def stop_queue_processor(self):
        """Signal the queue processor to stop."""
        self._queue_processor_running = False

    def clear_queue(self) -> int:
        """Clear all pending requests from the queue.

        Returns:
            Number of requests cleared
        """
        count = len(self._request_queue)
        self._request_queue.clear()
        logger.info(f"Cleared {count} requests from queue")
        return count

    def get_queue_info(self) -> dict:
        """Get detailed information about the current queue state.

        Returns:
            Dict with queue statistics and pending request info
        """
        now = datetime.now()
        pending_requests = []

        for request in self._request_queue:
            age = (now - request.created_at).total_seconds()
            pending_requests.append({
                "id": request.id,
                "priority": request.priority,
                "age_seconds": int(age),
                "timeout_in": max(0, int(self.QUEUE_TIMEOUT - age)),
            })

        return {
            "size": len(self._request_queue),
            "max_size": self.MAX_QUEUE_SIZE,
            "timeout_seconds": self.QUEUE_TIMEOUT,
            "wait_time_seconds": self.get_queue_wait_time(),
            "next_available": self.get_next_available_time().isoformat() if self.get_next_available_time() else None,
            "pending_requests": pending_requests,
        }

    # =========================================================================
    # Status and Reporting
    # =========================================================================

    def get_status(self) -> dict:
        """Get current degradation status."""
        next_available = self.get_next_available_time()
        return {
            "mode": self._mode.name,
            "is_degraded": self.is_degraded,
            "mode_since": self._mode_changed_at.isoformat(),
            "network_available": self._network_available,
            "queue_size": len(self._request_queue),
            "queue_wait_seconds": self.get_queue_wait_time(),
            "queue_processor_running": self._queue_processor_running,
            "next_api_available": next_available.isoformat() if next_available else None,
            "apis": {
                name: health.to_dict()
                for name, health in self._api_health.items()
            },
            "cache_entries": len(self._tool_cache),
        }

    def reset_api_health(self, api_name: Optional[str] = None):
        """Reset API health status (useful for manual recovery)."""
        if api_name:
            if api_name in self._api_health:
                self._api_health[api_name] = APIHealth(name=api_name)
        else:
            self._api_health = {
                "claude": APIHealth(name="claude"),
                "openai": APIHealth(name="openai"),
                "ollama": APIHealth(name="ollama"),
            }
        self._update_mode()


# Global singleton instance
_degradation_service: Optional[DegradationService] = None


def get_degradation_service() -> DegradationService:
    """Get the global degradation service instance."""
    global _degradation_service
    if _degradation_service is None:
        _degradation_service = DegradationService()
    return _degradation_service
