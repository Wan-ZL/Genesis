"""Audit logging service for tool execution.

Provides append-only audit log of all tool executions for security monitoring.
"""

import logging
import sqlite3
import hashlib
import json
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class AuditLogEntry:
    """Represents an audit log entry."""
    timestamp: str
    tool_name: str
    args_hash: str
    result_summary: str
    user_ip: Optional[str]
    success: bool
    duration_ms: float
    sandboxed: bool
    rate_limited: bool


class AuditLogger:
    """Manages audit logging for tool execution."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_database()

    def _init_database(self):
        """Initialize audit log database with schema."""
        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    args_hash TEXT NOT NULL,
                    result_summary TEXT,
                    user_ip TEXT,
                    success INTEGER NOT NULL,
                    duration_ms REAL NOT NULL,
                    sandboxed INTEGER DEFAULT 0,
                    rate_limited INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create indices for common queries
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_timestamp
                ON audit_log(timestamp DESC)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_tool_name
                ON audit_log(tool_name)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_success
                ON audit_log(success)
            """)

            conn.commit()
            logger.info(f"Audit log database initialized: {self.db_path}")

        finally:
            conn.close()

    def _hash_args(self, args: Dict[str, Any]) -> str:
        """Compute SHA256 hash of arguments for privacy.

        Args:
            args: Tool arguments

        Returns:
            Hex digest of hash
        """
        # Sort keys for consistent hashing
        args_json = json.dumps(args, sort_keys=True)
        return hashlib.sha256(args_json.encode()).hexdigest()[:16]

    def _summarize_result(self, result: Any, max_length: int = 200) -> str:
        """Create brief summary of result.

        Args:
            result: Tool execution result
            max_length: Maximum summary length

        Returns:
            Result summary string
        """
        if result is None:
            return "null"

        result_str = str(result)
        if len(result_str) > max_length:
            return result_str[:max_length] + "..."
        return result_str

    def log_execution(
        self,
        tool_name: str,
        args: Dict[str, Any],
        result: Any,
        success: bool,
        duration_ms: float,
        user_ip: Optional[str] = None,
        sandboxed: bool = False,
        rate_limited: bool = False,
    ):
        """Log a tool execution to audit log.

        Args:
            tool_name: Name of the tool
            args: Tool arguments
            result: Tool execution result
            success: Whether execution succeeded
            duration_ms: Execution duration in milliseconds
            user_ip: User IP address (optional)
            sandboxed: Whether execution was sandboxed
            rate_limited: Whether rate limiting was applied
        """
        try:
            timestamp = datetime.now().isoformat()
            args_hash = self._hash_args(args)
            result_summary = self._summarize_result(result)

            conn = sqlite3.connect(str(self.db_path))
            try:
                conn.execute("""
                    INSERT INTO audit_log
                    (timestamp, tool_name, args_hash, result_summary, user_ip,
                     success, duration_ms, sandboxed, rate_limited)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    timestamp,
                    tool_name,
                    args_hash,
                    result_summary,
                    user_ip,
                    1 if success else 0,
                    duration_ms,
                    1 if sandboxed else 0,
                    1 if rate_limited else 0,
                ))
                conn.commit()

                logger.debug(
                    f"Audit log: {tool_name} "
                    f"success={success} duration={duration_ms:.1f}ms"
                )

            finally:
                conn.close()

        except Exception as e:
            # Never fail the actual operation due to audit logging errors
            logger.error(f"Failed to write audit log: {e}", exc_info=True)

    def query(
        self,
        tool_name: Optional[str] = None,
        success: Optional[bool] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditLogEntry]:
        """Query audit log entries.

        Args:
            tool_name: Filter by tool name
            success: Filter by success status
            start_time: Filter by start timestamp (ISO format)
            end_time: Filter by end timestamp (ISO format)
            limit: Maximum number of entries to return
            offset: Number of entries to skip

        Returns:
            List of audit log entries
        """
        query = "SELECT * FROM audit_log WHERE 1=1"
        params = []

        if tool_name:
            query += " AND tool_name = ?"
            params.append(tool_name)

        if success is not None:
            query += " AND success = ?"
            params.append(1 if success else 0)

        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time)

        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time)

        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()

            entries = []
            for row in rows:
                entries.append(AuditLogEntry(
                    timestamp=row[1],
                    tool_name=row[2],
                    args_hash=row[3],
                    result_summary=row[4] or "",
                    user_ip=row[5],
                    success=bool(row[6]),
                    duration_ms=row[7],
                    sandboxed=bool(row[8]) if len(row) > 8 else False,
                    rate_limited=bool(row[9]) if len(row) > 9 else False,
                ))

            return entries

        finally:
            conn.close()

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics from audit log.

        Returns:
            Dict with statistics
        """
        conn = sqlite3.connect(str(self.db_path))
        try:
            # Total executions
            cursor = conn.execute("SELECT COUNT(*) FROM audit_log")
            total = cursor.fetchone()[0]

            # Success rate
            cursor = conn.execute("SELECT COUNT(*) FROM audit_log WHERE success = 1")
            successes = cursor.fetchone()[0]

            # Most used tools
            cursor = conn.execute("""
                SELECT tool_name, COUNT(*) as count
                FROM audit_log
                GROUP BY tool_name
                ORDER BY count DESC
                LIMIT 10
            """)
            top_tools = [
                {"tool": row[0], "count": row[1]}
                for row in cursor.fetchall()
            ]

            # Recent failures
            cursor = conn.execute("""
                SELECT tool_name, COUNT(*) as count
                FROM audit_log
                WHERE success = 0
                AND timestamp >= datetime('now', '-1 hour')
                GROUP BY tool_name
                ORDER BY count DESC
            """)
            recent_failures = [
                {"tool": row[0], "count": row[1]}
                for row in cursor.fetchall()
            ]

            # Average duration by tool
            cursor = conn.execute("""
                SELECT tool_name, AVG(duration_ms) as avg_ms
                FROM audit_log
                WHERE success = 1
                GROUP BY tool_name
                ORDER BY avg_ms DESC
                LIMIT 10
            """)
            avg_durations = [
                {"tool": row[0], "avg_duration_ms": round(row[1], 2)}
                for row in cursor.fetchall()
            ]

            return {
                "total_executions": total,
                "successful_executions": successes,
                "success_rate": round(successes / total * 100, 2) if total > 0 else 0,
                "top_tools": top_tools,
                "recent_failures": recent_failures,
                "avg_durations": avg_durations,
            }

        finally:
            conn.close()


# Global instance
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger(db_path: Optional[Path] = None) -> AuditLogger:
    """Get or create the global audit logger instance."""
    global _audit_logger
    if _audit_logger is None:
        if db_path is None:
            import config
            db_path = config.BASE_DIR / "memory" / "audit.db"
        _audit_logger = AuditLogger(db_path)
    return _audit_logger
