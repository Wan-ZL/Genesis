"""Proactive service for the Heartbeat Engine.

This module provides:
- Periodic background checks for notifications
- Calendar reminders (upcoming events)
- Daily briefing (morning summary)
- System health alerts
- Configurable quiet hours
"""
import asyncio
import aiosqlite
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, time as dt_time
from enum import Enum
from pathlib import Path
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class NotificationType(Enum):
    """Type of notification."""
    CALENDAR_REMINDER = "calendar_reminder"
    DAILY_BRIEFING = "daily_briefing"
    SYSTEM_HEALTH = "system_health"
    CUSTOM = "custom"


class NotificationPriority(Enum):
    """Priority level of notification."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


@dataclass
class Notification:
    """Represents a notification."""
    id: str
    type: NotificationType
    title: str
    body: str
    priority: NotificationPriority = NotificationPriority.NORMAL
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    read_at: Optional[str] = None
    action_url: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "type": self.type.value,
            "title": self.title,
            "body": self.body,
            "priority": self.priority.value,
            "created_at": self.created_at,
            "read_at": self.read_at,
            "action_url": self.action_url,
            "metadata": self.metadata
        }


@dataclass
class ProactiveConfig:
    """Configuration for proactive checks."""
    # Calendar reminders
    calendar_reminder_enabled: bool = True
    calendar_reminder_minutes: int = 30  # Remind 30 minutes before event

    # Daily briefing
    daily_briefing_enabled: bool = True
    daily_briefing_hour: int = 7  # 7am
    daily_briefing_minute: int = 0

    # System health
    system_health_enabled: bool = True
    system_health_interval_minutes: int = 60  # Check every hour

    # Quiet hours
    quiet_hours_enabled: bool = True
    quiet_hours_start: str = "22:00"  # 10pm
    quiet_hours_end: str = "07:00"  # 7am

    # Check intervals
    check_interval_seconds: int = 60  # Run checks every 60 seconds


class ProactiveService:
    """Service for proactive notifications and background checks."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._initialized = False
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self.config = ProactiveConfig()
        self._last_daily_briefing: Optional[datetime] = None
        self._last_health_check: Optional[datetime] = None
        self._notified_event_ids: set = set()  # Track events we've already notified about

        # Callback for new notifications (can be used to push to frontend)
        self._notification_callback: Optional[Callable] = None

    async def _ensure_initialized(self):
        """Ensure database tables exist."""
        if self._initialized:
            return

        async with aiosqlite.connect(self.db_path) as db:
            # Enable WAL mode for better concurrency
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA busy_timeout=5000")

            # Notifications table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS notifications (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    priority TEXT NOT NULL DEFAULT 'normal',
                    created_at TEXT NOT NULL,
                    read_at TEXT,
                    action_url TEXT,
                    metadata TEXT
                )
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_notifications_created_at
                ON notifications(created_at DESC)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_notifications_read_at
                ON notifications(read_at)
            """)

            # Proactive config table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS proactive_config (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            await db.commit()
        self._initialized = True

    def set_notification_callback(self, callback: Callable):
        """Set callback for new notifications.

        Callback signature: async callback(notification: Notification)
        """
        self._notification_callback = callback

    async def create_notification(
        self,
        type: NotificationType,
        title: str,
        body: str,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        action_url: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> Notification:
        """Create a new notification."""
        await self._ensure_initialized()

        notification = Notification(
            id=f"notif_{uuid.uuid4().hex[:12]}",
            type=type,
            title=title,
            body=body,
            priority=priority,
            action_url=action_url,
            metadata=metadata or {}
        )

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO notifications
                   (id, type, title, body, priority, created_at, action_url, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    notification.id,
                    notification.type.value,
                    notification.title,
                    notification.body,
                    notification.priority.value,
                    notification.created_at,
                    notification.action_url,
                    json.dumps(notification.metadata)
                )
            )
            await db.commit()

        logger.info(f"Created notification: {notification.title} ({notification.id})")

        # Trigger callback
        if self._notification_callback:
            try:
                await self._notification_callback(notification)
            except Exception as e:
                logger.error(f"Notification callback error: {e}")

        return notification

    async def get_notifications(
        self,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0
    ) -> list[Notification]:
        """Get notifications."""
        await self._ensure_initialized()

        query = """SELECT id, type, title, body, priority, created_at, read_at, action_url, metadata
                   FROM notifications"""

        params = []
        if unread_only:
            query += " WHERE read_at IS NULL"

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()

        return [self._row_to_notification(row) for row in rows]

    async def get_unread_count(self) -> int:
        """Get count of unread notifications."""
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM notifications WHERE read_at IS NULL"
            )
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def mark_as_read(self, notification_id: str) -> bool:
        """Mark a notification as read."""
        await self._ensure_initialized()

        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "UPDATE notifications SET read_at = ? WHERE id = ? AND read_at IS NULL",
                (now, notification_id)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def mark_all_as_read(self) -> int:
        """Mark all notifications as read."""
        await self._ensure_initialized()

        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "UPDATE notifications SET read_at = ? WHERE read_at IS NULL",
                (now,)
            )
            await db.commit()
            return cursor.rowcount

    async def delete_notification(self, notification_id: str) -> bool:
        """Delete a notification."""
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM notifications WHERE id = ?",
                (notification_id,)
            )
            await db.commit()
            return cursor.rowcount > 0

    def _row_to_notification(self, row) -> Notification:
        """Convert database row to Notification."""
        return Notification(
            id=row[0],
            type=NotificationType(row[1]),
            title=row[2],
            body=row[3],
            priority=NotificationPriority(row[4]),
            created_at=row[5],
            read_at=row[6],
            action_url=row[7],
            metadata=json.loads(row[8]) if row[8] else {}
        )

    # Configuration methods

    async def get_config(self) -> ProactiveConfig:
        """Get proactive configuration."""
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT key, value FROM proactive_config")
            rows = await cursor.fetchall()

        config_dict = dict(rows)

        # Apply saved config to default config
        config = ProactiveConfig()
        for key, value in config_dict.items():
            if hasattr(config, key):
                # Parse boolean values
                if isinstance(getattr(config, key), bool):
                    setattr(config, key, value.lower() == "true")
                # Parse integer values
                elif isinstance(getattr(config, key), int):
                    setattr(config, key, int(value))
                # String values
                else:
                    setattr(config, key, value)

        self.config = config
        return config

    async def update_config(self, config: ProactiveConfig):
        """Update proactive configuration."""
        await self._ensure_initialized()

        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            for key, value in vars(config).items():
                await db.execute(
                    """INSERT INTO proactive_config (key, value, updated_at)
                       VALUES (?, ?, ?)
                       ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = ?""",
                    (key, str(value), now, str(value), now)
                )
            await db.commit()

        self.config = config
        logger.info("Updated proactive configuration")

    # Background check methods

    def is_quiet_hours(self) -> bool:
        """Check if currently in quiet hours."""
        if not self.config.quiet_hours_enabled:
            return False

        now = datetime.now().time()
        start_time = datetime.strptime(self.config.quiet_hours_start, "%H:%M").time()
        end_time = datetime.strptime(self.config.quiet_hours_end, "%H:%M").time()

        # Handle overnight quiet hours (e.g., 22:00 to 07:00)
        if start_time > end_time:
            return now >= start_time or now < end_time
        else:
            return start_time <= now < end_time

    async def check_calendar_reminders(self):
        """Check for upcoming calendar events and create reminders."""
        if not self.config.calendar_reminder_enabled:
            return

        if self.is_quiet_hours():
            return

        try:
            from server.services.calendar import get_calendar_service

            calendar_svc = get_calendar_service()
            if not calendar_svc.is_available or not calendar_svc.is_configured:
                return

            # Get events in the next reminder window
            now = datetime.now()
            reminder_window = timedelta(minutes=self.config.calendar_reminder_minutes)
            end_time = now + reminder_window + timedelta(minutes=5)  # Small buffer

            events = await calendar_svc.list_events(start=now, end=end_time)

            for event in events:
                # Skip if we've already notified about this event
                if event.event_id in self._notified_event_ids:
                    continue

                # Check if event starts within reminder window
                time_until = event.start - now
                if timedelta(0) < time_until <= reminder_window:
                    minutes = int(time_until.total_seconds() / 60)

                    await self.create_notification(
                        type=NotificationType.CALENDAR_REMINDER,
                        title=f"Upcoming: {event.title}",
                        body=f"Starts in {minutes} minutes" + (f" at {event.location}" if event.location else ""),
                        priority=NotificationPriority.HIGH,
                        action_url="/calendar",
                        metadata={"event_id": event.event_id, "event_start": event.start.isoformat()}
                    )

                    self._notified_event_ids.add(event.event_id)
                    logger.info(f"Created calendar reminder for event: {event.title}")

        except Exception as e:
            logger.error(f"Calendar reminder check failed: {e}")

    async def check_daily_briefing(self):
        """Check if daily briefing should be sent."""
        if not self.config.daily_briefing_enabled:
            return

        now = datetime.now()
        briefing_time = now.replace(
            hour=self.config.daily_briefing_hour,
            minute=self.config.daily_briefing_minute,
            second=0,
            microsecond=0
        )

        # Check if it's time for the briefing
        if self._last_daily_briefing and self._last_daily_briefing.date() == now.date():
            return  # Already sent today

        # Check if we're within 5 minutes of briefing time
        time_diff = abs((now - briefing_time).total_seconds())
        if time_diff > 300:  # 5 minutes
            return

        try:
            from server.services.calendar import get_calendar_service

            calendar_svc = get_calendar_service()
            if not calendar_svc.is_available or not calendar_svc.is_configured:
                # Send briefing without calendar info
                await self.create_notification(
                    type=NotificationType.DAILY_BRIEFING,
                    title="Good morning!",
                    body="Have a great day ahead!",
                    priority=NotificationPriority.NORMAL,
                    action_url="/"
                )
            else:
                # Get today's events
                today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                today_end = today_start + timedelta(days=1)
                events = await calendar_svc.list_events(start=today_start, end=today_end)

                if events:
                    event_summary = f"You have {len(events)} event{'s' if len(events) != 1 else ''} today:\n"
                    for event in events[:3]:  # Show first 3
                        event_summary += f"• {event.start.strftime('%H:%M')} - {event.title}\n"
                    if len(events) > 3:
                        event_summary += f"... and {len(events) - 3} more"
                else:
                    event_summary = "No events scheduled for today."

                await self.create_notification(
                    type=NotificationType.DAILY_BRIEFING,
                    title="Good morning! Today's schedule",
                    body=event_summary,
                    priority=NotificationPriority.NORMAL,
                    action_url="/calendar"
                )

            self._last_daily_briefing = now
            logger.info("Sent daily briefing")

        except Exception as e:
            logger.error(f"Daily briefing check failed: {e}")

    async def check_system_health(self):
        """Check system health and create alerts."""
        if not self.config.system_health_enabled:
            return

        now = datetime.now()
        if self._last_health_check:
            time_since = (now - self._last_health_check).total_seconds() / 60
            if time_since < self.config.system_health_interval_minutes:
                return

        if self.is_quiet_hours():
            self._last_health_check = now
            return

        try:
            from server.services.resources import get_resource_service

            resource_svc = get_resource_service()
            snapshot = resource_svc.get_snapshot()

            # Check for critical or warning status
            if snapshot.status.value in ("warning", "critical"):
                priority = NotificationPriority.URGENT if snapshot.status.value == "critical" else NotificationPriority.HIGH

                warnings_text = "\n".join(f"• {w}" for w in snapshot.warnings)

                await self.create_notification(
                    type=NotificationType.SYSTEM_HEALTH,
                    title=f"System Health: {snapshot.status.value.title()}",
                    body=warnings_text,
                    priority=priority,
                    action_url="/settings",
                    metadata={"status": snapshot.status.value}
                )

                logger.warning(f"Created system health alert: {snapshot.status.value}")

            self._last_health_check = now

        except Exception as e:
            logger.error(f"System health check failed: {e}")

    async def run_all_checks(self):
        """Run all proactive checks."""
        try:
            await self.check_calendar_reminders()
        except Exception as e:
            logger.error(f"Calendar reminder check error: {e}")

        try:
            await self.check_daily_briefing()
        except Exception as e:
            logger.error(f"Daily briefing check error: {e}")

        try:
            await self.check_system_health()
        except Exception as e:
            logger.error(f"System health check error: {e}")

    # Background task management

    async def start(self):
        """Start the proactive service background task."""
        if self._running:
            return

        await self._ensure_initialized()
        await self.get_config()  # Load config from DB

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Proactive service started")

    async def stop(self):
        """Stop the proactive service background task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Proactive service stopped")

    async def _run_loop(self):
        """Main proactive check loop."""
        while self._running:
            try:
                await self.run_all_checks()
            except Exception as e:
                logger.error(f"Proactive service error: {e}")

            # Sleep for configured interval
            await asyncio.sleep(self.config.check_interval_seconds)


# Singleton instance
_proactive_service: Optional[ProactiveService] = None


def get_proactive_service(db_path: Optional[Path] = None) -> ProactiveService:
    """Get or create the proactive service singleton."""
    global _proactive_service
    if _proactive_service is None:
        if db_path is None:
            raise ValueError("db_path required for first initialization")
        _proactive_service = ProactiveService(db_path)
    return _proactive_service


def init_proactive_service(db_path: Path) -> ProactiveService:
    """Initialize the proactive service with a specific path."""
    global _proactive_service
    _proactive_service = ProactiveService(db_path)
    return _proactive_service
