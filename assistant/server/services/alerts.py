"""Alert service for error monitoring and notifications.

This module provides:
- Error threshold detection (configurable errors/minute)
- Alert history stored in SQLite
- macOS notification center integration
- Optional webhook support for external alerting (Slack, Discord, etc.)
"""
import aiosqlite
import asyncio
import subprocess
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable, Optional
import aiohttp


class AlertSeverity(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertType(Enum):
    """Types of alerts the system can generate."""
    ERROR_THRESHOLD = "error_threshold"
    RATE_LIMIT = "rate_limit"
    SERVER_HEALTH = "server_health"
    DISK_SPACE = "disk_space"
    API_ERROR = "api_error"
    CUSTOM = "custom"


@dataclass
class Alert:
    """Represents an alert event."""
    id: str
    type: AlertType
    severity: AlertSeverity
    title: str
    message: str
    timestamp: str
    metadata: dict = field(default_factory=dict)
    acknowledged: bool = False
    acknowledged_at: Optional[str] = None


@dataclass
class AlertConfig:
    """Configuration for alert thresholds and behavior."""
    # Error threshold: trigger alert if > N errors in window
    error_threshold: int = 5
    error_window_seconds: int = 60

    # Rate limiting: max alerts per type per hour
    alert_rate_limit: int = 10
    alert_rate_window_seconds: int = 3600

    # Notification settings
    enable_macos_notifications: bool = True
    enable_webhook: bool = False
    webhook_url: Optional[str] = None
    webhook_timeout_seconds: float = 10.0

    # Health check thresholds
    disk_space_warning_gb: float = 5.0
    disk_space_critical_gb: float = 1.0


class AlertService:
    """Service for monitoring errors and sending alerts."""

    def __init__(self, db_path: Path, config: Optional[AlertConfig] = None):
        self.db_path = db_path
        self.config = config or AlertConfig()
        self._initialized = False

        # In-memory error tracking for threshold detection
        self._error_timestamps: deque = deque()
        self._alert_timestamps: dict[str, deque] = {}  # type -> timestamps

        # Callbacks for alert notifications
        self._notification_callbacks: list[Callable] = []

    async def _ensure_initialized(self):
        """Ensure database tables exist."""
        if self._initialized:
            return

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    title TEXT NOT NULL,
                    message TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    metadata TEXT,
                    acknowledged INTEGER DEFAULT 0,
                    acknowledged_at TEXT
                )
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_alerts_timestamp
                ON alerts(timestamp DESC)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_alerts_type
                ON alerts(type)
            """)
            await db.commit()
        self._initialized = True

    def record_error(self, error_type: str = "unknown"):
        """Record an error occurrence for threshold monitoring.

        This method is called by other services when errors occur.
        If error count exceeds threshold, an alert is triggered.
        """
        now = time.time()
        self._error_timestamps.append(now)

        # Remove old timestamps outside the window
        cutoff = now - self.config.error_window_seconds
        while self._error_timestamps and self._error_timestamps[0] < cutoff:
            self._error_timestamps.popleft()

        # Check if threshold exceeded
        if len(self._error_timestamps) > self.config.error_threshold:
            # Schedule async alert creation
            asyncio.create_task(self._trigger_error_threshold_alert(
                error_count=len(self._error_timestamps),
                error_type=error_type
            ))

    async def _trigger_error_threshold_alert(self, error_count: int, error_type: str):
        """Trigger an alert for exceeded error threshold."""
        await self.create_alert(
            alert_type=AlertType.ERROR_THRESHOLD,
            severity=AlertSeverity.ERROR,
            title="Error Threshold Exceeded",
            message=f"{error_count} errors in the last {self.config.error_window_seconds} seconds",
            metadata={"error_count": error_count, "error_type": error_type}
        )

    def _check_rate_limit(self, alert_type: str) -> bool:
        """Check if we've exceeded the alert rate limit for this type.

        Returns True if alert should be sent, False if rate limited.
        """
        now = time.time()

        if alert_type not in self._alert_timestamps:
            self._alert_timestamps[alert_type] = deque()

        timestamps = self._alert_timestamps[alert_type]

        # Remove old timestamps
        cutoff = now - self.config.alert_rate_window_seconds
        while timestamps and timestamps[0] < cutoff:
            timestamps.popleft()

        # Check limit
        if len(timestamps) >= self.config.alert_rate_limit:
            return False

        timestamps.append(now)
        return True

    async def create_alert(
        self,
        alert_type: AlertType,
        severity: AlertSeverity,
        title: str,
        message: str,
        metadata: Optional[dict] = None
    ) -> Optional[Alert]:
        """Create and store a new alert.

        Returns the created Alert, or None if rate limited.
        """
        await self._ensure_initialized()

        # Check rate limit
        if not self._check_rate_limit(alert_type.value):
            return None

        alert = Alert(
            id=f"alert_{uuid.uuid4().hex[:12]}",
            type=alert_type,
            severity=severity,
            title=title,
            message=message,
            timestamp=datetime.now().isoformat(),
            metadata=metadata or {}
        )

        # Store in database
        async with aiosqlite.connect(self.db_path) as db:
            import json
            await db.execute(
                """INSERT INTO alerts
                   (id, type, severity, title, message, timestamp, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    alert.id,
                    alert.type.value,
                    alert.severity.value,
                    alert.title,
                    alert.message,
                    alert.timestamp,
                    json.dumps(alert.metadata)
                )
            )
            await db.commit()

        # Send notifications
        await self._send_notifications(alert)

        return alert

    async def _send_notifications(self, alert: Alert):
        """Send notifications for an alert."""
        # macOS notification
        if self.config.enable_macos_notifications:
            await self._send_macos_notification(alert)

        # Webhook notification
        if self.config.enable_webhook and self.config.webhook_url:
            await self._send_webhook_notification(alert)

        # Custom callbacks
        for callback in self._notification_callbacks:
            try:
                result = callback(alert)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                pass  # Don't let callback errors break alerting

    async def _send_macos_notification(self, alert: Alert):
        """Send a macOS notification center alert."""
        try:
            # Map severity to sound
            sound_map = {
                AlertSeverity.CRITICAL: "Basso",
                AlertSeverity.ERROR: "Sosumi",
                AlertSeverity.WARNING: "Pop",
                AlertSeverity.INFO: "default"
            }
            sound = sound_map.get(alert.severity, "default")

            # Use osascript to display notification
            script = f'''
            display notification "{alert.message}" with title "Genesis: {alert.title}" sound name "{sound}"
            '''

            process = await asyncio.create_subprocess_exec(
                "osascript", "-e", script,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            await asyncio.wait_for(process.wait(), timeout=5.0)
        except Exception:
            pass  # Notification failure shouldn't break alerting

    async def _send_webhook_notification(self, alert: Alert):
        """Send alert to webhook URL."""
        if not self.config.webhook_url:
            return

        payload = {
            "id": alert.id,
            "type": alert.type.value,
            "severity": alert.severity.value,
            "title": alert.title,
            "message": alert.message,
            "timestamp": alert.timestamp,
            "metadata": alert.metadata
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.config.webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.config.webhook_timeout_seconds)
                ) as response:
                    # Log but don't fail on non-2xx
                    if response.status >= 400:
                        pass
        except Exception:
            pass  # Webhook failure shouldn't break alerting

    def register_callback(self, callback: Callable):
        """Register a callback function to be called on new alerts."""
        self._notification_callbacks.append(callback)

    async def list_alerts(
        self,
        limit: int = 100,
        offset: int = 0,
        alert_type: Optional[AlertType] = None,
        severity: Optional[AlertSeverity] = None,
        acknowledged: Optional[bool] = None
    ) -> list[Alert]:
        """List alerts with optional filtering."""
        await self._ensure_initialized()

        query = "SELECT id, type, severity, title, message, timestamp, metadata, acknowledged, acknowledged_at FROM alerts"
        conditions = []
        params = []

        if alert_type:
            conditions.append("type = ?")
            params.append(alert_type.value)
        if severity:
            conditions.append("severity = ?")
            params.append(severity.value)
        if acknowledged is not None:
            conditions.append("acknowledged = ?")
            params.append(1 if acknowledged else 0)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        async with aiosqlite.connect(self.db_path) as db:
            import json
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()

            alerts = []
            for row in rows:
                alerts.append(Alert(
                    id=row[0],
                    type=AlertType(row[1]),
                    severity=AlertSeverity(row[2]),
                    title=row[3],
                    message=row[4],
                    timestamp=row[5],
                    metadata=json.loads(row[6]) if row[6] else {},
                    acknowledged=bool(row[7]),
                    acknowledged_at=row[8]
                ))
            return alerts

    async def get_alert(self, alert_id: str) -> Optional[Alert]:
        """Get a single alert by ID."""
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
            import json
            cursor = await db.execute(
                """SELECT id, type, severity, title, message, timestamp, metadata,
                          acknowledged, acknowledged_at
                   FROM alerts WHERE id = ?""",
                (alert_id,)
            )
            row = await cursor.fetchone()

            if not row:
                return None

            return Alert(
                id=row[0],
                type=AlertType(row[1]),
                severity=AlertSeverity(row[2]),
                title=row[3],
                message=row[4],
                timestamp=row[5],
                metadata=json.loads(row[6]) if row[6] else {},
                acknowledged=bool(row[7]),
                acknowledged_at=row[8]
            )

    async def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an alert. Returns True if successful."""
        await self._ensure_initialized()

        now = datetime.now().isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "UPDATE alerts SET acknowledged = 1, acknowledged_at = ? WHERE id = ?",
                (now, alert_id)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def get_alert_stats(self) -> dict:
        """Get alert statistics."""
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
            # Total count
            cursor = await db.execute("SELECT COUNT(*) FROM alerts")
            total = (await cursor.fetchone())[0]

            # Unacknowledged count
            cursor = await db.execute("SELECT COUNT(*) FROM alerts WHERE acknowledged = 0")
            unacknowledged = (await cursor.fetchone())[0]

            # Count by severity
            cursor = await db.execute(
                "SELECT severity, COUNT(*) FROM alerts GROUP BY severity"
            )
            by_severity = {row[0]: row[1] for row in await cursor.fetchall()}

            # Count by type
            cursor = await db.execute(
                "SELECT type, COUNT(*) FROM alerts GROUP BY type"
            )
            by_type = {row[0]: row[1] for row in await cursor.fetchall()}

            # Recent (last 24 hours)
            cursor = await db.execute(
                """SELECT COUNT(*) FROM alerts
                   WHERE datetime(timestamp) > datetime('now', '-1 day')"""
            )
            recent_24h = (await cursor.fetchone())[0]

        return {
            "total": total,
            "unacknowledged": unacknowledged,
            "by_severity": by_severity,
            "by_type": by_type,
            "recent_24h": recent_24h
        }

    async def clear_old_alerts(self, days: int = 30):
        """Delete alerts older than specified days."""
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """DELETE FROM alerts
                   WHERE datetime(timestamp) < datetime('now', ? || ' days')""",
                (f"-{days}",)
            )
            await db.commit()
            return cursor.rowcount

    def get_error_count(self) -> int:
        """Get current error count in the monitoring window."""
        now = time.time()
        cutoff = now - self.config.error_window_seconds

        # Clean old timestamps
        while self._error_timestamps and self._error_timestamps[0] < cutoff:
            self._error_timestamps.popleft()

        return len(self._error_timestamps)

    def reset(self):
        """Reset in-memory tracking (useful for testing)."""
        self._error_timestamps.clear()
        self._alert_timestamps.clear()
