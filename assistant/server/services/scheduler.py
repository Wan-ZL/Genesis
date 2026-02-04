"""Scheduler service for task automation.

This module provides:
- One-time and recurring scheduled tasks
- Cron-style scheduling syntax
- SQLite persistence across restarts
- Task history and logging
- Notification on task completion
"""
import asyncio
import aiosqlite
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class TaskType(Enum):
    """Type of scheduled task."""
    ONE_TIME = "one_time"
    RECURRING = "recurring"


class TaskStatus(Enum):
    """Status of a scheduled task."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DISABLED = "disabled"


@dataclass
class ScheduledTask:
    """Represents a scheduled task."""
    id: str
    name: str
    task_type: TaskType
    schedule: str  # ISO datetime for one-time, cron expression for recurring
    action: str  # Action type: "http", "notification", "eval"
    action_params: dict
    status: TaskStatus = TaskStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    run_count: int = 0
    error_count: int = 0
    last_error: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    enabled: bool = True

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "task_type": self.task_type.value,
            "schedule": self.schedule,
            "action": self.action,
            "action_params": self.action_params,
            "status": self.status.value,
            "created_at": self.created_at,
            "last_run": self.last_run,
            "next_run": self.next_run,
            "run_count": self.run_count,
            "error_count": self.error_count,
            "last_error": self.last_error,
            "metadata": self.metadata,
            "enabled": self.enabled
        }


@dataclass
class TaskExecution:
    """Record of a task execution."""
    id: str
    task_id: str
    started_at: str
    completed_at: Optional[str]
    status: str  # success, failed, timeout
    result: Optional[dict]
    error: Optional[str]
    duration_ms: Optional[int]


class CronParser:
    """Simple cron expression parser.

    Supports standard 5-field cron: minute hour day month weekday
    Special values: * (any), */n (every n), n-m (range), n,m (list)
    """

    FIELDS = ["minute", "hour", "day", "month", "weekday"]
    RANGES = {
        "minute": (0, 59),
        "hour": (0, 23),
        "day": (1, 31),
        "month": (1, 12),
        "weekday": (0, 6)  # 0 = Sunday
    }

    @classmethod
    def parse(cls, cron_expr: str) -> dict[str, set[int]]:
        """Parse a cron expression into a dictionary of valid values.

        Args:
            cron_expr: Cron expression like "0 7 * * *" (7am daily)

        Returns:
            dict mapping field names to sets of valid values
        """
        parts = cron_expr.strip().split()
        if len(parts) != 5:
            raise ValueError(f"Invalid cron expression: expected 5 fields, got {len(parts)}")

        result = {}
        for field_name, part in zip(cls.FIELDS, parts):
            min_val, max_val = cls.RANGES[field_name]
            result[field_name] = cls._parse_field(part, min_val, max_val)

        return result

    @classmethod
    def _parse_field(cls, field_str: str, min_val: int, max_val: int) -> set[int]:
        """Parse a single cron field."""
        values = set()

        for part in field_str.split(","):
            if part == "*":
                values.update(range(min_val, max_val + 1))
            elif "/" in part:
                # Step values like */5 or 0-30/5
                base, step = part.split("/")
                step = int(step)
                if base == "*":
                    start, end = min_val, max_val
                elif "-" in base:
                    start, end = map(int, base.split("-"))
                else:
                    start = int(base)
                    end = max_val
                values.update(range(start, end + 1, step))
            elif "-" in part:
                # Range like 1-5
                start, end = map(int, part.split("-"))
                values.update(range(start, end + 1))
            else:
                # Single value
                values.add(int(part))

        # Validate all values are in range
        for v in values:
            if v < min_val or v > max_val:
                raise ValueError(f"Value {v} out of range [{min_val}, {max_val}]")

        return values

    @classmethod
    def get_next_run(cls, cron_expr: str, after: Optional[datetime] = None) -> datetime:
        """Calculate the next run time for a cron expression.

        Args:
            cron_expr: Cron expression
            after: Time after which to find next run (default: now)

        Returns:
            datetime of next scheduled run
        """
        if after is None:
            after = datetime.now()

        # Start from the next minute
        current = after.replace(second=0, microsecond=0) + timedelta(minutes=1)

        parsed = cls.parse(cron_expr)

        # Search forward up to 1 year
        max_iterations = 525600  # minutes in a year

        for _ in range(max_iterations):
            if (current.minute in parsed["minute"] and
                current.hour in parsed["hour"] and
                current.day in parsed["day"] and
                current.month in parsed["month"] and
                current.weekday() in parsed["weekday"]):
                return current
            current += timedelta(minutes=1)

        raise ValueError(f"No valid run time found for cron expression: {cron_expr}")

    @classmethod
    def is_valid(cls, cron_expr: str) -> tuple[bool, Optional[str]]:
        """Validate a cron expression.

        Returns:
            (is_valid, error_message)
        """
        try:
            cls.parse(cron_expr)
            return True, None
        except ValueError as e:
            return False, str(e)


class SchedulerService:
    """Service for managing scheduled tasks."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._initialized = False
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._action_handlers: dict[str, Callable] = {}
        self._notification_callback: Optional[Callable] = None

        # Register default action handlers
        self._register_default_handlers()

    def _register_default_handlers(self):
        """Register built-in action handlers."""
        self._action_handlers["notification"] = self._handle_notification
        self._action_handlers["http"] = self._handle_http
        self._action_handlers["log"] = self._handle_log

    async def _ensure_initialized(self):
        """Ensure database tables exist."""
        if self._initialized:
            return

        async with aiosqlite.connect(self.db_path) as db:
            # Main tasks table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_tasks (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    schedule TEXT NOT NULL,
                    action TEXT NOT NULL,
                    action_params TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    last_run TEXT,
                    next_run TEXT,
                    run_count INTEGER DEFAULT 0,
                    error_count INTEGER DEFAULT 0,
                    last_error TEXT,
                    metadata TEXT,
                    enabled INTEGER DEFAULT 1
                )
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_next_run
                ON scheduled_tasks(next_run)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_status
                ON scheduled_tasks(status)
            """)

            # Task execution history
            await db.execute("""
                CREATE TABLE IF NOT EXISTS task_executions (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    status TEXT NOT NULL,
                    result TEXT,
                    error TEXT,
                    duration_ms INTEGER,
                    FOREIGN KEY (task_id) REFERENCES scheduled_tasks(id)
                )
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_executions_task_id
                ON task_executions(task_id)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_executions_started_at
                ON task_executions(started_at DESC)
            """)

            await db.commit()
        self._initialized = True

    def register_action_handler(self, action_type: str, handler: Callable):
        """Register a custom action handler.

        Handler should be an async function: handler(task: ScheduledTask) -> dict
        """
        self._action_handlers[action_type] = handler

    def set_notification_callback(self, callback: Callable):
        """Set callback for task completion notifications.

        Callback signature: callback(task: ScheduledTask, execution: TaskExecution)
        """
        self._notification_callback = callback

    async def create_task(
        self,
        name: str,
        task_type: TaskType,
        schedule: str,
        action: str,
        action_params: dict,
        metadata: Optional[dict] = None
    ) -> ScheduledTask:
        """Create a new scheduled task.

        Args:
            name: Human-readable task name
            task_type: ONE_TIME or RECURRING
            schedule: ISO datetime for one-time, cron expression for recurring
            action: Action type (notification, http, log, or custom)
            action_params: Parameters for the action
            metadata: Optional additional metadata

        Returns:
            Created ScheduledTask
        """
        await self._ensure_initialized()

        # Validate schedule
        if task_type == TaskType.ONE_TIME:
            try:
                next_run = datetime.fromisoformat(schedule)
                if next_run < datetime.now():
                    raise ValueError("One-time task schedule must be in the future")
            except ValueError as e:
                raise ValueError(f"Invalid datetime format: {e}")
        else:
            is_valid, error = CronParser.is_valid(schedule)
            if not is_valid:
                raise ValueError(f"Invalid cron expression: {error}")
            next_run = CronParser.get_next_run(schedule)

        # Validate action
        if action not in self._action_handlers:
            raise ValueError(f"Unknown action type: {action}. Available: {list(self._action_handlers.keys())}")

        task = ScheduledTask(
            id=f"task_{uuid.uuid4().hex[:12]}",
            name=name,
            task_type=task_type,
            schedule=schedule,
            action=action,
            action_params=action_params,
            next_run=next_run.isoformat(),
            metadata=metadata or {}
        )

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO scheduled_tasks
                   (id, name, task_type, schedule, action, action_params,
                    status, created_at, next_run, metadata, enabled)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task.id,
                    task.name,
                    task.task_type.value,
                    task.schedule,
                    task.action,
                    json.dumps(task.action_params),
                    task.status.value,
                    task.created_at,
                    task.next_run,
                    json.dumps(task.metadata),
                    1
                )
            )
            await db.commit()

        logger.info(f"Created scheduled task: {task.name} ({task.id})")
        return task

    async def get_task(self, task_id: str) -> Optional[ScheduledTask]:
        """Get a task by ID."""
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """SELECT id, name, task_type, schedule, action, action_params,
                          status, created_at, last_run, next_run, run_count,
                          error_count, last_error, metadata, enabled
                   FROM scheduled_tasks WHERE id = ?""",
                (task_id,)
            )
            row = await cursor.fetchone()

        if not row:
            return None

        return self._row_to_task(row)

    async def list_tasks(
        self,
        status: Optional[TaskStatus] = None,
        enabled: Optional[bool] = None,
        limit: int = 100,
        offset: int = 0
    ) -> list[ScheduledTask]:
        """List scheduled tasks with optional filtering."""
        await self._ensure_initialized()

        query = """SELECT id, name, task_type, schedule, action, action_params,
                          status, created_at, last_run, next_run, run_count,
                          error_count, last_error, metadata, enabled
                   FROM scheduled_tasks"""
        conditions = []
        params = []

        if status:
            conditions.append("status = ?")
            params.append(status.value)
        if enabled is not None:
            conditions.append("enabled = ?")
            params.append(1 if enabled else 0)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY next_run ASC NULLS LAST LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()

        return [self._row_to_task(row) for row in rows]

    async def update_task(
        self,
        task_id: str,
        name: Optional[str] = None,
        schedule: Optional[str] = None,
        action_params: Optional[dict] = None,
        enabled: Optional[bool] = None,
        metadata: Optional[dict] = None
    ) -> Optional[ScheduledTask]:
        """Update an existing task."""
        await self._ensure_initialized()

        task = await self.get_task(task_id)
        if not task:
            return None

        updates = []
        params = []

        if name is not None:
            updates.append("name = ?")
            params.append(name)

        if schedule is not None:
            # Validate new schedule
            if task.task_type == TaskType.ONE_TIME:
                try:
                    next_run = datetime.fromisoformat(schedule)
                except ValueError as e:
                    raise ValueError(f"Invalid datetime format: {e}")
            else:
                is_valid, error = CronParser.is_valid(schedule)
                if not is_valid:
                    raise ValueError(f"Invalid cron expression: {error}")
                next_run = CronParser.get_next_run(schedule)

            updates.append("schedule = ?")
            params.append(schedule)
            updates.append("next_run = ?")
            params.append(next_run.isoformat())

        if action_params is not None:
            updates.append("action_params = ?")
            params.append(json.dumps(action_params))

        if enabled is not None:
            updates.append("enabled = ?")
            params.append(1 if enabled else 0)
            if not enabled:
                updates.append("status = ?")
                params.append(TaskStatus.DISABLED.value)
            elif task.status == TaskStatus.DISABLED:
                updates.append("status = ?")
                params.append(TaskStatus.PENDING.value)

        if metadata is not None:
            updates.append("metadata = ?")
            params.append(json.dumps(metadata))

        if not updates:
            return task

        params.append(task_id)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                f"UPDATE scheduled_tasks SET {', '.join(updates)} WHERE id = ?",
                params
            )
            await db.commit()

        return await self.get_task(task_id)

    async def delete_task(self, task_id: str) -> bool:
        """Delete a task and its execution history."""
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
            # Delete executions first
            await db.execute(
                "DELETE FROM task_executions WHERE task_id = ?",
                (task_id,)
            )
            # Delete task
            cursor = await db.execute(
                "DELETE FROM scheduled_tasks WHERE id = ?",
                (task_id,)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def get_task_history(
        self,
        task_id: str,
        limit: int = 50
    ) -> list[TaskExecution]:
        """Get execution history for a task."""
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """SELECT id, task_id, started_at, completed_at, status,
                          result, error, duration_ms
                   FROM task_executions
                   WHERE task_id = ?
                   ORDER BY started_at DESC
                   LIMIT ?""",
                (task_id, limit)
            )
            rows = await cursor.fetchall()

        return [
            TaskExecution(
                id=row[0],
                task_id=row[1],
                started_at=row[2],
                completed_at=row[3],
                status=row[4],
                result=json.loads(row[5]) if row[5] else None,
                error=row[6],
                duration_ms=row[7]
            )
            for row in rows
        ]

    async def start(self):
        """Start the scheduler background task."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Scheduler started")

    async def stop(self):
        """Stop the scheduler background task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Scheduler stopped")

    async def _run_loop(self):
        """Main scheduler loop."""
        await self._ensure_initialized()

        while self._running:
            try:
                await self._check_and_run_tasks()
            except Exception as e:
                logger.error(f"Scheduler error: {e}")

            # Check every 30 seconds
            await asyncio.sleep(30)

    async def _check_and_run_tasks(self):
        """Check for tasks that need to run and execute them."""
        now = datetime.now()

        async with aiosqlite.connect(self.db_path) as db:
            # Find tasks due to run
            cursor = await db.execute(
                """SELECT id FROM scheduled_tasks
                   WHERE enabled = 1
                   AND status IN ('pending', 'completed', 'failed')
                   AND next_run IS NOT NULL
                   AND datetime(next_run) <= datetime(?)""",
                (now.isoformat(),)
            )
            rows = await cursor.fetchall()

        for (task_id,) in rows:
            task = await self.get_task(task_id)
            if task:
                asyncio.create_task(self._execute_task(task))

    async def _execute_task(self, task: ScheduledTask):
        """Execute a scheduled task."""
        execution_id = f"exec_{uuid.uuid4().hex[:12]}"
        started_at = datetime.now()

        logger.info(f"Executing task: {task.name} ({task.id})")

        # Update task status
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE scheduled_tasks SET status = ? WHERE id = ?",
                (TaskStatus.RUNNING.value, task.id)
            )
            await db.commit()

        # Execute the action
        result = None
        error = None
        status = "success"

        try:
            handler = self._action_handlers.get(task.action)
            if handler:
                result = await handler(task)
            else:
                raise ValueError(f"No handler for action: {task.action}")
        except Exception as e:
            error = str(e)
            status = "failed"
            logger.error(f"Task {task.id} failed: {e}")

        completed_at = datetime.now()
        duration_ms = int((completed_at - started_at).total_seconds() * 1000)

        # Calculate next run time
        if task.task_type == TaskType.RECURRING and task.enabled:
            next_run = CronParser.get_next_run(task.schedule, completed_at)
            next_status = TaskStatus.PENDING
        elif task.task_type == TaskType.ONE_TIME:
            next_run = None
            next_status = TaskStatus.COMPLETED if status == "success" else TaskStatus.FAILED
        else:
            next_run = None
            next_status = TaskStatus.COMPLETED if status == "success" else TaskStatus.FAILED

        # Update task
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """UPDATE scheduled_tasks
                   SET status = ?, last_run = ?, next_run = ?,
                       run_count = run_count + 1,
                       error_count = error_count + ?,
                       last_error = ?
                   WHERE id = ?""",
                (
                    next_status.value,
                    completed_at.isoformat(),
                    next_run.isoformat() if next_run else None,
                    1 if error else 0,
                    error,
                    task.id
                )
            )

            # Record execution
            await db.execute(
                """INSERT INTO task_executions
                   (id, task_id, started_at, completed_at, status, result, error, duration_ms)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    execution_id,
                    task.id,
                    started_at.isoformat(),
                    completed_at.isoformat(),
                    status,
                    json.dumps(result) if result else None,
                    error,
                    duration_ms
                )
            )
            await db.commit()

        # Notify
        if self._notification_callback:
            execution = TaskExecution(
                id=execution_id,
                task_id=task.id,
                started_at=started_at.isoformat(),
                completed_at=completed_at.isoformat(),
                status=status,
                result=result,
                error=error,
                duration_ms=duration_ms
            )
            try:
                callback_result = self._notification_callback(task, execution)
                if asyncio.iscoroutine(callback_result):
                    await callback_result
            except Exception as e:
                logger.error(f"Notification callback error: {e}")

        logger.info(f"Task {task.id} completed: {status} ({duration_ms}ms)")

    def _row_to_task(self, row) -> ScheduledTask:
        """Convert a database row to ScheduledTask."""
        return ScheduledTask(
            id=row[0],
            name=row[1],
            task_type=TaskType(row[2]),
            schedule=row[3],
            action=row[4],
            action_params=json.loads(row[5]),
            status=TaskStatus(row[6]),
            created_at=row[7],
            last_run=row[8],
            next_run=row[9],
            run_count=row[10],
            error_count=row[11],
            last_error=row[12],
            metadata=json.loads(row[13]) if row[13] else {},
            enabled=bool(row[14])
        )

    # Built-in action handlers

    async def _handle_notification(self, task: ScheduledTask) -> dict:
        """Handle notification action."""
        import subprocess

        params = task.action_params
        title = params.get("title", task.name)
        message = params.get("message", "Scheduled task completed")

        # macOS notification
        try:
            script = f'''display notification "{message}" with title "{title}"'''
            process = await asyncio.create_subprocess_exec(
                "osascript", "-e", script,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            await asyncio.wait_for(process.wait(), timeout=5.0)
        except Exception as e:
            logger.warning(f"Notification failed: {e}")

        return {"delivered": True, "title": title, "message": message}

    async def _handle_http(self, task: ScheduledTask) -> dict:
        """Handle HTTP request action."""
        import aiohttp

        params = task.action_params
        url = params.get("url")
        method = params.get("method", "GET").upper()
        headers = params.get("headers", {})
        body = params.get("body")
        timeout = params.get("timeout", 30)

        if not url:
            raise ValueError("HTTP action requires 'url' parameter")

        async with aiohttp.ClientSession() as session:
            kwargs = {
                "headers": headers,
                "timeout": aiohttp.ClientTimeout(total=timeout)
            }
            if body and method in ("POST", "PUT", "PATCH"):
                kwargs["json"] = body

            async with session.request(method, url, **kwargs) as response:
                response_body = await response.text()
                return {
                    "status_code": response.status,
                    "body": response_body[:1000],  # Truncate
                    "headers": dict(response.headers)
                }

    async def _handle_log(self, task: ScheduledTask) -> dict:
        """Handle log action (for testing/debugging)."""
        params = task.action_params
        message = params.get("message", f"Task executed: {task.name}")
        level = params.get("level", "info").lower()

        log_func = getattr(logger, level, logger.info)
        log_func(f"[Scheduled] {message}")

        return {"logged": True, "message": message, "level": level}


# Singleton instance
_scheduler_service: Optional[SchedulerService] = None


def get_scheduler_service(db_path: Optional[Path] = None) -> SchedulerService:
    """Get or create the scheduler service singleton."""
    global _scheduler_service
    if _scheduler_service is None:
        if db_path is None:
            raise ValueError("db_path required for first initialization")
        _scheduler_service = SchedulerService(db_path)
    return _scheduler_service


def init_scheduler_service(db_path: Path) -> SchedulerService:
    """Initialize the scheduler service with a specific path."""
    global _scheduler_service
    _scheduler_service = SchedulerService(db_path)
    return _scheduler_service
