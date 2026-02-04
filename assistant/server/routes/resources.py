"""Resource monitoring API endpoints."""
import logging
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from typing import Optional

from server.services.resources import get_resource_service, ResourceConfig
import config

router = APIRouter()
logger = logging.getLogger(__name__)

# Initialize resource service
resources = get_resource_service(files_path=config.FILES_PATH)


class ResourceLimitsUpdate(BaseModel):
    """Request model for updating resource limits."""
    max_memory_mb: Optional[int] = None
    max_requests_per_minute: Optional[int] = None
    file_max_age_days: Optional[int] = None


@router.get("/resources")
async def get_resources():
    """Get current resource usage and status.

    Returns detailed information about:
    - Memory usage (process and system)
    - CPU usage (process and system)
    - Disk space
    - Current limits and thresholds
    - Any active warnings
    """
    return resources.to_dict()


@router.get("/resources/memory")
async def get_memory():
    """Get detailed memory usage."""
    return resources.get_memory_usage()


@router.get("/resources/cpu")
async def get_cpu():
    """Get detailed CPU usage."""
    return resources.get_cpu_usage()


@router.get("/resources/disk")
async def get_disk():
    """Get detailed disk usage."""
    return resources.get_disk_usage()


@router.get("/resources/rate-limit")
async def check_rate_limit(client_id: str = Query(default="default", description="Client identifier")):
    """Check rate limit status for a client.

    Returns:
        - allowed: Whether the client can make another request
        - current_count: Number of requests in the current window
        - limit: Maximum requests allowed per window
        - remaining: Requests remaining in window
        - reset_at: When the rate limit window resets
    """
    result = resources.check_rate_limit(client_id)
    return {
        "allowed": result.allowed,
        "current_count": result.current_count,
        "limit": result.limit,
        "remaining": result.remaining,
        "reset_at": result.reset_at
    }


@router.post("/resources/cleanup/files")
async def cleanup_files(dry_run: bool = Query(default=False, description="Only report what would be deleted")):
    """Clean up old files based on configured max age.

    Args:
        dry_run: If true, only shows what would be deleted without actually deleting

    Returns:
        - deleted: List of files that were (or would be) deleted
        - errors: Any errors encountered
        - total_bytes_freed: Total bytes freed (or that would be freed)
    """
    result = await resources.cleanup_old_files(dry_run=dry_run)
    return result


@router.post("/resources/cleanup/memory")
async def cleanup_memory():
    """Attempt to free memory by clearing caches and running garbage collection.

    Returns:
        - memory_before_mb: Memory usage before cleanup
        - memory_after_mb: Memory usage after cleanup
        - freed_mb: Amount of memory freed
    """
    result = await resources.cleanup_memory()
    return result


@router.get("/resources/limits")
async def get_limits():
    """Get current resource limits configuration."""
    cfg = resources.config
    return {
        "max_memory_mb": cfg.max_memory_mb,
        "memory_warning_percent": cfg.memory_warning_percent,
        "memory_critical_percent": cfg.memory_critical_percent,
        "cpu_warning_percent": cfg.cpu_warning_percent,
        "cpu_critical_percent": cfg.cpu_critical_percent,
        "disk_warning_gb": cfg.disk_warning_gb,
        "disk_critical_gb": cfg.disk_critical_gb,
        "max_requests_per_minute": cfg.max_requests_per_minute,
        "file_max_age_days": cfg.file_max_age_days,
        "cleanup_check_interval_hours": cfg.cleanup_check_interval_hours,
        "memory_cleanup_threshold_percent": cfg.memory_cleanup_threshold_percent
    }


@router.post("/resources/limits")
async def update_limits(limits: ResourceLimitsUpdate):
    """Update resource limits configuration.

    Only provided fields will be updated.
    """
    cfg = resources.config
    updated = {}

    if limits.max_memory_mb is not None:
        if limits.max_memory_mb < 64:
            raise HTTPException(status_code=400, detail="max_memory_mb must be at least 64")
        cfg.max_memory_mb = limits.max_memory_mb
        updated["max_memory_mb"] = limits.max_memory_mb

    if limits.max_requests_per_minute is not None:
        if limits.max_requests_per_minute < 1:
            raise HTTPException(status_code=400, detail="max_requests_per_minute must be at least 1")
        cfg.max_requests_per_minute = limits.max_requests_per_minute
        updated["max_requests_per_minute"] = limits.max_requests_per_minute

    if limits.file_max_age_days is not None:
        if limits.file_max_age_days < 1:
            raise HTTPException(status_code=400, detail="file_max_age_days must be at least 1")
        cfg.file_max_age_days = limits.file_max_age_days
        updated["file_max_age_days"] = limits.file_max_age_days

    return {"status": "ok", "updated": updated}


@router.post("/resources/check")
async def check_resources():
    """Check resource status and return any warnings.

    This endpoint can be called periodically to monitor system health.
    Returns the current snapshot with any active warnings.
    """
    snapshot = await resources.check_and_alert()
    return {
        "timestamp": snapshot.timestamp,
        "status": snapshot.status.value,
        "warnings": snapshot.warnings,
        "memory": snapshot.memory,
        "cpu": snapshot.cpu,
        "disk": snapshot.disk
    }
