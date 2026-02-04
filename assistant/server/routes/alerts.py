"""Alerts API endpoints."""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
import shutil
from pathlib import Path

from server.services.alerts import (
    AlertService, AlertConfig, AlertType, AlertSeverity, Alert
)
import config

router = APIRouter()

# Global alert service instance (initialized on startup)
_alert_service: Optional[AlertService] = None


def get_alert_service() -> AlertService:
    """Get or create the alert service singleton."""
    global _alert_service
    if _alert_service is None:
        db_path = config.DATABASE_PATH.parent / "alerts.db"
        _alert_service = AlertService(db_path)
    return _alert_service


def init_alert_service(alert_config: Optional[AlertConfig] = None):
    """Initialize the alert service with optional config."""
    global _alert_service
    db_path = config.DATABASE_PATH.parent / "alerts.db"
    _alert_service = AlertService(db_path, config=alert_config)
    return _alert_service


class AlertResponse(BaseModel):
    """Response model for alert data."""
    id: str
    type: str
    severity: str
    title: str
    message: str
    timestamp: str
    metadata: dict
    acknowledged: bool
    acknowledged_at: Optional[str]


class CreateAlertRequest(BaseModel):
    """Request model for creating custom alerts."""
    type: str = "custom"
    severity: str = "info"
    title: str
    message: str
    metadata: Optional[dict] = None


class ComponentHealth(BaseModel):
    """Health status of a system component."""
    name: str
    status: str  # healthy, degraded, unhealthy
    message: Optional[str] = None
    details: Optional[dict] = None


class DetailedHealthResponse(BaseModel):
    """Detailed health check response."""
    status: str  # healthy, degraded, unhealthy
    version: str
    uptime_seconds: int
    components: list[ComponentHealth]
    alerts: dict  # summary of recent alerts


@router.get("/health/detailed")
async def detailed_health_check() -> DetailedHealthResponse:
    """Enhanced health check with component status.

    Checks:
    - Database connectivity
    - Disk space
    - Recent error count
    - Alert service status
    """
    import time

    # Try to get version
    try:
        from version import __version__
    except ImportError:
        __version__ = "unknown"

    # Try to get uptime
    try:
        from server.routes.status import _start_time
        uptime = int(time.time() - _start_time)
    except (ImportError, NameError):
        uptime = 0

    components = []
    overall_status = "healthy"

    # Check database
    try:
        from server.services.memory import MemoryService
        memory = MemoryService(config.DATABASE_PATH)
        await memory._ensure_initialized()
        components.append(ComponentHealth(
            name="database",
            status="healthy",
            message="SQLite database accessible"
        ))
    except Exception as e:
        overall_status = "unhealthy"
        components.append(ComponentHealth(
            name="database",
            status="unhealthy",
            message=f"Database error: {str(e)}"
        ))

    # Check disk space
    try:
        memory_dir = config.DATABASE_PATH.parent
        disk_usage = shutil.disk_usage(memory_dir)
        free_gb = disk_usage.free / (1024 ** 3)

        alert_config = get_alert_service().config
        if free_gb < alert_config.disk_space_critical_gb:
            overall_status = "unhealthy"
            components.append(ComponentHealth(
                name="disk_space",
                status="unhealthy",
                message=f"Critical: Only {free_gb:.1f}GB free",
                details={"free_gb": round(free_gb, 2), "total_gb": round(disk_usage.total / (1024 ** 3), 2)}
            ))
        elif free_gb < alert_config.disk_space_warning_gb:
            if overall_status == "healthy":
                overall_status = "degraded"
            components.append(ComponentHealth(
                name="disk_space",
                status="degraded",
                message=f"Warning: Only {free_gb:.1f}GB free",
                details={"free_gb": round(free_gb, 2), "total_gb": round(disk_usage.total / (1024 ** 3), 2)}
            ))
        else:
            components.append(ComponentHealth(
                name="disk_space",
                status="healthy",
                message=f"{free_gb:.1f}GB available",
                details={"free_gb": round(free_gb, 2), "total_gb": round(disk_usage.total / (1024 ** 3), 2)}
            ))
    except Exception as e:
        if overall_status == "healthy":
            overall_status = "degraded"
        components.append(ComponentHealth(
            name="disk_space",
            status="degraded",
            message=f"Unable to check: {str(e)}"
        ))

    # Check error rate
    alert_service = get_alert_service()
    error_count = alert_service.get_error_count()
    if error_count > alert_service.config.error_threshold:
        if overall_status == "healthy":
            overall_status = "degraded"
        components.append(ComponentHealth(
            name="error_rate",
            status="degraded",
            message=f"High error rate: {error_count} errors in {alert_service.config.error_window_seconds}s",
            details={"error_count": error_count, "threshold": alert_service.config.error_threshold}
        ))
    else:
        components.append(ComponentHealth(
            name="error_rate",
            status="healthy",
            message=f"{error_count} errors in window",
            details={"error_count": error_count, "threshold": alert_service.config.error_threshold}
        ))

    # Check alert service
    try:
        stats = await alert_service.get_alert_stats()
        components.append(ComponentHealth(
            name="alerts",
            status="healthy",
            message=f"{stats['unacknowledged']} unacknowledged alerts",
            details=stats
        ))
    except Exception as e:
        if overall_status == "healthy":
            overall_status = "degraded"
        components.append(ComponentHealth(
            name="alerts",
            status="degraded",
            message=f"Alert service error: {str(e)}"
        ))

    # Get alert summary
    try:
        stats = await alert_service.get_alert_stats()
        alert_summary = {
            "total": stats["total"],
            "unacknowledged": stats["unacknowledged"],
            "recent_24h": stats["recent_24h"]
        }
    except Exception:
        alert_summary = {"error": "Unable to retrieve"}

    return DetailedHealthResponse(
        status=overall_status,
        version=__version__,
        uptime_seconds=uptime,
        components=components,
        alerts=alert_summary
    )


