"""Tests for the scheduler service and API."""
import asyncio
import json
import pytest
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from server.services.scheduler import (
    SchedulerService,
    ScheduledTask,
    TaskExecution,
    TaskType,
    TaskStatus,
    CronParser,
    init_scheduler_service,
)


# CronParser Tests

class TestCronParser:
    """Tests for cron expression parsing."""

    def test_parse_simple_expression(self):
        """Test parsing a simple cron expression."""
        result = CronParser.parse("0 7 * * *")
        assert result["minute"] == {0}
        assert result["hour"] == {7}
        assert result["day"] == set(range(1, 32))
        assert result["month"] == set(range(1, 13))
        assert result["weekday"] == set(range(0, 7))

    def test_parse_step_values(self):
        """Test parsing step values (*/n)."""
        result = CronParser.parse("*/15 * * * *")
        assert result["minute"] == {0, 15, 30, 45}

    def test_parse_range(self):
        """Test parsing range (n-m)."""
        result = CronParser.parse("0 9-17 * * *")
        assert result["hour"] == {9, 10, 11, 12, 13, 14, 15, 16, 17}

    def test_parse_list(self):
        """Test parsing list (n,m,...)."""
        result = CronParser.parse("0 8,12,18 * * *")
        assert result["hour"] == {8, 12, 18}

    def test_parse_combined(self):
        """Test parsing combined expressions."""
        result = CronParser.parse("0,30 9-17 * * 1-5")
        assert result["minute"] == {0, 30}
        assert result["hour"] == set(range(9, 18))
        assert result["weekday"] == {1, 2, 3, 4, 5}

    def test_parse_range_with_step(self):
        """Test parsing range with step (n-m/step)."""
        result = CronParser.parse("0-30/10 * * * *")
        assert result["minute"] == {0, 10, 20, 30}

    def test_invalid_field_count(self):
        """Test error on invalid field count."""
        with pytest.raises(ValueError, match="expected 5 fields"):
            CronParser.parse("* * * *")

    def test_invalid_value_out_of_range(self):
        """Test error on out of range value."""
        with pytest.raises(ValueError, match="out of range"):
            CronParser.parse("60 * * * *")

    def test_is_valid_valid_expression(self):
        """Test is_valid returns True for valid expression."""
        is_valid, error = CronParser.is_valid("0 7 * * *")
        assert is_valid is True
        assert error is None

    def test_is_valid_invalid_expression(self):
        """Test is_valid returns False for invalid expression."""
        is_valid, error = CronParser.is_valid("invalid")
        assert is_valid is False
        assert error is not None

    def test_get_next_run_daily(self):
        """Test getting next run for daily schedule."""
        # Set a fixed time for testing
        base_time = datetime(2026, 2, 4, 6, 0, 0)
        next_run = CronParser.get_next_run("0 7 * * *", base_time)
        assert next_run.hour == 7
        assert next_run.minute == 0
        assert next_run >= base_time

    def test_get_next_run_hourly(self):
        """Test getting next run for hourly schedule."""
        base_time = datetime(2026, 2, 4, 10, 30, 0)
        next_run = CronParser.get_next_run("0 * * * *", base_time)
        assert next_run.minute == 0
        assert next_run > base_time

    def test_get_next_run_every_15_minutes(self):
        """Test getting next run for every 15 minutes."""
        base_time = datetime(2026, 2, 4, 10, 10, 0)
        next_run = CronParser.get_next_run("*/15 * * * *", base_time)
        assert next_run.minute == 15
        assert next_run.hour == 10

    def test_get_next_run_weekday_only(self):
        """Test getting next run for weekday-only schedule."""
        # Find a Monday
        base_time = datetime(2026, 2, 2, 10, 0, 0)  # Monday
        next_run = CronParser.get_next_run("0 9 * * 1-5", base_time)
        assert next_run.weekday() in range(0, 5)  # Monday-Friday


# SchedulerService Tests

