"""Tests for the proactive notification system."""
import asyncio
import json
import pytest
import pytest_asyncio
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from server.services.proactive import (
    ProactiveService,
    ProactiveConfig,
    NotificationType,
    NotificationPriority,
    Notification
)


@pytest.fixture
def temp_db():
    """Create a temporary database file."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield Path(f.name)
    # Cleanup
    Path(f.name).unlink(missing_ok=True)


@pytest.fixture
def proactive_config():
    """Create a test proactive config."""
    return ProactiveConfig(
        calendar_reminder_enabled=True,
        calendar_reminder_minutes=30,
        daily_briefing_enabled=True,
        daily_briefing_hour=7,
        daily_briefing_minute=0,
        system_health_enabled=True,
        system_health_interval_minutes=60,
        quiet_hours_enabled=True,
        quiet_hours_start="22:00",
        quiet_hours_end="07:00",
        check_interval_seconds=60
    )


@pytest_asyncio.fixture
async def proactive_service(temp_db, proactive_config):
    """Create a proactive service instance for testing."""
    service = ProactiveService(temp_db)
    service.config = proactive_config
    await service._ensure_initialized()
    return service


class TestNotificationCRUD:
    """Tests for notification CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_notification(self, proactive_service):
        """Test creating a notification."""
        notification = await proactive_service.create_notification(
            type=NotificationType.CUSTOM,
            title="Test Notification",
            body="This is a test",
            priority=NotificationPriority.NORMAL
        )

        assert notification.id is not None
        assert notification.title == "Test Notification"
        assert notification.body == "This is a test"
        assert notification.type == NotificationType.CUSTOM
        assert notification.priority == NotificationPriority.NORMAL
        assert notification.read_at is None

    @pytest.mark.asyncio
    async def test_get_notifications(self, proactive_service):
        """Test retrieving notifications."""
        # Create test notifications
        await proactive_service.create_notification(
            type=NotificationType.CUSTOM,
            title="Notification 1",
            body="Body 1"
        )
        await proactive_service.create_notification(
            type=NotificationType.CUSTOM,
            title="Notification 2",
            body="Body 2"
        )

        notifications = await proactive_service.get_notifications()
        assert len(notifications) == 2
        assert notifications[0].title == "Notification 2"  # Most recent first

    @pytest.mark.asyncio
    async def test_get_unread_count(self, proactive_service):
        """Test getting unread notification count."""
        # Create notifications
        notif1 = await proactive_service.create_notification(
            type=NotificationType.CUSTOM,
            title="Unread 1",
            body="Body 1"
        )
        await proactive_service.create_notification(
            type=NotificationType.CUSTOM,
            title="Unread 2",
            body="Body 2"
        )

        # Check unread count
        count = await proactive_service.get_unread_count()
        assert count == 2

        # Mark one as read
        await proactive_service.mark_as_read(notif1.id)
        count = await proactive_service.get_unread_count()
        assert count == 1

    @pytest.mark.asyncio
    async def test_mark_as_read(self, proactive_service):
        """Test marking notification as read."""
        notification = await proactive_service.create_notification(
            type=NotificationType.CUSTOM,
            title="Test",
            body="Body"
        )

        # Mark as read
        success = await proactive_service.mark_as_read(notification.id)
        assert success is True

        # Check it's marked as read
        notifications = await proactive_service.get_notifications()
        assert notifications[0].read_at is not None

        # Try marking again (should return False - already read)
        success = await proactive_service.mark_as_read(notification.id)
        assert success is False

    @pytest.mark.asyncio
    async def test_mark_all_as_read(self, proactive_service):
        """Test marking all notifications as read."""
        await proactive_service.create_notification(
            type=NotificationType.CUSTOM,
            title="Notification 1",
            body="Body 1"
        )
        await proactive_service.create_notification(
            type=NotificationType.CUSTOM,
            title="Notification 2",
            body="Body 2"
        )

        # Mark all as read
        count = await proactive_service.mark_all_as_read()
        assert count == 2

        # Verify all are read
        unread_count = await proactive_service.get_unread_count()
        assert unread_count == 0

    @pytest.mark.asyncio
    async def test_delete_notification(self, proactive_service):
        """Test deleting a notification."""
        notification = await proactive_service.create_notification(
            type=NotificationType.CUSTOM,
            title="To Delete",
            body="Body"
        )

        # Delete notification
        success = await proactive_service.delete_notification(notification.id)
        assert success is True

        # Verify it's deleted
        notifications = await proactive_service.get_notifications()
        assert len(notifications) == 0

        # Try deleting again (should return False)
        success = await proactive_service.delete_notification(notification.id)
        assert success is False

    @pytest.mark.asyncio
    async def test_get_notifications_with_filter(self, proactive_service):
        """Test filtering notifications by unread status."""
        notif1 = await proactive_service.create_notification(
            type=NotificationType.CUSTOM,
            title="Unread",
            body="Body"
        )
        notif2 = await proactive_service.create_notification(
            type=NotificationType.CUSTOM,
            title="Read",
            body="Body"
        )

        # Mark one as read
        await proactive_service.mark_as_read(notif2.id)

        # Get unread only
        unread = await proactive_service.get_notifications(unread_only=True)
        assert len(unread) == 1
        assert unread[0].id == notif1.id

        # Get all
        all_notifs = await proactive_service.get_notifications(unread_only=False)
        assert len(all_notifs) == 2


