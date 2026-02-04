"""Degradation status API endpoints."""
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from server.services.degradation import get_degradation_service, DegradationMode

router = APIRouter()
logger = logging.getLogger(__name__)


class DegradationStatus(BaseModel):
    """Degradation status response."""
    mode: str
    is_degraded: bool
    mode_since: str
    network_available: bool
    queue_size: int
    queue_wait_seconds: Optional[int]
    apis: dict
    cache_entries: int


class ResetRequest(BaseModel):
    """Request to reset API health."""
    api_name: Optional[str] = None  # None = reset all


@router.get("/degradation", response_model=DegradationStatus)
async def get_degradation_status():
    """Get current degradation mode and API health status.

    Returns information about:
    - Current degradation mode (NORMAL, CLAUDE_UNAVAILABLE, OPENAI_UNAVAILABLE, RATE_LIMITED, OFFLINE)
    - API health for Claude and OpenAI
    - Network availability
    - Request queue status (if rate limited)
    - Cached tool results count
    """
    service = get_degradation_service()
    status = service.get_status()
    return DegradationStatus(**status)


@router.post("/degradation/reset")
async def reset_api_health(request: ResetRequest):
    """Reset API health status.

    Use this to manually recover from degraded state after fixing issues.
    Pass api_name to reset specific API, or omit to reset all.
    """
    service = get_degradation_service()
    service.reset_api_health(request.api_name)
    return {
        "success": True,
        "message": f"Reset {'all APIs' if not request.api_name else request.api_name}",
        "current_status": service.get_status()
    }


@router.post("/degradation/check-network")
async def check_network():
    """Force a network connectivity check.

    Returns current network availability and updates degradation mode.
    """
    service = get_degradation_service()
    is_available = await service.check_network(force=True)
    return {
        "network_available": is_available,
        "mode": service.mode.name,
    }


@router.delete("/degradation/cache")
async def clear_cache():
    """Clear all cached tool results.

    Tool results are cached for offline access. Use this to force fresh data.
    """
    service = get_degradation_service()
    count = len(service._tool_cache)
    service.clear_cache()
    return {
        "success": True,
        "cleared_entries": count,
    }