class TestSchedulerService:
    """Tests for the SchedulerService."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database path."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            yield Path(f.name)

    @pytest.fixture
    def service(self, temp_db):
        """Create a scheduler service instance."""
        return SchedulerService(temp_db)

    @pytest.mark.asyncio
    async def test_create_one_time_task(self, service):
        """Test creating a one-time task."""
        future_time = (datetime.now() + timedelta(hours=1)).isoformat()
        task = await service.create_task(
            name="Test Reminder",
            task_type=TaskType.ONE_TIME,
            schedule=future_time,
            action="notification",
            action_params={"title": "Test", "message": "Hello"}
        )

        assert task.id.startswith("task_")
        assert task.name == "Test Reminder"
        assert task.task_type == TaskType.ONE_TIME
        assert task.status == TaskStatus.PENDING
        assert task.next_run is not None

    @pytest.mark.asyncio
    async def test_create_recurring_task(self, service):
        """Test creating a recurring task."""
        task = await service.create_task(
            name="Daily Briefing",
            task_type=TaskType.RECURRING,
            schedule="0 7 * * *",
            action="notification",
            action_params={"title": "Morning", "message": "Good morning!"}
        )

        assert task.id.startswith("task_")
        assert task.name == "Daily Briefing"
        assert task.task_type == TaskType.RECURRING
        assert task.status == TaskStatus.PENDING
        assert task.next_run is not None

    @pytest.mark.asyncio
    async def test_create_task_invalid_schedule(self, service):
        """Test error on invalid schedule."""
        with pytest.raises(ValueError, match="Invalid datetime format"):
            await service.create_task(
                name="Bad Task",
                task_type=TaskType.ONE_TIME,
                schedule="not-a-datetime",
                action="notification",
                action_params={}
            )

    @pytest.mark.asyncio
    async def test_create_task_past_schedule(self, service):
        """Test error on past schedule for one-time task."""
        past_time = (datetime.now() - timedelta(hours=1)).isoformat()
        with pytest.raises(ValueError, match="must be in the future"):
            await service.create_task(
                name="Past Task",
                task_type=TaskType.ONE_TIME,
                schedule=past_time,
                action="notification",
                action_params={}
            )

    @pytest.mark.asyncio
    async def test_create_task_invalid_cron(self, service):
        """Test error on invalid cron expression."""
        with pytest.raises(ValueError, match="Invalid cron expression"):
            await service.create_task(
                name="Bad Cron",
                task_type=TaskType.RECURRING,
                schedule="invalid cron",
                action="notification",
                action_params={}
            )

    @pytest.mark.asyncio
    async def test_create_task_unknown_action(self, service):
        """Test error on unknown action type."""
        future_time = (datetime.now() + timedelta(hours=1)).isoformat()
        with pytest.raises(ValueError, match="Unknown action type"):
            await service.create_task(
                name="Unknown Action",
                task_type=TaskType.ONE_TIME,
                schedule=future_time,
                action="nonexistent_action",
                action_params={}
            )

    @pytest.mark.asyncio
    async def test_get_task(self, service):
        """Test getting a task by ID."""
        future_time = (datetime.now() + timedelta(hours=1)).isoformat()
        created = await service.create_task(
            name="Test Task",
            task_type=TaskType.ONE_TIME,
            schedule=future_time,
            action="log",
            action_params={"message": "Test"}
        )

        retrieved = await service.get_task(created.id)
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.name == "Test Task"

    @pytest.mark.asyncio
    async def test_get_task_not_found(self, service):
        """Test getting nonexistent task returns None."""
        result = await service.get_task("nonexistent_id")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_tasks(self, service):
        """Test listing tasks."""
        future_time = (datetime.now() + timedelta(hours=1)).isoformat()
        await service.create_task(
            name="Task 1",
            task_type=TaskType.ONE_TIME,
            schedule=future_time,
            action="log",
            action_params={}
        )
        await service.create_task(
            name="Task 2",
            task_type=TaskType.RECURRING,
            schedule="0 * * * *",
            action="log",
            action_params={}
        )

        tasks = await service.list_tasks()
        assert len(tasks) == 2

    @pytest.mark.asyncio
    async def test_list_tasks_filter_status(self, service):
        """Test listing tasks filtered by status."""
        future_time = (datetime.now() + timedelta(hours=1)).isoformat()
        await service.create_task(
            name="Pending Task",
            task_type=TaskType.ONE_TIME,
            schedule=future_time,
            action="log",
            action_params={}
        )

        tasks = await service.list_tasks(status=TaskStatus.PENDING)
        assert len(tasks) == 1
        assert tasks[0].status == TaskStatus.PENDING

        tasks = await service.list_tasks(status=TaskStatus.COMPLETED)
        assert len(tasks) == 0

    @pytest.mark.asyncio
    async def test_list_tasks_filter_enabled(self, service):
        """Test listing tasks filtered by enabled state."""
        future_time = (datetime.now() + timedelta(hours=1)).isoformat()
        task = await service.create_task(
            name="Task",
            task_type=TaskType.ONE_TIME,
            schedule=future_time,
            action="log",
            action_params={}
        )

        # Disable the task
        await service.update_task(task.id, enabled=False)

        enabled_tasks = await service.list_tasks(enabled=True)
        assert len(enabled_tasks) == 0

        disabled_tasks = await service.list_tasks(enabled=False)
        assert len(disabled_tasks) == 1

    @pytest.mark.asyncio
    async def test_update_task_name(self, service):
        """Test updating task name."""
        future_time = (datetime.now() + timedelta(hours=1)).isoformat()
        task = await service.create_task(
            name="Original Name",
            task_type=TaskType.ONE_TIME,
            schedule=future_time,
            action="log",
            action_params={}
        )

        updated = await service.update_task(task.id, name="New Name")
        assert updated.name == "New Name"

    @pytest.mark.asyncio
    async def test_update_task_schedule(self, service):
        """Test updating task schedule."""
        task = await service.create_task(
            name="Recurring Task",
            task_type=TaskType.RECURRING,
            schedule="0 7 * * *",
            action="log",
            action_params={}
        )

        updated = await service.update_task(task.id, schedule="0 8 * * *")
        assert updated.schedule == "0 8 * * *"

    @pytest.mark.asyncio
    async def test_update_task_enabled(self, service):
        """Test enabling/disabling task."""
        future_time = (datetime.now() + timedelta(hours=1)).isoformat()
        task = await service.create_task(
            name="Task",
            task_type=TaskType.ONE_TIME,
            schedule=future_time,
            action="log",
            action_params={}
        )

        # Disable
        disabled = await service.update_task(task.id, enabled=False)
        assert disabled.enabled is False
        assert disabled.status == TaskStatus.DISABLED

        # Re-enable
        enabled = await service.update_task(task.id, enabled=True)
        assert enabled.enabled is True
        assert enabled.status == TaskStatus.PENDING

    @pytest.mark.asyncio
    async def test_update_task_not_found(self, service):
        """Test updating nonexistent task returns None."""
        result = await service.update_task("nonexistent", name="New Name")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_task(self, service):
        """Test deleting a task."""
        future_time = (datetime.now() + timedelta(hours=1)).isoformat()
        task = await service.create_task(
            name="To Delete",
            task_type=TaskType.ONE_TIME,
            schedule=future_time,
            action="log",
            action_params={}
        )

        deleted = await service.delete_task(task.id)
        assert deleted is True

        # Verify it's gone
        retrieved = await service.get_task(task.id)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_delete_task_not_found(self, service):
        """Test deleting nonexistent task returns False."""
        result = await service.delete_task("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_task_history_empty(self, service):
        """Test getting history for task with no executions."""
        future_time = (datetime.now() + timedelta(hours=1)).isoformat()
        task = await service.create_task(
            name="New Task",
            task_type=TaskType.ONE_TIME,
            schedule=future_time,
            action="log",
            action_params={}
        )

        history = await service.get_task_history(task.id)
        assert len(history) == 0

    @pytest.mark.asyncio
    async def test_task_to_dict(self, service):
        """Test task to_dict method."""
        future_time = (datetime.now() + timedelta(hours=1)).isoformat()
        task = await service.create_task(
            name="Dict Task",
            task_type=TaskType.ONE_TIME,
            schedule=future_time,
            action="log",
            action_params={"message": "test"},
            metadata={"key": "value"}
        )

        d = task.to_dict()
        assert d["id"] == task.id
        assert d["name"] == "Dict Task"
        assert d["task_type"] == "one_time"
        assert d["action_params"] == {"message": "test"}
        assert d["metadata"] == {"key": "value"}

    @pytest.mark.asyncio
    async def test_register_action_handler(self, service):
        """Test registering custom action handler."""
        async def custom_handler(task):
            return {"custom": True}

        service.register_action_handler("custom_action", custom_handler)

        # Now we can create a task with this action
        future_time = (datetime.now() + timedelta(hours=1)).isoformat()
        task = await service.create_task(
            name="Custom Task",
            task_type=TaskType.ONE_TIME,
            schedule=future_time,
            action="custom_action",
            action_params={}
        )
        assert task is not None


# Action Handler Tests

class TestActionHandlers:
    """Tests for built-in action handlers."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database path."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            yield Path(f.name)

    @pytest.fixture
    def service(self, temp_db):
        """Create a scheduler service instance."""
        return SchedulerService(temp_db)

    @pytest.mark.asyncio
    async def test_log_action(self, service):
        """Test log action handler."""
        task = ScheduledTask(
            id="test_task",
            name="Log Test",
            task_type=TaskType.ONE_TIME,
            schedule=(datetime.now() + timedelta(hours=1)).isoformat(),
            action="log",
            action_params={"message": "Test log message", "level": "info"}
        )

        result = await service._handle_log(task)
        assert result["logged"] is True
        assert result["message"] == "Test log message"
        assert result["level"] == "info"

    @pytest.mark.asyncio
    async def test_notification_action(self, service):
        """Test notification action handler (mocked)."""
        task = ScheduledTask(
            id="test_task",
            name="Notification Test",
            task_type=TaskType.ONE_TIME,
            schedule=(datetime.now() + timedelta(hours=1)).isoformat(),
            action="notification",
            action_params={"title": "Test Title", "message": "Test Message"}
        )

        # Mock the subprocess call
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_process = MagicMock()
            mock_process.wait = AsyncMock(return_value=0)
            mock_exec.return_value = mock_process

            result = await service._handle_notification(task)

        assert result["delivered"] is True
        assert result["title"] == "Test Title"
        assert result["message"] == "Test Message"

    @pytest.mark.asyncio
    async def test_http_action_get(self, service):
        """Test HTTP GET action handler."""
        task = ScheduledTask(
            id="test_task",
            name="HTTP Test",
            task_type=TaskType.ONE_TIME,
            schedule=(datetime.now() + timedelta(hours=1)).isoformat(),
            action="http",
            action_params={
                "url": "https://httpbin.org/get",
                "method": "GET",
                "timeout": 10
            }
        )

        # Mock the HTTP request
        with patch("aiohttp.ClientSession") as mock_session:
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.text = AsyncMock(return_value='{"status": "ok"}')
            mock_response.headers = {"Content-Type": "application/json"}
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock(return_value=None)

            mock_session_instance = MagicMock()
            mock_session_instance.request = MagicMock(return_value=mock_response)
            mock_session_instance.__aenter__ = AsyncMock(return_value=mock_session_instance)
            mock_session_instance.__aexit__ = AsyncMock(return_value=None)

            mock_session.return_value = mock_session_instance

            result = await service._handle_http(task)

        assert result["status_code"] == 200

    @pytest.mark.asyncio
    async def test_http_action_missing_url(self, service):
        """Test HTTP action fails without URL."""
        task = ScheduledTask(
            id="test_task",
            name="HTTP Test",
            task_type=TaskType.ONE_TIME,
            schedule=(datetime.now() + timedelta(hours=1)).isoformat(),
            action="http",
            action_params={"method": "GET"}  # Missing URL
        )

        with pytest.raises(ValueError, match="requires 'url' parameter"):
            await service._handle_http(task)