class TestProactiveConfig:
    """Tests for proactive configuration."""

    @pytest.mark.asyncio
    async def test_get_default_config(self, proactive_service):
        """Test getting default configuration."""
        config = await proactive_service.get_config()
        assert config.calendar_reminder_enabled is True
        assert config.daily_briefing_enabled is True
        assert config.system_health_enabled is True

    @pytest.mark.asyncio
    async def test_update_config(self, proactive_service):
        """Test updating configuration."""
        new_config = ProactiveConfig(
            calendar_reminder_enabled=False,
            calendar_reminder_minutes=15,
            daily_briefing_hour=8
        )

        await proactive_service.update_config(new_config)

        # Verify config was updated
        saved_config = await proactive_service.get_config()
        assert saved_config.calendar_reminder_enabled is False
        assert saved_config.calendar_reminder_minutes == 15
        assert saved_config.daily_briefing_hour == 8

    @pytest.mark.asyncio
    async def test_config_persistence(self, temp_db):
        """Test that config persists across service restarts."""
        # Create service and update config
        service1 = ProactiveService(temp_db)
        await service1._ensure_initialized()

        new_config = ProactiveConfig(
            calendar_reminder_minutes=45,
            quiet_hours_start="23:00"
        )
        await service1.update_config(new_config)

        # Create new service instance (simulating restart)
        service2 = ProactiveService(temp_db)
        await service2._ensure_initialized()
        loaded_config = await service2.get_config()

        # Verify config was loaded
        assert loaded_config.calendar_reminder_minutes == 45
        assert loaded_config.quiet_hours_start == "23:00"


class TestQuietHours:
    """Tests for quiet hours functionality."""

    @pytest.mark.asyncio
    async def test_is_quiet_hours_disabled(self, proactive_service):
        """Test quiet hours when disabled."""
        proactive_service.config.quiet_hours_enabled = False
        assert proactive_service.is_quiet_hours() is False

    @pytest.mark.asyncio
    async def test_is_quiet_hours_daytime(self, proactive_service):
        """Test quiet hours during daytime."""
        # Set quiet hours 22:00 to 07:00
        proactive_service.config.quiet_hours_start = "22:00"
        proactive_service.config.quiet_hours_end = "07:00"

        # Mock current time to 12:00 (daytime)
        with patch('server.services.proactive.datetime') as mock_dt:
            mock_dt.now.return_value.time.return_value = datetime.strptime("12:00", "%H:%M").time()
            mock_dt.strptime = datetime.strptime
            assert proactive_service.is_quiet_hours() is False

    @pytest.mark.asyncio
    async def test_is_quiet_hours_nighttime(self, proactive_service):
        """Test quiet hours during nighttime."""
        # Set quiet hours 22:00 to 07:00
        proactive_service.config.quiet_hours_start = "22:00"
        proactive_service.config.quiet_hours_end = "07:00"

        # Mock current time to 23:00 (nighttime)
        with patch('server.services.proactive.datetime') as mock_dt:
            mock_dt.now.return_value.time.return_value = datetime.strptime("23:00", "%H:%M").time()
            mock_dt.strptime = datetime.strptime
            assert proactive_service.is_quiet_hours() is True

    @pytest.mark.asyncio
    async def test_is_quiet_hours_early_morning(self, proactive_service):
        """Test quiet hours in early morning."""
        # Set quiet hours 22:00 to 07:00
        proactive_service.config.quiet_hours_start = "22:00"
        proactive_service.config.quiet_hours_end = "07:00"

        # Mock current time to 06:00 (early morning)
        with patch('server.services.proactive.datetime') as mock_dt:
            mock_dt.now.return_value.time.return_value = datetime.strptime("06:00", "%H:%M").time()
            mock_dt.strptime = datetime.strptime
            assert proactive_service.is_quiet_hours() is True


