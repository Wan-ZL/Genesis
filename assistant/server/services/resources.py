"""Resource monitoring service for tracking system resources.

This module provides:
- Memory usage tracking (process and system)
- CPU usage tracking
- Disk space monitoring
- Request rate limiting per client
- Automatic cleanup of old files
- Memory cleanup when thresholds exceeded
"""
import asyncio
import os
import shutil
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Callable, Optional
import psutil


class ResourceStatus(Enum):
    """Status levels for resource usage."""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class ResourceConfig:
    """Configuration for resource monitoring and limits."""
    # Memory limits (in MB)
    max_memory_mb: int = 512
    memory_warning_percent: float = 75.0
    memory_critical_percent: float = 90.0

    # CPU limits (percentage)
    cpu_warning_percent: float = 80.0
    cpu_critical_percent: float = 95.0

    # Disk limits (in GB)
    disk_warning_gb: float = 5.0
    disk_critical_gb: float = 1.0

    # Rate limiting
    max_requests_per_minute: int = 60
    rate_limit_window_seconds: int = 60

    # Cleanup settings
    file_max_age_days: int = 30
    cleanup_check_interval_hours: int = 24

    # Memory cleanup settings
    memory_cleanup_threshold_percent: float = 85.0


@dataclass
class ResourceSnapshot:
    """Point-in-time snapshot of resource usage."""
    timestamp: str
    memory: dict
    cpu: dict
    disk: dict
    status: ResourceStatus
    warnings: list = field(default_factory=list)


@dataclass
class RateLimitResult:
    """Result of a rate limit check."""
    allowed: bool
    current_count: int
    limit: int
    remaining: int
    reset_at: Optional[str] = None


