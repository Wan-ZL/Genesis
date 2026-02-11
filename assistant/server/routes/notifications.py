"""Notification API routes."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import logging
import config

from server.services.proactive import get_proactive_service, init_proactive_service, NotificationType, NotificationPriority

logger = logging.getLogger(__name__)
router = APIRouter()


# Initialization functions
async def init_proactive():
    """Initialize and start proactive service."""
    db_path = config.DATABASE_PATH.parent / "proactive.db"
    proactive_svc = init_proactive_service(db_path)
    await proactive_svc.start()


async def stop_proactive():
    """Stop proactive service."""
    try:
        proactive_svc = get_proactive_service()
        await proactive_svc.stop()
    except ValueError:
        # Service not initialized, nothing to stop
        pass


class NotificationResponse(BaseModel):
    """Notification response model."""
    id: str
    type: str
    title: str
    body: str
    priority: str
    created_at: str
    read_at: Optional[str]
    action_url: Optional[str]
    metadata: dict


class NotificationListResponse(BaseModel):
    """List of notifications response."""
    notifications: list[NotificationResponse]
    unread_count: int
    total: int


class ProactiveConfigRequest(BaseModel):
    """Proactive configuration request model."""
    calendar_reminder_enabled: Optional[bool] = None
    calendar_reminder_minutes: Optional[int] = None
    daily_briefing_enabled: Optional[bool] = None
    daily_briefing_hour: Optional[int] = None
    daily_briefing_minute: Optional[int] = None
    system_health_enabled: Optional[bool] = None
    system_health_interval_minutes: Optional[int] = None
    quiet_hours_enabled: Optional[bool] = None
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None


@router.get("/notifications")
async def get_notifications(
    unread_only: bool = False,
    limit: int = 50,
    offset: int = 0
):
    """Get notifications.

    Args:
        unread_only: Only return unread notifications
        limit: Maximum number of notifications to return
        offset: Offset for pagination

    Returns:
        List of notifications with unread count
    """
    try:
        proactive_svc = get_proactive_service()
        notifications = await proactive_svc.get_notifications(
            unread_only=unread_only,
            limit=limit,
            offset=offset
        )
        unread_count = await proactive_svc.get_unread_count()

        return NotificationListResponse(
            notifications=[NotificationResponse(**n.to_dict()) for n in notifications],
            unread_count=unread_count,
            total=len(notifications)
        )
    except Exception as e:
        logger.error(f"Failed to get notifications: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/notifications/unread-count")
async def get_unread_count():
    """Get count of unread notifications.

    Returns:
        Dict with unread count
    """
    try:
        proactive_svc = get_proactive_service()
        count = await proactive_svc.get_unread_count()
        return {"unread_count": count}
    except Exception as e:
        logger.error(f"Failed to get unread count: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/notifications/{notification_id}/read")
async def mark_notification_as_read(notification_id: str):
    """Mark a notification as read.

    Args:
        notification_id: ID of notification to mark as read

    Returns:
        Success status
    """
    try:
        proactive_svc = get_proactive_service()
        success = await proactive_svc.mark_as_read(notification_id)

        if not success:
            raise HTTPException(status_code=404, detail="Notification not found or already read")

        return {"success": True, "notification_id": notification_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to mark notification as read: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/notifications/read-all")
async def mark_all_as_read():
    """Mark all notifications as read.

    Returns:
        Number of notifications marked as read
    """
    try:
        proactive_svc = get_proactive_service()
        count = await proactive_svc.mark_all_as_read()
        return {"success": True, "count": count}
    except Exception as e:
        logger.error(f"Failed to mark all as read: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/notifications/{notification_id}")
async def delete_notification(notification_id: str):
    """Delete a notification.

    Args:
        notification_id: ID of notification to delete

    Returns:
        Success status
    """
    try:
        proactive_svc = get_proactive_service()
        success = await proactive_svc.delete_notification(notification_id)

        if not success:
            raise HTTPException(status_code=404, detail="Notification not found")

        return {"success": True, "notification_id": notification_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete notification: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/notifications/config")
async def get_proactive_config():
    """Get proactive notification configuration.

    Returns:
        Proactive configuration
    """
    try:
        proactive_svc = get_proactive_service()
        config = await proactive_svc.get_config()
        return vars(config)
    except Exception as e:
        logger.error(f"Failed to get proactive config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/notifications/config")
async def update_proactive_config(request: ProactiveConfigRequest):
    """Update proactive notification configuration.

    Args:
        request: Configuration update request

    Returns:
        Updated configuration
    """
    try:
        proactive_svc = get_proactive_service()
        current_config = await proactive_svc.get_config()

        # Update only provided fields
        for key, value in request.model_dump(exclude_unset=True).items():
            if hasattr(current_config, key) and value is not None:
                setattr(current_config, key, value)

        await proactive_svc.update_config(current_config)
        return {"success": True, "config": vars(current_config)}
    except Exception as e:
        logger.error(f"Failed to update proactive config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/notifications/test")
async def create_test_notification():
    """Create a test notification for debugging.

    Returns:
        Created notification
    """
    try:
        proactive_svc = get_proactive_service()
        notification = await proactive_svc.create_notification(
            type=NotificationType.CUSTOM,
            title="Test Notification",
            body="This is a test notification to verify the system is working.",
            priority=NotificationPriority.NORMAL
        )
        return NotificationResponse(**notification.to_dict())
    except Exception as e:
        logger.error(f"Failed to create test notification: {e}")
        raise HTTPException(status_code=500, detail=str(e))