class TestCalendarReminders:
    """Tests for calendar reminder functionality."""

    @pytest.mark.asyncio
    async def test_calendar_reminder_disabled(self, proactive_service):
        """Test calendar reminders when disabled."""
        proactive_service.config.calendar_reminder_enabled = False

        # Should not create any notifications
        await proactive_service.check_calendar_reminders()

        notifications = await proactive_service.get_notifications()
        assert len(notifications) == 0

    @pytest.mark.asyncio
    async def test_calendar_reminder_quiet_hours(self, proactive_service):
        """Test calendar reminders respect quiet hours."""
        proactive_service.config.quiet_hours_enabled = True

        # Mock quiet hours check to return True
        with patch.object(proactive_service, 'is_quiet_hours', return_value=True):
            await proactive_service.check_calendar_reminders()

        # Should not create notifications
        notifications = await proactive_service.get_notifications()
        assert len(notifications) == 0

    @pytest.mark.asyncio
    async def test_calendar_reminder_upcoming_event(self, proactive_service):
        """Test creating reminder for upcoming event."""
        # Disable quiet hours for this test
        proactive_service.config.quiet_hours_enabled = False

        # Mock calendar service
        mock_event = MagicMock()
        mock_event.event_id = "test_event_1"
        mock_event.title = "Team Meeting"
        mock_event.location = "Room 101"
        mock_event.start = datetime.now() + timedelta(minutes=25)

        mock_calendar_svc = MagicMock()
        mock_calendar_svc.is_available = True
        mock_calendar_svc.is_configured = True
        mock_calendar_svc.list_events = AsyncMock(return_value=[mock_event])

        with patch('server.services.calendar.get_calendar_service', return_value=mock_calendar_svc):
            await proactive_service.check_calendar_reminders()

        # Should create a notification
        notifications = await proactive_service.get_notifications()
        assert len(notifications) == 1
        assert notifications[0].type == NotificationType.CALENDAR_REMINDER
        assert "Team Meeting" in notifications[0].title
        assert "Room 101" in notifications[0].body

    @pytest.mark.asyncio
    async def test_calendar_reminder_no_duplicate(self, proactive_service):
        """Test no duplicate reminders for same event."""
        # Disable quiet hours for this test
        proactive_service.config.quiet_hours_enabled = False

        # Mock calendar service
        mock_event = MagicMock()
        mock_event.event_id = "test_event_1"
        mock_event.title = "Team Meeting"
        mock_event.start = datetime.now() + timedelta(minutes=25)

        mock_calendar_svc = MagicMock()
        mock_calendar_svc.is_available = True
        mock_calendar_svc.is_configured = True
        mock_calendar_svc.list_events = AsyncMock(return_value=[mock_event])

        with patch('server.services.calendar.get_calendar_service', return_value=mock_calendar_svc):
            # First check - should create notification
            await proactive_service.check_calendar_reminders()
            notifications = await proactive_service.get_notifications()
            assert len(notifications) == 1

            # Second check - should not create duplicate
            await proactive_service.check_calendar_reminders()
            notifications = await proactive_service.get_notifications()
            assert len(notifications) == 1


