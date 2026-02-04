"""Schedule API endpoints for task automation."""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

from server.services.scheduler import (
    SchedulerService, ScheduledTask, TaskType, TaskStatus,
    TaskExecution, CronParser, get_scheduler_service, init_scheduler_service
)
import config

router = APIRouter()

# Global scheduler service instance (initialized on startup)
_scheduler_service: Optional[SchedulerService] = None


def get_service() -> SchedulerService:
    """Get or create the scheduler service singleton."""
    global _scheduler_service
    if _scheduler_service is None:
        db_path = config.DATABASE_PATH.parent / "scheduler.db"
        _scheduler_service = init_scheduler_service(db_path)
    return _scheduler_service


async def init_scheduler() -> SchedulerService:
    """Initialize and start the scheduler service."""
    service = get_service()
    await service.start()
    return service


async def stop_scheduler():
    """Stop the scheduler service."""
    global _scheduler_service
    if _scheduler_service:
        await _scheduler_service.stop()


# Request/Response models

class CreateTaskRequest(BaseModel):
    """Request model for creating a scheduled task."""
    name: str = Field(..., min_length=1, max_length=100, description="Task name")
    task_type: str = Field(..., description="Task type: 'one_time' or 'recurring'")
    schedule: str = Field(
        ...,
        description="ISO datetime for one-time, cron expression for recurring"
    )
    action: str = Field(
        ...,
        description="Action type: 'notification', 'http', 'log'"
    )
    action_params: dict = Field(
        default_factory=dict,
        description="Parameters for the action"
    )
    metadata: Optional[dict] = Field(
        default=None,
        description="Optional metadata"
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "name": "Morning Briefing",
                    "task_type": "recurring",
                    "schedule": "0 7 * * *",
                    "action": "notification",
                    "action_params": {
                        "title": "Good Morning",
                        "message": "Time for your daily briefing"
                    }
                },
                {
                    "name": "API Health Check",
                    "task_type": "recurring",
                    "schedule": "*/30 * * * *",
                    "action": "http",
                    "action_params": {
                        "url": "http://127.0.0.1:8080/api/health",
                        "method": "GET"
                    }
                },
                {
                    "name": "Reminder",
                    "task_type": "one_time",
                    "schedule": "2026-02-05T15:00:00",
                    "action": "notification",
                    "action_params": {
                        "title": "Reminder",
                        "message": "Meeting in 15 minutes"
                    }
                }
            ]
        }


