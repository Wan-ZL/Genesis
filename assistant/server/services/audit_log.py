"""Audit log service for tracking permission changes.

This module provides persistent logging of all permission changes
for security auditing and compliance purposes.
"""
import aiosqlite
from datetime import datetime
from pathlib import Path
from typing import Optional
import uuid


class AuditLogService:
    """Service for logging and querying permission audit events."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._initialized = False

    async def _ensure_initialized(self):
        """Ensure database table exists."""
        if self._initialized:
            return

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS permission_audit_log (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    old_level INTEGER NOT NULL,
                    old_level_name TEXT NOT NULL,
                    new_level INTEGER NOT NULL,
                    new_level_name TEXT NOT NULL,
                    source TEXT NOT NULL,
                    ip_address TEXT,
                    user_agent TEXT,
                    reason TEXT
                )
            """)
            # Index for fast timestamp queries
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_timestamp
                ON permission_audit_log(timestamp DESC)
            """)
            await db.commit()
        self._initialized = True

    async def log_permission_change(
        self,
        old_level: int,
        old_level_name: str,
        new_level: int,
        new_level_name: str,
        source: str = "api",
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        reason: Optional[str] = None
    ) -> str:
        """Log a permission level change.

        Args:
            old_level: Previous permission level value
            old_level_name: Previous permission level name (e.g., "LOCAL")
            new_level: New permission level value
            new_level_name: New permission level name (e.g., "SYSTEM")
            source: Source of the change ("api", "cli", "settings", "startup")
            ip_address: Client IP address (for API requests)
            user_agent: Client user agent (for API requests)
            reason: Optional reason for the change

        Returns:
            The ID of the created audit log entry
        """
        await self._ensure_initialized()

        log_id = f"audit_{uuid.uuid4().hex[:12]}"
        timestamp = datetime.now().isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO permission_audit_log
                   (id, timestamp, old_level, old_level_name, new_level, new_level_name,
                    source, ip_address, user_agent, reason)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (log_id, timestamp, old_level, old_level_name, new_level, new_level_name,
                 source, ip_address, user_agent, reason)
            )
            await db.commit()

        return log_id

    async def get_audit_log(
        self,
        limit: int = 50,
        offset: int = 0,
        source_filter: Optional[str] = None
    ) -> list[dict]:
        """Get audit log entries.

        Args:
            limit: Maximum number of entries to return (default 50)
            offset: Pagination offset (default 0)
            source_filter: Optional filter by source ("api", "cli", etc.)

        Returns:
            List of audit log entries, most recent first
        """
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
            if source_filter:
                cursor = await db.execute(
                    """SELECT id, timestamp, old_level, old_level_name,
                              new_level, new_level_name, source, ip_address,
                              user_agent, reason
                       FROM permission_audit_log
                       WHERE source = ?
                       ORDER BY timestamp DESC
                       LIMIT ? OFFSET ?""",
                    (source_filter, limit, offset)
                )
            else:
                cursor = await db.execute(
                    """SELECT id, timestamp, old_level, old_level_name,
                              new_level, new_level_name, source, ip_address,
                              user_agent, reason
                       FROM permission_audit_log
                       ORDER BY timestamp DESC
                       LIMIT ? OFFSET ?""",
                    (limit, offset)
                )

            rows = await cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "timestamp": row[1],
                    "old_level": row[2],
                    "old_level_name": row[3],
                    "new_level": row[4],
                    "new_level_name": row[5],
                    "source": row[6],
                    "ip_address": row[7],
                    "user_agent": row[8],
                    "reason": row[9],
                    "change": f"{row[3]} ({row[2]}) -> {row[5]} ({row[4]})"
                }
                for row in rows
            ]

    async def get_audit_count(self, source_filter: Optional[str] = None) -> int:
        """Get total count of audit log entries.

        Args:
            source_filter: Optional filter by source

        Returns:
            Total number of audit log entries
        """
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
            if source_filter:
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM permission_audit_log WHERE source = ?",
                    (source_filter,)
                )
            else:
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM permission_audit_log"
                )
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def get_latest_change(self) -> Optional[dict]:
        """Get the most recent permission change.

        Returns:
            Most recent audit log entry or None
        """
        entries = await self.get_audit_log(limit=1)
        return entries[0] if entries else None

    async def clear_audit_log(self):
        """Clear all audit log entries.

        WARNING: This is destructive. Use only for testing or explicit user request.
        """
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM permission_audit_log")
            await db.commit()
