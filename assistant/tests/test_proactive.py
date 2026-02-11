"""Tests for proactive notification service."""
import pytest
import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
import tempfile

from server.services.proactive import (
    ProactiveService,
    ProactiveConfig,
    Notification,
    NotificationType,
    NotificationPriority
)


@pytest.fixture
async def proactive_service():
    """Create a temporary proactive service for testing."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
        db_path = Path(tmp.name)
    
    service = ProactiveService(db_path)
    await service._ensure_initialized()
    
    yield service
    
    # Cleanup
    try:
        db_path.unlink()
    except:
        pass


@pytest.mark.asyncio
async def test_create_notification(proactive_service):
    """Test creating a notification."""
    notification = await proactive_service.create_notification(
        type=NotificationType.CUSTOM,
        title="Test Title",
        body="Test body content",
        priority=NotificationPriority.HIGH,
        action_url="/test"
    )
    
    assert notification.id.startswith("notif_")
    assert notification.type == NotificationType.CUSTOM
    assert notification.title == "Test Title"
    assert notification.body == "Test body content"
    assert notification.priority == NotificationPriority.HIGH
    assert notification.action_url == "/test"
    assert notification.read_at is None


@pytest.mark.asyncio
async def test_get_notifications(proactive_service):
    """Test retrieving notifications."""
    # Create test notifications
    await proactive_service.create_notification(
        type=NotificationType.CUSTOM,
        title="First",
        body="Body 1"
    )
    await proactive_service.create_notification(
        type=NotificationType.CUSTOM,
        title="Second",
        body="Body 2"
    )
    
    # Get all notifications
    notifications = await proactive_service.get_notifications()
    
    assert len(notifications) == 2
    # Should be in reverse chronological order
    assert notifications[0].title == "Second"
    assert notifications[1].title == "First"


@pytest.mark.asyncio
async def test_get_unread_count(proactive_service):
    """Test getting unread notification count."""
    # Initially zero
    count = await proactive_service.get_unread_count()
    assert count == 0
    
    # Create notifications
    notif1 = await proactive_service.create_notification(
        type=NotificationType.CUSTOM,
        title="Test 1",
        body="Body 1"
    )
    notif2 = await proactive_service.create_notification(
        type=NotificationType.CUSTOM,
        title="Test 2",
        body="Body 2"
    )
    
    # Both unread
    count = await proactive_service.get_unread_count()
    assert count == 2
    
    # Mark one as read
    await proactive_service.mark_as_read(notif1.id)
    count = await proactive_service.get_unread_count()
    assert count == 1


@pytest.mark.asyncio
async def test_mark_as_read(proactive_service):
    """Test marking a notification as read."""
    notification = await proactive_service.create_notification(
        type=NotificationType.CUSTOM,
        title="Test",
        body="Body"
    )
    
    # Initially unread
    assert notification.read_at is None
    
    # Mark as read
    success = await proactive_service.mark_as_read(notification.id)
    assert success is True
    
    # Verify it's marked as read
    notifications = await proactive_service.get_notifications()
    assert len(notifications) == 1
    assert notifications[0].read_at is not None
    
    # Try marking again (should return False since already read)
    success = await proactive_service.mark_as_read(notification.id)
    assert success is False


@pytest.mark.asyncio
async def test_mark_all_as_read(proactive_service):
    """Test marking all notifications as read."""
    # Create multiple notifications
    for i in range(3):
        await proactive_service.create_notification(
            type=NotificationType.CUSTOM,
            title=f"Test {i}",
            body=f"Body {i}"
        )
    
    # All should be unread
    count = await proactive_service.get_unread_count()
    assert count == 3
    
    # Mark all as read
    marked_count = await proactive_service.mark_all_as_read()
    assert marked_count == 3
    
    # Now zero unread
    count = await proactive_service.get_unread_count()
    assert count == 0


@pytest.mark.asyncio
async def test_delete_notification(proactive_service):
    """Test deleting a notification."""
    notification = await proactive_service.create_notification(
        type=NotificationType.CUSTOM,
        title="Test",
        body="Body"
    )
    
    # Verify it exists
    notifications = await proactive_service.get_notifications()
    assert len(notifications) == 1
    
    # Delete it
    success = await proactive_service.delete_notification(notification.id)
    assert success is True
    
    # Verify it's gone
    notifications = await proactive_service.get_notifications()
    assert len(notifications) == 0


@pytest.mark.asyncio
async def test_unread_only_filter(proactive_service):
    """Test filtering for unread notifications only."""
    notif1 = await proactive_service.create_notification(
        type=NotificationType.CUSTOM,
        title="Test 1",
        body="Body 1"
    )
    notif2 = await proactive_service.create_notification(
        type=NotificationType.CUSTOM,
        title="Test 2",
        body="Body 2"
    )
    
    # Mark one as read
    await proactive_service.mark_as_read(notif1.id)
    
    # Get only unread
    unread = await proactive_service.get_notifications(unread_only=True)
    assert len(unread) == 1
    assert unread[0].title == "Test 2"


@pytest.mark.asyncio
async def test_pagination(proactive_service):
    """Test pagination of notifications."""
    # Create 10 notifications
    for i in range(10):
        await proactive_service.create_notification(
            type=NotificationType.CUSTOM,
            title=f"Test {i}",
            body=f"Body {i}"
        )
    
    # Get first page (5 items)
    page1 = await proactive_service.get_notifications(limit=5, offset=0)
    assert len(page1) == 5
    assert page1[0].title == "Test 9"  # Most recent first
    
    # Get second page
    page2 = await proactive_service.get_notifications(limit=5, offset=5)
    assert len(page2) == 5
    assert page2[0].title == "Test 4"


@pytest.mark.asyncio
async def test_quiet_hours_detection(proactive_service):
    """Test quiet hours detection."""
    # Set quiet hours 22:00-07:00
    config = ProactiveConfig(
        quiet_hours_enabled=True,
        quiet_hours_start="22:00",
        quiet_hours_end="07:00"
    )
    proactive_service.config = config
    
    # Test at different times
    # Note: We can't control actual time, but we can test the logic
    # This is a basic structure test
    is_quiet = proactive_service.is_quiet_hours()
    assert isinstance(is_quiet, bool)
    
    # Test with disabled quiet hours
    config.quiet_hours_enabled = False
    is_quiet = proactive_service.is_quiet_hours()
    assert is_quiet is False


@pytest.mark.asyncio
async def test_config_persistence(proactive_service):
    """Test saving and loading configuration."""
    # Create custom config
    config = ProactiveConfig(
        calendar_reminder_enabled=False,
        calendar_reminder_minutes=45,
        daily_briefing_hour=9,
        quiet_hours_start="23:00"
    )
    
    # Save it
    await proactive_service.update_config(config)
    
    # Load it back
    loaded_config = await proactive_service.get_config()
    
    assert loaded_config.calendar_reminder_enabled is False
    assert loaded_config.calendar_reminder_minutes == 45
    assert loaded_config.daily_briefing_hour == 9
    assert loaded_config.quiet_hours_start == "23:00"


@pytest.mark.asyncio
async def test_notification_callback(proactive_service):
    """Test notification callback is triggered."""
    callback_called = []
    
    async def test_callback(notification):
        callback_called.append(notification.id)
    
    proactive_service.set_notification_callback(test_callback)
    
    notification = await proactive_service.create_notification(
        type=NotificationType.CUSTOM,
        title="Test",
        body="Body"
    )
    
    # Give callback time to execute
    await asyncio.sleep(0.1)
    
    assert len(callback_called) == 1
    assert callback_called[0] == notification.id


@pytest.mark.asyncio
async def test_notification_metadata(proactive_service):
    """Test notification metadata storage."""
    metadata = {
        "event_id": "evt_123",
        "source": "calendar",
        "extra_data": {"key": "value"}
    }
    
    notification = await proactive_service.create_notification(
        type=NotificationType.CALENDAR_REMINDER,
        title="Event Reminder",
        body="Meeting in 30 minutes",
        metadata=metadata
    )
    
    # Retrieve and verify metadata
    notifications = await proactive_service.get_notifications()
    assert len(notifications) == 1
    assert notifications[0].metadata == metadata


@pytest.mark.asyncio
async def test_notification_to_dict(proactive_service):
    """Test notification to_dict conversion."""
    notification = await proactive_service.create_notification(
        type=NotificationType.SYSTEM_HEALTH,
        title="Low Disk Space",
        body="Only 1GB remaining",
        priority=NotificationPriority.URGENT,
        action_url="/settings",
        metadata={"disk_free_gb": 1.0}
    )
    
    notif_dict = notification.to_dict()
    
    assert notif_dict["id"] == notification.id
    assert notif_dict["type"] == "system_health"
    assert notif_dict["title"] == "Low Disk Space"
    assert notif_dict["priority"] == "urgent"
    assert notif_dict["action_url"] == "/settings"
    assert notif_dict["metadata"]["disk_free_gb"] == 1.0


@pytest.mark.asyncio
async def test_service_start_stop(proactive_service):
    """Test starting and stopping the proactive service."""
    # Start the service
    await proactive_service.start()
    assert proactive_service._running is True
    assert proactive_service._task is not None
    
    # Stop the service
    await proactive_service.stop()
    assert proactive_service._running is False
    assert proactive_service._task is None


@pytest.mark.asyncio
async def test_priority_levels(proactive_service):
    """Test all priority levels."""
    priorities = [
        NotificationPriority.LOW,
        NotificationPriority.NORMAL,
        NotificationPriority.HIGH,
        NotificationPriority.URGENT
    ]
    
    for priority in priorities:
        notification = await proactive_service.create_notification(
            type=NotificationType.CUSTOM,
            title=f"Test {priority.value}",
            body="Body",
            priority=priority
        )
        assert notification.priority == priority


@pytest.mark.asyncio
async def test_notification_types(proactive_service):
    """Test all notification types."""
    types = [
        NotificationType.CALENDAR_REMINDER,
        NotificationType.DAILY_BRIEFING,
        NotificationType.SYSTEM_HEALTH,
        NotificationType.CUSTOM
    ]
    
    for notif_type in types:
        notification = await proactive_service.create_notification(
            type=notif_type,
            title=f"Test {notif_type.value}",
            body="Body"
        )
        assert notification.type == notif_type


@pytest.mark.asyncio
async def test_delete_nonexistent_notification(proactive_service):
    """Test deleting a notification that doesn't exist."""
    success = await proactive_service.delete_notification("notif_fake123")
    assert success is False


@pytest.mark.asyncio
async def test_mark_nonexistent_as_read(proactive_service):
    """Test marking a nonexistent notification as read."""
    success = await proactive_service.mark_as_read("notif_fake123")
    assert success is False