class UpdateTaskRequest(BaseModel):
    """Request model for updating a scheduled task."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    schedule: Optional[str] = None
    action_params: Optional[dict] = None
    enabled: Optional[bool] = None
    metadata: Optional[dict] = None


class TaskResponse(BaseModel):
    """Response model for a scheduled task."""
    id: str
    name: str
    task_type: str
    schedule: str
    action: str
    action_params: dict
    status: str
    created_at: str
    last_run: Optional[str]
    next_run: Optional[str]
    run_count: int
    error_count: int
    last_error: Optional[str]
    metadata: dict
    enabled: bool


class ExecutionResponse(BaseModel):
    """Response model for task execution."""
    id: str
    task_id: str
    started_at: str
    completed_at: Optional[str]
    status: str
    result: Optional[dict]
    error: Optional[str]
    duration_ms: Optional[int]


class ValidateCronRequest(BaseModel):
    """Request model for validating cron expression."""
    cron: str


class ValidateCronResponse(BaseModel):
    """Response model for cron validation."""
    valid: bool
    error: Optional[str]
    next_runs: Optional[list[str]] = None


def task_to_response(task: ScheduledTask) -> TaskResponse:
    """Convert ScheduledTask to TaskResponse."""
    return TaskResponse(
        id=task.id,
        name=task.name,
        task_type=task.task_type.value,
        schedule=task.schedule,
        action=task.action,
        action_params=task.action_params,
        status=task.status.value,
        created_at=task.created_at,
        last_run=task.last_run,
        next_run=task.next_run,
        run_count=task.run_count,
        error_count=task.error_count,
        last_error=task.last_error,
        metadata=task.metadata,
        enabled=task.enabled
    )


def execution_to_response(execution: TaskExecution) -> ExecutionResponse:
    """Convert TaskExecution to ExecutionResponse."""
    return ExecutionResponse(
        id=execution.id,
        task_id=execution.task_id,
        started_at=execution.started_at,
        completed_at=execution.completed_at,
        status=execution.status,
        result=execution.result,
        error=execution.error,
        duration_ms=execution.duration_ms
    )


# Endpoints

@router.get("/schedule")
async def list_tasks(
    status: Optional[str] = Query(None, description="Filter by status"),
    enabled: Optional[bool] = Query(None, description="Filter by enabled state"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
) -> dict:
    """List all scheduled tasks with optional filtering."""
    service = get_service()

    # Convert status string to enum
    task_status = None
    if status:
        try:
            task_status = TaskStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status: {status}. Valid values: {[s.value for s in TaskStatus]}"
            )

    tasks = await service.list_tasks(
        status=task_status,
        enabled=enabled,
        limit=limit,
        offset=offset
    )

    return {
        "tasks": [task_to_response(t).model_dump() for t in tasks],
        "count": len(tasks),
        "limit": limit,
        "offset": offset
    }


@router.post("/schedule")
async def create_task(request: CreateTaskRequest) -> TaskResponse:
    """Create a new scheduled task."""
    service = get_service()

    # Validate task type
    try:
        task_type = TaskType(request.task_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid task_type: {request.task_type}. Valid values: one_time, recurring"
        )

    try:
        task = await service.create_task(
            name=request.name,
            task_type=task_type,
            schedule=request.schedule,
            action=request.action,
            action_params=request.action_params,
            metadata=request.metadata
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return task_to_response(task)


@router.get("/schedule/{task_id}")
async def get_task(task_id: str) -> TaskResponse:
    """Get a specific scheduled task."""
    service = get_service()
    task = await service.get_task(task_id)

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return task_to_response(task)


@router.put("/schedule/{task_id}")
async def update_task(task_id: str, request: UpdateTaskRequest) -> TaskResponse:
    """Update an existing scheduled task."""
    service = get_service()

    try:
        task = await service.update_task(
            task_id=task_id,
            name=request.name,
            schedule=request.schedule,
            action_params=request.action_params,
            enabled=request.enabled,
            metadata=request.metadata
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return task_to_response(task)


@router.delete("/schedule/{task_id}")
async def delete_task(task_id: str) -> dict:
    """Delete a scheduled task."""
    service = get_service()
    deleted = await service.delete_task(task_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")

    return {"deleted": True, "task_id": task_id}


@router.post("/schedule/{task_id}/enable")
async def enable_task(task_id: str) -> TaskResponse:
    """Enable a disabled task."""
    service = get_service()
    task = await service.update_task(task_id, enabled=True)

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return task_to_response(task)


@router.post("/schedule/{task_id}/disable")
async def disable_task(task_id: str) -> TaskResponse:
    """Disable a task."""
    service = get_service()
    task = await service.update_task(task_id, enabled=False)

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return task_to_response(task)


@router.get("/schedule/{task_id}/history")
async def get_task_history(
    task_id: str,
    limit: int = Query(50, ge=1, le=1000)
) -> dict:
    """Get execution history for a task."""
    service = get_service()

    # First check if task exists
    task = await service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    executions = await service.get_task_history(task_id, limit=limit)

    return {
        "task_id": task_id,
        "executions": [execution_to_response(e).model_dump() for e in executions],
        "count": len(executions)
    }


@router.post("/schedule/validate-cron")
async def validate_cron(request: ValidateCronRequest) -> ValidateCronResponse:
    """Validate a cron expression and show next run times."""
    is_valid, error = CronParser.is_valid(request.cron)

    if not is_valid:
        return ValidateCronResponse(valid=False, error=error)

    # Calculate next 5 run times
    next_runs = []
    current = datetime.now()
    for _ in range(5):
        next_run = CronParser.get_next_run(request.cron, current)
        next_runs.append(next_run.isoformat())
        current = next_run

    return ValidateCronResponse(valid=True, error=None, next_runs=next_runs)