@router.get("/alerts")
async def list_alerts(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    type: Optional[str] = None,
    severity: Optional[str] = None,
    acknowledged: Optional[bool] = None
) -> dict:
    """List alerts with optional filtering."""
    service = get_alert_service()

    # Convert string params to enums if provided
    alert_type = AlertType(type) if type else None
    alert_severity = AlertSeverity(severity) if severity else None

    try:
        alerts = await service.list_alerts(
            limit=limit,
            offset=offset,
            alert_type=alert_type,
            severity=alert_severity,
            acknowledged=acknowledged
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "alerts": [
            AlertResponse(
                id=a.id,
                type=a.type.value,
                severity=a.severity.value,
                title=a.title,
                message=a.message,
                timestamp=a.timestamp,
                metadata=a.metadata,
                acknowledged=a.acknowledged,
                acknowledged_at=a.acknowledged_at
            ).model_dump()
            for a in alerts
        ],
        "count": len(alerts),
        "limit": limit,
        "offset": offset
    }


@router.get("/alerts/stats")
async def get_alert_stats() -> dict:
    """Get alert statistics."""
    service = get_alert_service()
    return await service.get_alert_stats()


@router.get("/alerts/{alert_id}")
async def get_alert(alert_id: str):
    """Get a single alert by ID."""
    service = get_alert_service()
    alert = await service.get_alert(alert_id)

    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    return AlertResponse(
        id=alert.id,
        type=alert.type.value,
        severity=alert.severity.value,
        title=alert.title,
        message=alert.message,
        timestamp=alert.timestamp,
        metadata=alert.metadata,
        acknowledged=alert.acknowledged,
        acknowledged_at=alert.acknowledged_at
    )


@router.post("/alerts")
async def create_alert(request: CreateAlertRequest):
    """Create a custom alert."""
    service = get_alert_service()

    try:
        alert_type = AlertType(request.type)
        severity = AlertSeverity(request.severity)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    alert = await service.create_alert(
        alert_type=alert_type,
        severity=severity,
        title=request.title,
        message=request.message,
        metadata=request.metadata
    )

    if alert is None:
        raise HTTPException(status_code=429, detail="Rate limited")

    return AlertResponse(
        id=alert.id,
        type=alert.type.value,
        severity=alert.severity.value,
        title=alert.title,
        message=alert.message,
        timestamp=alert.timestamp,
        metadata=alert.metadata,
        acknowledged=alert.acknowledged,
        acknowledged_at=alert.acknowledged_at
    )


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str):
    """Acknowledge an alert."""
    service = get_alert_service()
    success = await service.acknowledge_alert(alert_id)

    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")

    return {"acknowledged": True, "alert_id": alert_id}


@router.delete("/alerts/old")
async def clear_old_alerts(days: int = Query(30, ge=1, le=365)):
    """Delete alerts older than specified days."""
    service = get_alert_service()
    deleted = await service.clear_old_alerts(days)
    return {"deleted_count": deleted, "days": days}