class TestDailyBriefing:
    """Tests for daily briefing functionality."""

    @pytest.mark.asyncio
    async def test_daily_briefing_disabled(self, proactive_service):
        """Test daily briefing when disabled."""
        proactive_service.config.daily_briefing_enabled = False

        await proactive_service.check_daily_briefing()

        notifications = await proactive_service.get_notifications()
        assert len(notifications) == 0

    @pytest.mark.asyncio
    async def test_daily_briefing_wrong_time(self, proactive_service):
        """Test daily briefing at wrong time."""
        proactive_service.config.daily_briefing_hour = 7
        proactive_service.config.daily_briefing_minute = 0

        # Mock current time to 12:00 (not briefing time)
        with patch('server.services.proactive.datetime') as mock_dt:
            mock_dt.now.return_value = datetime.strptime("2024-01-01 12:00:00", "%Y-%m-%d %H:%M:%S")
            await proactive_service.check_daily_briefing()

        # Should not create notification
        notifications = await proactive_service.get_notifications()
        assert len(notifications) == 0

    @pytest.mark.asyncio
    async def test_daily_briefing_already_sent_today(self, proactive_service):
        """Test daily briefing is only sent once per day."""
        proactive_service._last_daily_briefing = datetime.now()

        await proactive_service.check_daily_briefing()

        # Should not create notification
        notifications = await proactive_service.get_notifications()
        assert len(notifications) == 0

    @pytest.mark.asyncio
    async def test_daily_briefing_with_events(self, proactive_service):
        """Test daily briefing with calendar events."""
        proactive_service.config.daily_briefing_hour = 7
        proactive_service.config.daily_briefing_minute = 0

        # Mock current time to 7:02 (within 5 min window)
        now = datetime.strptime("2024-01-01 07:02:00", "%Y-%m-%d %H:%M:%S")

        # Mock calendar events
        mock_event = MagicMock()
        mock_event.title = "Morning Standup"
        mock_event.start = now.replace(hour=9, minute=0)

        mock_calendar_svc = MagicMock()
        mock_calendar_svc.is_available = True
        mock_calendar_svc.is_configured = True
        mock_calendar_svc.list_events = AsyncMock(return_value=[mock_event])

        with patch('server.services.proactive.datetime') as mock_dt:
            mock_dt.now.return_value = now
            with patch('server.services.calendar.get_calendar_service', return_value=mock_calendar_svc):
                await proactive_service.check_daily_briefing()

        # Should create briefing notification with event info
        notifications = await proactive_service.get_notifications()
        assert len(notifications) == 1
        assert notifications[0].type == NotificationType.DAILY_BRIEFING
        assert "Morning Standup" in notifications[0].body


