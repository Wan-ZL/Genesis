"""Rate limiter for tool execution.

Implements token bucket algorithm for per-tool rate limiting.
"""

import time
import logging
from typing import Dict, Optional
from dataclasses import dataclass, field
from threading import Lock

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Rate limit configuration for a tool."""
    # Maximum requests per window
    max_requests: int = 10
    # Time window in seconds
    window_seconds: int = 60
    # Burst allowance (extra tokens available immediately)
    burst: int = 5


@dataclass
class TokenBucket:
    """Token bucket for rate limiting."""
    capacity: float
    tokens: float
    refill_rate: float  # tokens per second
    last_refill: float = field(default_factory=time.time)
    lock: Lock = field(default_factory=Lock)

    def consume(self, tokens: int = 1) -> tuple[bool, float]:
        """Try to consume tokens from bucket.

        Args:
            tokens: Number of tokens to consume

        Returns:
            Tuple of (success, remaining_tokens)
        """
        with self.lock:
            # Refill tokens based on time elapsed
            now = time.time()
            elapsed = now - self.last_refill
            self.tokens = min(
                self.capacity,
                self.tokens + elapsed * self.refill_rate
            )
            self.last_refill = now

            # Try to consume
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True, self.tokens
            else:
                return False, self.tokens

    def get_wait_time(self, tokens: int = 1) -> float:
        """Get time to wait until tokens are available.

        Args:
            tokens: Number of tokens needed

        Returns:
            Seconds to wait (0 if tokens available now)
        """
        with self.lock:
            if self.tokens >= tokens:
                return 0.0
            needed = tokens - self.tokens
            return needed / self.refill_rate


class ToolRateLimiter:
    """Manages rate limits for tool execution."""

    # Default rate limits per tool type
    DEFAULT_LIMITS = {
        # Shell commands are dangerous, limit strictly
        'run_shell_command': RateLimitConfig(max_requests=5, window_seconds=60, burst=2),
        # Web fetches consume network, moderate limit
        'web_fetch': RateLimitConfig(max_requests=30, window_seconds=60, burst=10),
        # File operations, moderate limit
        'read_file': RateLimitConfig(max_requests=50, window_seconds=60, burst=10),
        'list_files': RateLimitConfig(max_requests=50, window_seconds=60, burst=10),
        'search_code': RateLimitConfig(max_requests=30, window_seconds=60, burst=5),
        # Calendar operations, moderate limit
        'list_events': RateLimitConfig(max_requests=20, window_seconds=60, burst=5),
        'create_event': RateLimitConfig(max_requests=10, window_seconds=60, burst=3),
        'update_event': RateLimitConfig(max_requests=10, window_seconds=60, burst=3),
        'delete_event': RateLimitConfig(max_requests=10, window_seconds=60, burst=3),
        # MCP tools, conservative limit
        'mcp': RateLimitConfig(max_requests=20, window_seconds=60, burst=5),
        # Default for unknown tools
        'default': RateLimitConfig(max_requests=30, window_seconds=60, burst=10),
    }

    def __init__(self):
        self._buckets: Dict[str, TokenBucket] = {}
        self._configs: Dict[str, RateLimitConfig] = self.DEFAULT_LIMITS.copy()

    def _get_bucket(self, tool_name: str) -> TokenBucket:
        """Get or create token bucket for a tool."""
        if tool_name not in self._buckets:
            # Determine config
            config = self._configs.get(tool_name)

            # Check for MCP tools
            if config is None and tool_name.startswith('mcp:'):
                config = self._configs['mcp']

            # Fallback to default
            if config is None:
                config = self._configs['default']

            # Create bucket
            capacity = config.max_requests + config.burst
            refill_rate = config.max_requests / config.window_seconds

            self._buckets[tool_name] = TokenBucket(
                capacity=capacity,
                tokens=capacity,  # Start full
                refill_rate=refill_rate
            )

        return self._buckets[tool_name]

    def check_rate_limit(self, tool_name: str) -> tuple[bool, Optional[float], float]:
        """Check if tool execution is allowed under rate limit.

        Args:
            tool_name: Name of the tool

        Returns:
            Tuple of (allowed, retry_after_seconds, remaining_quota)
        """
        bucket = self._get_bucket(tool_name)
        allowed, remaining = bucket.consume()

        if allowed:
            logger.debug(f"Rate limit OK for {tool_name}: {remaining:.1f} tokens remaining")
            return True, None, remaining
        else:
            retry_after = bucket.get_wait_time()
            logger.warning(
                f"Rate limit exceeded for {tool_name}: "
                f"retry after {retry_after:.1f}s"
            )
            return False, retry_after, 0.0

    def set_limit(self, tool_name: str, config: RateLimitConfig):
        """Set custom rate limit for a tool.

        Args:
            tool_name: Name of the tool
            config: Rate limit configuration
        """
        self._configs[tool_name] = config
        # Remove existing bucket so it gets recreated with new config
        if tool_name in self._buckets:
            del self._buckets[tool_name]
        logger.info(
            f"Set rate limit for {tool_name}: "
            f"{config.max_requests}/{config.window_seconds}s"
        )

    def reset(self, tool_name: Optional[str] = None):
        """Reset rate limit state.

        Args:
            tool_name: Specific tool to reset, or None for all tools
        """
        if tool_name:
            if tool_name in self._buckets:
                del self._buckets[tool_name]
                logger.info(f"Reset rate limit for {tool_name}")
        else:
            self._buckets.clear()
            logger.info("Reset all rate limits")

    def get_status(self, tool_name: Optional[str] = None) -> Dict[str, Dict]:
        """Get rate limit status.

        Args:
            tool_name: Specific tool, or None for all tools

        Returns:
            Dict mapping tool names to status dicts
        """
        status = {}

        if tool_name:
            bucket = self._get_bucket(tool_name)
            config = self._configs.get(tool_name, self._configs['default'])
            status[tool_name] = {
                'remaining': bucket.tokens,
                'capacity': bucket.capacity,
                'max_requests': config.max_requests,
                'window_seconds': config.window_seconds,
            }
        else:
            for name, bucket in self._buckets.items():
                config = self._configs.get(name, self._configs['default'])
                status[name] = {
                    'remaining': bucket.tokens,
                    'capacity': bucket.capacity,
                    'max_requests': config.max_requests,
                    'window_seconds': config.window_seconds,
                }

        return status


# Global instance
_rate_limiter: Optional[ToolRateLimiter] = None


def get_rate_limiter() -> ToolRateLimiter:
    """Get or create the global rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = ToolRateLimiter()
    return _rate_limiter