class ResourceService:
    """Service for monitoring system resources and enforcing limits."""

    def __init__(self, config: Optional[ResourceConfig] = None, files_path: Optional[Path] = None):
        self.config = config or ResourceConfig()
        self.files_path = files_path

        # Rate limiting tracking: client_id -> deque of timestamps
        self._request_timestamps: dict[str, deque] = defaultdict(deque)

        # Cleanup tracking
        self._last_cleanup_check: Optional[float] = None

        # Warning/alert callbacks
        self._warning_callbacks: list[Callable] = []

        # CPU tracking (needs sampling over time for accuracy)
        self._process = psutil.Process()

    def get_memory_usage(self) -> dict:
        """Get current memory usage statistics."""
        # Process memory
        process_memory = self._process.memory_info()
        process_mb = process_memory.rss / (1024 * 1024)

        # System memory
        system_memory = psutil.virtual_memory()

        return {
            "process_mb": round(process_mb, 2),
            "process_percent": round(process_memory.rss / system_memory.total * 100, 2),
            "system_total_mb": round(system_memory.total / (1024 * 1024), 2),
            "system_available_mb": round(system_memory.available / (1024 * 1024), 2),
            "system_percent": system_memory.percent,
            "limit_mb": self.config.max_memory_mb,
            "status": self._get_memory_status(process_mb).value
        }

    def _get_memory_status(self, process_mb: float) -> ResourceStatus:
        """Determine memory status based on thresholds."""
        percent_of_limit = (process_mb / self.config.max_memory_mb) * 100
        if percent_of_limit >= self.config.memory_critical_percent:
            return ResourceStatus.CRITICAL
        elif percent_of_limit >= self.config.memory_warning_percent:
            return ResourceStatus.WARNING
        return ResourceStatus.HEALTHY

    def get_cpu_usage(self) -> dict:
        """Get current CPU usage statistics."""
        # Process CPU (averaged over 0.1 second)
        try:
            process_cpu = self._process.cpu_percent(interval=0.1)
        except Exception:
            process_cpu = 0.0

        # System CPU
        system_cpu = psutil.cpu_percent(interval=0.1)
        cpu_count = psutil.cpu_count()

        return {
            "process_percent": round(process_cpu, 2),
            "system_percent": round(system_cpu, 2),
            "cpu_count": cpu_count,
            "status": self._get_cpu_status(process_cpu).value
        }

    def _get_cpu_status(self, cpu_percent: float) -> ResourceStatus:
        """Determine CPU status based on thresholds."""
        if cpu_percent >= self.config.cpu_critical_percent:
            return ResourceStatus.CRITICAL
        elif cpu_percent >= self.config.cpu_warning_percent:
            return ResourceStatus.WARNING
        return ResourceStatus.HEALTHY

    def get_disk_usage(self) -> dict:
        """Get current disk usage statistics."""
        # Get disk usage for the partition containing the files path
        if self.files_path:
            path_to_check = self.files_path
        else:
            path_to_check = Path.cwd()

        try:
            disk = psutil.disk_usage(str(path_to_check))
            free_gb = disk.free / (1024 * 1024 * 1024)
        except Exception:
            # Fallback to root
            disk = psutil.disk_usage("/")
            free_gb = disk.free / (1024 * 1024 * 1024)

        return {
            "total_gb": round(disk.total / (1024 * 1024 * 1024), 2),
            "used_gb": round(disk.used / (1024 * 1024 * 1024), 2),
            "free_gb": round(free_gb, 2),
            "percent": disk.percent,
            "status": self._get_disk_status(free_gb).value
        }

    def _get_disk_status(self, free_gb: float) -> ResourceStatus:
        """Determine disk status based on thresholds."""
        if free_gb <= self.config.disk_critical_gb:
            return ResourceStatus.CRITICAL
        elif free_gb <= self.config.disk_warning_gb:
            return ResourceStatus.WARNING
        return ResourceStatus.HEALTHY

    def get_snapshot(self) -> ResourceSnapshot:
        """Get a complete snapshot of all resource usage."""
        memory = self.get_memory_usage()
        cpu = self.get_cpu_usage()
        disk = self.get_disk_usage()

        # Determine overall status (worst of all)
        statuses = [
            ResourceStatus(memory["status"]),
            ResourceStatus(cpu["status"]),
            ResourceStatus(disk["status"])
        ]
        if ResourceStatus.CRITICAL in statuses:
            overall_status = ResourceStatus.CRITICAL
        elif ResourceStatus.WARNING in statuses:
            overall_status = ResourceStatus.WARNING
        else:
            overall_status = ResourceStatus.HEALTHY

        # Collect warnings
        warnings = []
        if memory["status"] != "healthy":
            warnings.append(f"Memory usage {memory['status']}: {memory['process_mb']:.0f}MB / {memory['limit_mb']}MB")
        if cpu["status"] != "healthy":
            warnings.append(f"CPU usage {cpu['status']}: {cpu['process_percent']:.1f}%")
        if disk["status"] != "healthy":
            warnings.append(f"Disk space {disk['status']}: {disk['free_gb']:.1f}GB free")

        return ResourceSnapshot(
            timestamp=datetime.now().isoformat(),
            memory=memory,
            cpu=cpu,
            disk=disk,
            status=overall_status,
            warnings=warnings
        )

    def to_dict(self) -> dict:
        """Convert resource metrics to dictionary for JSON response."""
        snapshot = self.get_snapshot()
        return {
            "timestamp": snapshot.timestamp,
            "status": snapshot.status.value,
            "warnings": snapshot.warnings,
            "memory": snapshot.memory,
            "cpu": snapshot.cpu,
            "disk": snapshot.disk,
            "limits": {
                "max_memory_mb": self.config.max_memory_mb,
                "max_requests_per_minute": self.config.max_requests_per_minute,
                "file_max_age_days": self.config.file_max_age_days
            }
        }

    # Rate limiting methods
    def check_rate_limit(self, client_id: str = "default") -> RateLimitResult:
        """Check if a client is within rate limits.

        Args:
            client_id: Unique identifier for the client (e.g., IP address)

        Returns:
            RateLimitResult with allowed status and remaining quota
        """
        now = time.time()
        window_start = now - self.config.rate_limit_window_seconds

        # Get or create timestamp deque for this client
        timestamps = self._request_timestamps[client_id]

        # Remove old timestamps outside the window
        while timestamps and timestamps[0] < window_start:
            timestamps.popleft()

        current_count = len(timestamps)
        limit = self.config.max_requests_per_minute
        remaining = max(0, limit - current_count)
        allowed = current_count < limit

        # Calculate when the limit will reset (when oldest request expires)
        reset_at = None
        if timestamps:
            reset_time = timestamps[0] + self.config.rate_limit_window_seconds
            reset_at = datetime.fromtimestamp(reset_time).isoformat()

        return RateLimitResult(
            allowed=allowed,
            current_count=current_count,
            limit=limit,
            remaining=remaining,
            reset_at=reset_at
        )

    def record_request(self, client_id: str = "default"):
        """Record a request for rate limiting purposes.

        Args:
            client_id: Unique identifier for the client
        """
        now = time.time()
        self._request_timestamps[client_id].append(now)

    # Cleanup methods
    async def cleanup_old_files(self, dry_run: bool = False) -> dict:
        """Delete files older than the configured max age.

        Args:
            dry_run: If True, only report what would be deleted

        Returns:
            Dictionary with cleanup results
        """
        if not self.files_path or not self.files_path.exists():
            return {"deleted": [], "errors": [], "total_bytes_freed": 0}

        cutoff = datetime.now() - timedelta(days=self.config.file_max_age_days)
        deleted = []
        errors = []
        total_bytes = 0

        for file_path in self.files_path.rglob("*"):
            if not file_path.is_file():
                continue

            try:
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                if mtime < cutoff:
                    file_size = file_path.stat().st_size
                    if not dry_run:
                        file_path.unlink()
                    deleted.append({
                        "path": str(file_path),
                        "size_bytes": file_size,
                        "modified": mtime.isoformat()
                    })
                    total_bytes += file_size
            except Exception as e:
                errors.append({"path": str(file_path), "error": str(e)})

        self._last_cleanup_check = time.time()

        return {
            "deleted": deleted,
            "errors": errors,
            "total_bytes_freed": total_bytes,
            "dry_run": dry_run
        }

    def should_run_cleanup(self) -> bool:
        """Check if cleanup should be run based on interval."""
        if self._last_cleanup_check is None:
            return True

        hours_since_check = (time.time() - self._last_cleanup_check) / 3600
        return hours_since_check >= self.config.cleanup_check_interval_hours

    # Memory cleanup methods
    def should_cleanup_memory(self) -> bool:
        """Check if memory cleanup should be triggered."""
        memory = self.get_memory_usage()
        percent_of_limit = (memory["process_mb"] / self.config.max_memory_mb) * 100
        return percent_of_limit >= self.config.memory_cleanup_threshold_percent

    async def cleanup_memory(self) -> dict:
        """Attempt to free memory by clearing caches and running GC.

        Returns:
            Dictionary with cleanup results
        """
        import gc

        memory_before = self.get_memory_usage()

        # Force garbage collection
        gc.collect()

        # Clear rate limiting cache (old entries)
        now = time.time()
        window_start = now - self.config.rate_limit_window_seconds
        for client_id in list(self._request_timestamps.keys()):
            timestamps = self._request_timestamps[client_id]
            while timestamps and timestamps[0] < window_start:
                timestamps.popleft()
            if not timestamps:
                del self._request_timestamps[client_id]

        memory_after = self.get_memory_usage()
        freed_mb = memory_before["process_mb"] - memory_after["process_mb"]

        return {
            "memory_before_mb": memory_before["process_mb"],
            "memory_after_mb": memory_after["process_mb"],
            "freed_mb": round(max(0, freed_mb), 2),
            "gc_collected": gc.get_count()
        }

    # Callback registration
    def register_warning_callback(self, callback: Callable):
        """Register a callback to be called when warnings are generated."""
        self._warning_callbacks.append(callback)

    async def check_and_alert(self):
        """Check resource status and trigger alerts if needed."""
        snapshot = self.get_snapshot()

        if snapshot.warnings and self._warning_callbacks:
            for callback in self._warning_callbacks:
                try:
                    result = callback(snapshot)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception:
                    pass  # Don't let callback errors break monitoring

        return snapshot

    def reset(self):
        """Reset all tracking data (useful for testing)."""
        self._request_timestamps.clear()
        self._last_cleanup_check = None


# Global instance will be created with proper config when imported
resources: Optional[ResourceService] = None


def get_resource_service(files_path: Optional[Path] = None, config: Optional[ResourceConfig] = None) -> ResourceService:
    """Get or create the global resource service instance."""
    global resources
    if resources is None:
        resources = ResourceService(config=config, files_path=files_path)
    return resources