class TestSystemHealth:
    """Tests for system health check functionality."""

    @pytest.mark.asyncio
    async def test_system_health_disabled(self, proactive_service):
        """Test system health when disabled."""
        proactive_service.config.system_health_enabled = False

        await proactive_service.check_system_health()

        notifications = await proactive_service.get_notifications()
        assert len(notifications) == 0

    @pytest.mark.asyncio
    async def test_system_health_too_soon(self, proactive_service):
        """Test system health check interval."""
        proactive_service.config.system_health_interval_minutes = 60
        proactive_service._last_health_check = datetime.now() - timedelta(minutes=30)

        await proactive_service.check_system_health()

        # Should not create notification (too soon)
        notifications = await proactive_service.get_notifications()
        assert len(notifications) == 0

    @pytest.mark.asyncio
    async def test_system_health_warning(self, proactive_service):
        """Test system health warning alert."""
        from server.services.resources import ResourceSnapshot, ResourceStatus

        # Disable quiet hours for this test
        proactive_service.config.quiet_hours_enabled = False

        # Mock resource service with warning status
        mock_snapshot = ResourceSnapshot(
            timestamp=datetime.now().isoformat(),
            memory={"status": "warning"},
            cpu={"status": "healthy"},
            disk={"status": "healthy"},
            status=ResourceStatus.WARNING,
            warnings=["Memory usage warning: 400MB / 512MB"]
        )

        mock_resource_svc = MagicMock()
        mock_resource_svc.get_snapshot.return_value = mock_snapshot

        with patch('server.services.resources.get_resource_service', return_value=mock_resource_svc):
            await proactive_service.check_system_health()

        # Should create warning notification
        notifications = await proactive_service.get_notifications()
        assert len(notifications) == 1
        assert notifications[0].type == NotificationType.SYSTEM_HEALTH
        assert notifications[0].priority == NotificationPriority.HIGH

    @pytest.mark.asyncio
    async def test_system_health_critical(self, proactive_service):
        """Test system health critical alert."""
        from server.services.resources import ResourceSnapshot, ResourceStatus

        # Disable quiet hours for this test
        proactive_service.config.quiet_hours_enabled = False

        # Mock resource service with critical status
        mock_snapshot = ResourceSnapshot(
            timestamp=datetime.now().isoformat(),
            memory={"status": "critical"},
            cpu={"status": "healthy"},
            disk={"status": "critical"},
            status=ResourceStatus.CRITICAL,
            warnings=["Memory usage critical: 480MB / 512MB", "Disk space critical: 0.5GB free"]
        )

        mock_resource_svc = MagicMock()
        mock_resource_svc.get_snapshot.return_value = mock_snapshot

        with patch('server.services.resources.get_resource_service', return_value=mock_resource_svc):
            await proactive_service.check_system_health()

        # Should create urgent notification
        notifications = await proactive_service.get_notifications()
        assert len(notifications) == 1
        assert notifications[0].type == NotificationType.SYSTEM_HEALTH
        assert notifications[0].priority == NotificationPriority.URGENT


class TestNotificationCallback:
    """Tests for notification callback functionality."""

    @pytest.mark.asyncio
    async def test_notification_callback(self, proactive_service):
        """Test that notification callback is triggered."""
        callback_called = []

        async def mock_callback(notification):
            callback_called.append(notification)

        proactive_service.set_notification_callback(mock_callback)

        await proactive_service.create_notification(
            type=NotificationType.CUSTOM,
            title="Test",
            body="Body"
        )

        # Callback should have been called
        assert len(callback_called) == 1
        assert callback_called[0].title == "Test"

    @pytest.mark.asyncio
    async def test_notification_callback_error_handling(self, proactive_service):
        """Test callback error doesn't break notification creation."""
        async def failing_callback(notification):
            raise Exception("Callback error")

        proactive_service.set_notification_callback(failing_callback)

        # Should still create notification despite callback error
        notification = await proactive_service.create_notification(
            type=NotificationType.CUSTOM,
            title="Test",
            body="Body"
        )

        assert notification.id is not None


class TestBackgroundService:
    """Tests for background service functionality."""

    @pytest.mark.asyncio
    async def test_start_stop_service(self, proactive_service):
        """Test starting and stopping the background service."""
        assert proactive_service._running is False

        await proactive_service.start()
        assert proactive_service._running is True
        assert proactive_service._task is not None

        await proactive_service.stop()
        assert proactive_service._running is False

    @pytest.mark.asyncio
    async def test_run_all_checks(self, proactive_service):
        """Test running all proactive checks."""
        # Mock all check methods to track they were called
        with patch.object(proactive_service, 'check_calendar_reminders', new=AsyncMock()) as mock_calendar, \
             patch.object(proactive_service, 'check_daily_briefing', new=AsyncMock()) as mock_briefing, \
             patch.object(proactive_service, 'check_system_health', new=AsyncMock()) as mock_health:

            await proactive_service.run_all_checks()

            # All checks should have been called
            mock_calendar.assert_called_once()
            mock_briefing.assert_called_once()
            mock_health.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_all_checks_error_handling(self, proactive_service):
        """Test that errors in individual checks don't break run_all_checks."""
        # Mock one check to fail
        with patch.object(proactive_service, 'check_calendar_reminders', side_effect=Exception("Calendar error")), \
             patch.object(proactive_service, 'check_daily_briefing', new=AsyncMock()) as mock_briefing:

            # Should not raise exception
            await proactive_service.run_all_checks()

            # Other checks should still run
            mock_briefing.assert_called_once()