# API Tests

class TestScheduleAPI:
    """Tests for the schedule API endpoints."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database path."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            yield Path(f.name)

    @pytest.fixture
    def client(self, temp_db):
        """Create a test client."""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        import server.routes.schedule as schedule_module
        import server.services.scheduler as scheduler_module

        # Reset both global singletons to ensure clean state
        schedule_module._scheduler_service = None
        scheduler_module._scheduler_service = None

        # Create a fresh service with temp db
        service = SchedulerService(temp_db)
        schedule_module._scheduler_service = service
        scheduler_module._scheduler_service = service

        app = FastAPI()
        app.include_router(schedule_module.router, prefix="/api")

        yield TestClient(app)

        # Clean up after test
        schedule_module._scheduler_service = None
        scheduler_module._scheduler_service = None

    def test_list_tasks_empty(self, client):
        """Test listing tasks when empty."""
        response = client.get("/api/schedule")
        assert response.status_code == 200
        data = response.json()
        assert data["tasks"] == []
        assert data["count"] == 0

    def test_create_task(self, client):
        """Test creating a task via API."""
        future_time = (datetime.now() + timedelta(hours=1)).isoformat()
        response = client.post("/api/schedule", json={
            "name": "API Test Task",
            "task_type": "one_time",
            "schedule": future_time,
            "action": "log",
            "action_params": {"message": "Test"}
        })

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "API Test Task"
        assert data["task_type"] == "one_time"
        assert data["status"] == "pending"
        assert "id" in data

    def test_create_recurring_task(self, client):
        """Test creating a recurring task via API."""
        response = client.post("/api/schedule", json={
            "name": "Recurring Test",
            "task_type": "recurring",
            "schedule": "0 7 * * *",
            "action": "notification",
            "action_params": {"title": "Morning", "message": "Good morning"}
        })

        assert response.status_code == 200
        data = response.json()
        assert data["task_type"] == "recurring"
        assert data["schedule"] == "0 7 * * *"

    def test_create_task_invalid_type(self, client):
        """Test error on invalid task type."""
        future_time = (datetime.now() + timedelta(hours=1)).isoformat()
        response = client.post("/api/schedule", json={
            "name": "Bad Type",
            "task_type": "invalid",
            "schedule": future_time,
            "action": "log",
            "action_params": {}
        })

        assert response.status_code == 400

    def test_create_task_invalid_schedule(self, client):
        """Test error on invalid schedule."""
        response = client.post("/api/schedule", json={
            "name": "Bad Schedule",
            "task_type": "one_time",
            "schedule": "not-a-date",
            "action": "log",
            "action_params": {}
        })

        assert response.status_code == 400

    def test_get_task(self, client):
        """Test getting a task by ID."""
        # Create a task first
        future_time = (datetime.now() + timedelta(hours=1)).isoformat()
        create_response = client.post("/api/schedule", json={
            "name": "Get Test",
            "task_type": "one_time",
            "schedule": future_time,
            "action": "log",
            "action_params": {}
        })
        task_id = create_response.json()["id"]

        # Get the task
        response = client.get(f"/api/schedule/{task_id}")
        assert response.status_code == 200
        assert response.json()["id"] == task_id

    def test_get_task_not_found(self, client):
        """Test 404 on nonexistent task."""
        response = client.get("/api/schedule/nonexistent")
        assert response.status_code == 404

    def test_update_task(self, client):
        """Test updating a task."""
        # Create a task first
        future_time = (datetime.now() + timedelta(hours=1)).isoformat()
        create_response = client.post("/api/schedule", json={
            "name": "Update Test",
            "task_type": "one_time",
            "schedule": future_time,
            "action": "log",
            "action_params": {}
        })
        task_id = create_response.json()["id"]

        # Update the task
        response = client.put(f"/api/schedule/{task_id}", json={
            "name": "Updated Name"
        })
        assert response.status_code == 200
        assert response.json()["name"] == "Updated Name"

    def test_delete_task(self, client):
        """Test deleting a task."""
        # Create a task first
        future_time = (datetime.now() + timedelta(hours=1)).isoformat()
        create_response = client.post("/api/schedule", json={
            "name": "Delete Test",
            "task_type": "one_time",
            "schedule": future_time,
            "action": "log",
            "action_params": {}
        })
        task_id = create_response.json()["id"]

        # Delete the task
        response = client.delete(f"/api/schedule/{task_id}")
        assert response.status_code == 200
        assert response.json()["deleted"] is True

        # Verify it's gone
        get_response = client.get(f"/api/schedule/{task_id}")
        assert get_response.status_code == 404

    def test_enable_disable_task(self, client):
        """Test enabling and disabling a task."""
        # Create a task first
        future_time = (datetime.now() + timedelta(hours=1)).isoformat()
        create_response = client.post("/api/schedule", json={
            "name": "Toggle Test",
            "task_type": "one_time",
            "schedule": future_time,
            "action": "log",
            "action_params": {}
        })
        task_id = create_response.json()["id"]

        # Disable
        response = client.post(f"/api/schedule/{task_id}/disable")
        assert response.status_code == 200
        assert response.json()["enabled"] is False

        # Enable
        response = client.post(f"/api/schedule/{task_id}/enable")
        assert response.status_code == 200
        assert response.json()["enabled"] is True

    def test_validate_cron(self, client):
        """Test cron validation endpoint."""
        response = client.post("/api/schedule/validate-cron", json={
            "cron": "0 7 * * *"
        })

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert len(data["next_runs"]) == 5

    def test_validate_cron_invalid(self, client):
        """Test cron validation with invalid expression."""
        response = client.post("/api/schedule/validate-cron", json={
            "cron": "invalid"
        })

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert data["error"] is not None

    def test_get_task_history(self, client):
        """Test getting task history."""
        # Create a task first
        future_time = (datetime.now() + timedelta(hours=1)).isoformat()
        create_response = client.post("/api/schedule", json={
            "name": "History Test",
            "task_type": "one_time",
            "schedule": future_time,
            "action": "log",
            "action_params": {}
        })
        task_id = create_response.json()["id"]

        # Get history (should be empty)
        response = client.get(f"/api/schedule/{task_id}/history")
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == task_id
        assert data["executions"] == []
