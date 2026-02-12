"""Audit log API endpoints."""

from fastapi import APIRouter, Query
from typing import Optional, List, Dict, Any
from pydantic import BaseModel

from server.services.audit import get_audit_logger

router = APIRouter()


class AuditLogEntryResponse(BaseModel):
    """Response model for audit log entry."""
    timestamp: str
    tool_name: str
    args_hash: str
    result_summary: str
    user_ip: Optional[str]
    success: bool
    duration_ms: float
    sandboxed: bool
    rate_limited: bool


class AuditLogResponse(BaseModel):
    """Response model for audit log query."""
    entries: List[AuditLogEntryResponse]
    total: int
    limit: int
    offset: int


class AuditStatsResponse(BaseModel):
    """Response model for audit statistics."""
    total_executions: int
    successful_executions: int
    success_rate: float
    top_tools: List[Dict[str, Any]]
    recent_failures: List[Dict[str, Any]]
    avg_durations: List[Dict[str, Any]]


@router.get("/audit", response_model=AuditLogResponse)
async def get_audit_log(
    tool_name: Optional[str] = Query(None, description="Filter by tool name"),
    success: Optional[bool] = Query(None, description="Filter by success status"),
    start_time: Optional[str] = Query(None, description="Start timestamp (ISO format)"),
    end_time: Optional[str] = Query(None, description="End timestamp (ISO format)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum entries to return"),
    offset: int = Query(0, ge=0, description="Number of entries to skip"),
):
    """Query audit log entries with filters and pagination."""
    audit_logger = get_audit_logger()

    entries = audit_logger.query(
        tool_name=tool_name,
        success=success,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        offset=offset,
    )

    # Convert to response models
    entry_responses = [
        AuditLogEntryResponse(
            timestamp=e.timestamp,
            tool_name=e.tool_name,
            args_hash=e.args_hash,
            result_summary=e.result_summary,
            user_ip=e.user_ip,
            success=e.success,
            duration_ms=e.duration_ms,
            sandboxed=e.sandboxed,
            rate_limited=e.rate_limited,
        )
        for e in entries
    ]

    return AuditLogResponse(
        entries=entry_responses,
        total=len(entry_responses),
        limit=limit,
        offset=offset,
    )


@router.get("/audit/stats", response_model=AuditStatsResponse)
async def get_audit_stats():
    """Get statistics from audit log."""
    audit_logger = get_audit_logger()
    stats = audit_logger.get_stats()

    return AuditStatsResponse(**stats)
