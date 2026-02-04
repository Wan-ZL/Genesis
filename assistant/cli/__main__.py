"""CLI entry point for AI Assistant.

Usage:
    python -m assistant.cli export --output conversation.json
    python -m assistant.cli import --input conversation.json
    python -m assistant.cli import --input conversation.json --mode replace
    python -m assistant.cli alerts list
    python -m assistant.cli alerts list --severity error --limit 50
    python -m assistant.cli alerts stats
    python -m assistant.cli backup create --output backup.tar.gz
    python -m assistant.cli backup restore --input backup.tar.gz
    python -m assistant.cli backup list
    python -m assistant.cli backup verify --input backup.tar.gz
    python -m assistant.cli resources
    python -m assistant.cli resources --json
    python -m assistant.cli resources cleanup --dry-run
    python -m assistant.cli resources cleanup memory
    python -m assistant.cli logs tail
    python -m assistant.cli logs tail --name error --lines 100
    python -m assistant.cli logs clear --name assistant --confirm
    python -m assistant.cli logs list
    python -m assistant.cli logs cleanup --dry-run
    python -m assistant.cli schedule list
    python -m assistant.cli schedule add --name "Morning Briefing" --type recurring --schedule "0 7 * * *" --action notification --params '{"title":"Good Morning"}'
    python -m assistant.cli schedule add --name "Reminder" --type one_time --schedule "2026-02-05T15:00:00" --action notification --params '{"message":"Meeting soon"}'
    python -m assistant.cli schedule remove <task_id>
    python -m assistant.cli schedule enable <task_id>
    python -m assistant.cli schedule disable <task_id>
    python -m assistant.cli schedule history <task_id>
    python -m assistant.cli settings encrypt
    python -m assistant.cli settings status
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from server.services.memory import MemoryService
from server.services.alerts import AlertService, AlertSeverity, AlertType
from server.services.backup import BackupService, BackupStatus
from server.services.resources import ResourceService, ResourceConfig
from server.services.logging_service import LogConfig, LoggingService, get_logging_service
from server.services.scheduler import (
    SchedulerService, TaskType, TaskStatus, CronParser, init_scheduler_service
)
from server.services.settings import SettingsService
import config


async def export_command(args):
    """Export conversation to JSON file."""
    memory = MemoryService(config.DATABASE_PATH)

    export_data = await memory.export_conversation()

    # Write to file or stdout
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(json.dumps(export_data, indent=2))
        print(f"Exported {export_data['message_count']} messages to {output_path}")
    else:
        print(json.dumps(export_data, indent=2))


async def import_command(args):
    """Import conversation from JSON file."""
    memory = MemoryService(config.DATABASE_PATH)

    # Read input file
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: File not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    try:
        data = json.loads(input_path.read_text())
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    # Perform import
    try:
        result = await memory.import_conversation(data, mode=args.mode)
        print(f"Import complete:")
        print(f"  - Imported: {result['imported_count']} messages")
        print(f"  - Skipped: {result['skipped_count']} messages")
        print(f"  - Mode: {result['mode']}")
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


async def alerts_list_command(args):
    """List alerts with optional filtering."""
    db_path = config.DATABASE_PATH.parent / "alerts.db"
    service = AlertService(db_path)

    # Convert filter args to enums
    severity = AlertSeverity(args.severity) if args.severity else None
    alert_type = AlertType(args.type) if args.type else None
    acknowledged = None
    if args.acknowledged:
        acknowledged = args.acknowledged.lower() == "true"

    alerts = await service.list_alerts(
        limit=args.limit,
        offset=args.offset,
        severity=severity,
        alert_type=alert_type,
        acknowledged=acknowledged
    )

    if args.json:
        output = [
            {
                "id": a.id,
                "type": a.type.value,
                "severity": a.severity.value,
                "title": a.title,
                "message": a.message,
                "timestamp": a.timestamp,
                "acknowledged": a.acknowledged
            }
            for a in alerts
        ]
        print(json.dumps(output, indent=2))
    else:
        if not alerts:
            print("No alerts found.")
            return

        # Pretty print format
        for alert in alerts:
            severity_icon = {
                AlertSeverity.CRITICAL: "🔴",
                AlertSeverity.ERROR: "🟠",
                AlertSeverity.WARNING: "🟡",
                AlertSeverity.INFO: "🔵"
            }.get(alert.severity, "⚪")

            ack_status = "✓" if alert.acknowledged else ""
            print(f"{severity_icon} [{alert.timestamp[:16]}] {alert.title} {ack_status}")
            print(f"   {alert.message}")
            print(f"   ID: {alert.id} | Type: {alert.type.value} | Severity: {alert.severity.value}")
            print()


async def alerts_stats_command(args):
    """Show alert statistics."""
    db_path = config.DATABASE_PATH.parent / "alerts.db"
    service = AlertService(db_path)

    stats = await service.get_alert_stats()

    if args.json:
        print(json.dumps(stats, indent=2))
    else:
        print("Alert Statistics")
        print("=" * 40)
        print(f"Total alerts:       {stats['total']}")
        print(f"Unacknowledged:     {stats['unacknowledged']}")
        print(f"Last 24 hours:      {stats['recent_24h']}")
        print()
        print("By Severity:")
        for severity, count in stats.get('by_severity', {}).items():
            print(f"  {severity}: {count}")
        print()
        print("By Type:")
        for alert_type, count in stats.get('by_type', {}).items():
            print(f"  {alert_type}: {count}")


async def alerts_acknowledge_command(args):
    """Acknowledge an alert."""
    db_path = config.DATABASE_PATH.parent / "alerts.db"
    service = AlertService(db_path)

    success = await service.acknowledge_alert(args.alert_id)
    if success:
        print(f"Alert {args.alert_id} acknowledged.")
    else:
        print(f"Error: Alert {args.alert_id} not found.", file=sys.stderr)
        sys.exit(1)


async def alerts_clear_command(args):
    """Clear old alerts."""
    db_path = config.DATABASE_PATH.parent / "alerts.db"
    service = AlertService(db_path)

    deleted = await service.clear_old_alerts(args.days)
    print(f"Deleted {deleted} alerts older than {args.days} days.")


async def backup_create_command(args):
    """Create a backup of all assistant data."""
    memory_dir = config.DATABASE_PATH.parent
    service = BackupService(memory_dir, max_backups=args.keep)

    output_path = Path(args.output) if args.output else None

    print("Creating backup...")
    result = await service.create_backup(
        output_path=output_path,
        include_benchmarks=args.include_benchmarks,
    )

    if result.status == BackupStatus.SUCCESS:
        print(f"Backup created successfully: {result.output_path}")
        print(f"  Files included: {', '.join(result.metadata.files_included)}")
        print(f"  Total size: {result.metadata.total_size_bytes:,} bytes")
        print(f"  Version: {result.metadata.version}")
    elif result.status == BackupStatus.PARTIAL:
        print(f"Backup created with warnings: {result.output_path}")
        for error in result.errors:
            print(f"  Warning: {error}")
    else:
        print(f"Backup failed: {result.message}", file=sys.stderr)
        for error in result.errors:
            print(f"  Error: {error}", file=sys.stderr)
        sys.exit(1)


async def backup_restore_command(args):
    """Restore from a backup file."""
    memory_dir = config.DATABASE_PATH.parent
    service = BackupService(memory_dir)

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Backup file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    # Preview mode
    if args.preview:
        try:
            preview = await service.preview_restore(input_path)
            print("Restore Preview")
            print("=" * 40)
            print(f"Backup version: {preview.metadata.version}")
            print(f"Created at: {preview.metadata.created_at}")
            print(f"Assistant version: {preview.metadata.assistant_version}")
            print(f"Total size: {preview.total_size_bytes:,} bytes")
            print(f"Compatible: {'Yes' if preview.is_compatible else 'No'}")
            if not preview.is_compatible:
                print(f"  {preview.compatibility_message}")
            print()
            print("Files to restore:")
            for f in preview.files_to_restore:
                print(f"  {f}")
            if preview.existing_files_to_overwrite:
                print()
                print("Files that will be overwritten:")
                for f in preview.existing_files_to_overwrite:
                    print(f"  {f}")
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        return

    # Actual restore
    print("Restoring from backup...")
    result = await service.restore(input_path, force=args.force)

    if result.status == BackupStatus.SUCCESS:
        print(f"Restore completed successfully")
        print(f"  Files restored: {', '.join(result.files_restored)}")
    elif result.status == BackupStatus.PARTIAL:
        print(f"Restore completed with warnings")
        print(f"  Files restored: {', '.join(result.files_restored)}")
        for error in result.errors:
            print(f"  Warning: {error}")
    else:
        print(f"Restore failed: {result.message}", file=sys.stderr)
        for error in result.errors:
            print(f"  Error: {error}", file=sys.stderr)
        sys.exit(1)


async def backup_list_command(args):
    """List available backups."""
    memory_dir = config.DATABASE_PATH.parent
    service = BackupService(memory_dir)

    backups = await service.list_backups()

    if args.json:
        print(json.dumps(backups, indent=2))
        return

    if not backups:
        print("No backups found.")
        return

    print("Available Backups")
    print("=" * 60)
    for backup in backups:
        size_kb = backup['size_bytes'] / 1024
        created = backup.get('created_at', 'Unknown')[:16] if backup.get('created_at') else 'Unknown'
        print(f"  {backup['filename']}")
        print(f"    Created: {created} | Size: {size_kb:.1f} KB | Files: {backup['files_count']}")


async def backup_verify_command(args):
    """Verify backup integrity."""
    memory_dir = config.DATABASE_PATH.parent
    service = BackupService(memory_dir)

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Backup file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    is_valid, message = await service.verify_backup(input_path)

    if is_valid:
        print(f"Backup verified: {message}")
    else:
        print(f"Backup invalid: {message}", file=sys.stderr)
        sys.exit(1)


async def backup_schedule_command(args):
    """Show backup schedule configuration."""
    memory_dir = config.DATABASE_PATH.parent
    service = BackupService(memory_dir)

    schedule_config = await service.schedule_daily_backup(
        hour=args.hour,
        minute=args.minute,
    )

    if args.json:
        print(json.dumps(schedule_config, indent=2))
        return

    print("Backup Schedule Configuration")
    print("=" * 40)
    print(f"Schedule: Daily at {args.hour:02d}:{args.minute:02d}")
    print(f"Cron expression: {schedule_config['schedule']['cron']}")
    print()
    print("Command:")
    print(f"  {schedule_config['command']}")
    print()
    print("To enable automatic backups, add to crontab:")
    print(f"  {schedule_config['schedule']['cron']} cd {memory_dir.parent} && {schedule_config['command']}")


async def resources_command(args):
    """Show current resource usage."""
    service = ResourceService(files_path=config.FILES_PATH)
    data = service.to_dict()

    if args.json:
        print(json.dumps(data, indent=2))
        return

    # Status indicator
    status_icons = {
        "healthy": "OK",
        "warning": "WARN",
        "critical": "CRIT"
    }
    status_icon = status_icons.get(data["status"], "?")

    print("Resource Usage")
    print("=" * 50)
    print(f"Status: {status_icon} ({data['status']})")
    print()

    # Memory section
    mem = data["memory"]
    print(f"Memory:")
    print(f"  Process:  {mem['process_mb']:.1f} MB ({mem['process_percent']:.1f}% of system)")
    print(f"  System:   {mem['system_available_mb']:.0f} MB available / {mem['system_total_mb']:.0f} MB total ({mem['system_percent']:.1f}% used)")
    print(f"  Limit:    {mem['limit_mb']} MB")
    print(f"  Status:   {mem['status']}")
    print()

    # CPU section
    cpu = data["cpu"]
    print(f"CPU:")
    print(f"  Process:  {cpu['process_percent']:.1f}%")
    print(f"  System:   {cpu['system_percent']:.1f}%")
    print(f"  Cores:    {cpu['cpu_count']}")
    print(f"  Status:   {cpu['status']}")
    print()

    # Disk section
    disk = data["disk"]
    print(f"Disk:")
    print(f"  Used:     {disk['used_gb']:.1f} GB / {disk['total_gb']:.1f} GB ({disk['percent']:.1f}%)")
    print(f"  Free:     {disk['free_gb']:.1f} GB")
    print(f"  Status:   {disk['status']}")
    print()

    # Warnings
    if data["warnings"]:
        print("Warnings:")
        for warning in data["warnings"]:
            print(f"  - {warning}")
        print()

    # Limits summary
    limits = data["limits"]
    print("Configured Limits:")
    print(f"  Max memory:              {limits['max_memory_mb']} MB")
    print(f"  Max requests/minute:     {limits['max_requests_per_minute']}")
    print(f"  File max age:            {limits['file_max_age_days']} days")


async def resources_cleanup_files_command(args):
    """Clean up old files."""
    service = ResourceService(files_path=config.FILES_PATH)

    result = await service.cleanup_old_files(dry_run=args.dry_run)

    if args.json:
        print(json.dumps(result, indent=2))
        return

    action = "Would delete" if args.dry_run else "Deleted"

    if not result["deleted"]:
        print("No files to clean up.")
        return

    print(f"File Cleanup {'(DRY RUN)' if args.dry_run else ''}")
    print("=" * 50)

    for file_info in result["deleted"]:
        size_kb = file_info["size_bytes"] / 1024
        print(f"  {action}: {file_info['path']} ({size_kb:.1f} KB)")

    total_mb = result["total_bytes_freed"] / (1024 * 1024)
    print()
    print(f"Total: {len(result['deleted'])} files, {total_mb:.2f} MB")

    if result["errors"]:
        print()
        print("Errors:")
        for error in result["errors"]:
            print(f"  {error['path']}: {error['error']}")


async def resources_cleanup_memory_command(args):
    """Clean up memory."""
    service = ResourceService(files_path=config.FILES_PATH)

    result = await service.cleanup_memory()

    if args.json:
        print(json.dumps(result, indent=2))
        return

    print("Memory Cleanup")
    print("=" * 50)
    print(f"Before: {result['memory_before_mb']:.1f} MB")
    print(f"After:  {result['memory_after_mb']:.1f} MB")
    print(f"Freed:  {result['freed_mb']:.1f} MB")


def logs_tail_command(args):
    """Show last N lines of a log file (like tail -f)."""
    log_dir = config.BASE_DIR / "logs"
    log_config = LogConfig(log_dir=log_dir)
    service = LoggingService(log_config)

    lines = service.tail_log(log_name=args.name, lines=args.lines)

    if args.json:
        print(json.dumps({"lines": lines, "log_name": args.name}, indent=2))
        return

    if not lines:
        print(f"No log entries in {args.name}.log")
        return

    for line in lines:
        print(line)


def logs_list_command(args):
    """List all log files with metadata."""
    log_dir = config.BASE_DIR / "logs"
    log_config = LogConfig(log_dir=log_dir)
    service = LoggingService(log_config)

    stats = service.get_stats()

    if args.json:
        print(json.dumps(stats, indent=2))
        return

    print("Log Files")
    print("=" * 60)
    print(f"Directory: {stats['log_dir']}")
    print(f"Log level: {stats['log_level']}")
    print(f"Max file size: {stats['max_bytes'] / (1024*1024):.1f} MB")
    print(f"Backup count: {stats['backup_count']}")
    print()

    if not stats['files']:
        print("No log files found.")
        return

    print(f"Files ({stats['total_files']} total, {stats['total_size_bytes'] / 1024:.1f} KB):")
    for f in stats['files']:
        size_kb = f['size_bytes'] / 1024
        modified = f['modified_at'][:16] if f['modified_at'] else 'Unknown'
        print(f"  {f['name']:<30} {size_kb:>8.1f} KB  {modified}")


def logs_clear_command(args):
    """Clear a log file."""
    log_dir = config.BASE_DIR / "logs"
    log_config = LogConfig(log_dir=log_dir)
    service = LoggingService(log_config)

    # Confirmation check
    if not args.confirm:
        print(f"This will clear all content from {args.name}.log")
        print("Run with --confirm to proceed.")
        sys.exit(1)

    result = service.clear_log(log_name=args.name, confirm=True)

    if args.json:
        print(json.dumps(result, indent=2))
        return

    if result['success']:
        print(result['message'])
    else:
        print(f"Error: {result['message']}", file=sys.stderr)
        sys.exit(1)


def logs_cleanup_command(args):
    """Clean up old log files."""
    log_dir = config.BASE_DIR / "logs"
    log_config = LogConfig(log_dir=log_dir, max_age_days=args.days)
    service = LoggingService(log_config)

    result = service.cleanup_old_logs(dry_run=args.dry_run)

    if args.json:
        print(json.dumps(result, indent=2))
        return

    action = "Would delete" if args.dry_run else "Deleted"

    if not result["deleted"]:
        print(f"No log files older than {args.days} days found.")
        return

    print(f"Log Cleanup {'(DRY RUN)' if args.dry_run else ''}")
    print("=" * 50)
    print(f"Cutoff date: {result['cutoff_date'][:10]}")
    print()

    for file_info in result["deleted"]:
        size_kb = file_info["size_bytes"] / 1024
        print(f"  {action}: {file_info['name']} ({size_kb:.1f} KB)")

    total_kb = result["total_bytes_freed"] / 1024
    print()
    print(f"Total: {len(result['deleted'])} files, {total_kb:.1f} KB")

    if result["errors"]:
        print()
        print("Errors:")
        for error in result["errors"]:
            print(f"  {error['path']}: {error['error']}")


# Schedule commands

async def schedule_list_command(args):
    """List scheduled tasks."""
    db_path = config.DATABASE_PATH.parent / "scheduler.db"
    service = init_scheduler_service(db_path)

    # Convert filter args
    status = TaskStatus(args.status) if args.status else None
    enabled = None
    if args.enabled is not None:
        enabled = args.enabled.lower() == "true"

    tasks = await service.list_tasks(
        status=status,
        enabled=enabled,
        limit=args.limit,
        offset=args.offset
    )

    if args.json:
        print(json.dumps([t.to_dict() for t in tasks], indent=2))
        return

    if not tasks:
        print("No scheduled tasks found.")
        return

    print("Scheduled Tasks")
    print("=" * 70)

    for task in tasks:
        status_icons = {
            TaskStatus.PENDING: "PEND",
            TaskStatus.RUNNING: "RUN ",
            TaskStatus.COMPLETED: "DONE",
            TaskStatus.FAILED: "FAIL",
            TaskStatus.CANCELLED: "CANC",
            TaskStatus.DISABLED: "OFF "
        }
        status_icon = status_icons.get(task.status, "?   ")

        enabled_str = "" if task.enabled else " [disabled]"
        type_str = "cron" if task.task_type == TaskType.RECURRING else "once"

        print(f"[{status_icon}] {task.name}{enabled_str}")
        print(f"       ID: {task.id} | Type: {type_str} | Schedule: {task.schedule}")
        print(f"       Action: {task.action} | Runs: {task.run_count} | Errors: {task.error_count}")
        if task.next_run:
            print(f"       Next run: {task.next_run[:19]}")
        if task.last_run:
            print(f"       Last run: {task.last_run[:19]}")
        if task.last_error:
            print(f"       Last error: {task.last_error[:50]}")
        print()


async def schedule_add_command(args):
    """Add a new scheduled task."""
    db_path = config.DATABASE_PATH.parent / "scheduler.db"
    service = init_scheduler_service(db_path)

    # Parse action params
    try:
        action_params = json.loads(args.params) if args.params else {}
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON for --params: {e}", file=sys.stderr)
        sys.exit(1)

    # Parse task type
    try:
        task_type = TaskType(args.type)
    except ValueError:
        print(f"Error: Invalid task type: {args.type}. Use 'one_time' or 'recurring'", file=sys.stderr)
        sys.exit(1)

    try:
        task = await service.create_task(
            name=args.name,
            task_type=task_type,
            schedule=args.schedule,
            action=args.action,
            action_params=action_params,
            metadata=json.loads(args.metadata) if args.metadata else None
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(task.to_dict(), indent=2))
        return

    print(f"Task created successfully!")
    print(f"  ID: {task.id}")
    print(f"  Name: {task.name}")
    print(f"  Type: {task.task_type.value}")
    print(f"  Schedule: {task.schedule}")
    print(f"  Action: {task.action}")
    print(f"  Next run: {task.next_run}")


async def schedule_remove_command(args):
    """Remove a scheduled task."""
    db_path = config.DATABASE_PATH.parent / "scheduler.db"
    service = init_scheduler_service(db_path)

    # First check if task exists
    task = await service.get_task(args.task_id)
    if not task:
        print(f"Error: Task not found: {args.task_id}", file=sys.stderr)
        sys.exit(1)

    # Confirm deletion
    if not args.confirm:
        print(f"This will delete task: {task.name} ({task.id})")
        print(f"  Type: {task.task_type.value}")
        print(f"  Schedule: {task.schedule}")
        print(f"  Run count: {task.run_count}")
        print()
        print("Run with --confirm to proceed.")
        sys.exit(0)

    deleted = await service.delete_task(args.task_id)

    if deleted:
        print(f"Task deleted: {task.name} ({task.id})")
    else:
        print(f"Error: Failed to delete task", file=sys.stderr)
        sys.exit(1)


async def schedule_enable_command(args):
    """Enable a scheduled task."""
    db_path = config.DATABASE_PATH.parent / "scheduler.db"
    service = init_scheduler_service(db_path)

    task = await service.update_task(args.task_id, enabled=True)

    if not task:
        print(f"Error: Task not found: {args.task_id}", file=sys.stderr)
        sys.exit(1)

    print(f"Task enabled: {task.name} ({task.id})")
    print(f"  Next run: {task.next_run}")


async def schedule_disable_command(args):
    """Disable a scheduled task."""
    db_path = config.DATABASE_PATH.parent / "scheduler.db"
    service = init_scheduler_service(db_path)

    task = await service.update_task(args.task_id, enabled=False)

    if not task:
        print(f"Error: Task not found: {args.task_id}", file=sys.stderr)
        sys.exit(1)

    print(f"Task disabled: {task.name} ({task.id})")


async def schedule_history_command(args):
    """Show execution history for a task."""
    db_path = config.DATABASE_PATH.parent / "scheduler.db"
    service = init_scheduler_service(db_path)

    # First check if task exists
    task = await service.get_task(args.task_id)
    if not task:
        print(f"Error: Task not found: {args.task_id}", file=sys.stderr)
        sys.exit(1)

    executions = await service.get_task_history(args.task_id, limit=args.limit)

    if args.json:
        print(json.dumps([{
            "id": e.id,
            "started_at": e.started_at,
            "completed_at": e.completed_at,
            "status": e.status,
            "duration_ms": e.duration_ms,
            "error": e.error
        } for e in executions], indent=2))
        return

    print(f"Execution History: {task.name}")
    print("=" * 60)

    if not executions:
        print("No executions yet.")
        return

    for execution in executions:
        status_icons = {"success": "OK ", "failed": "ERR", "timeout": "TIM"}
        status_icon = status_icons.get(execution.status, "?  ")

        duration_str = f"{execution.duration_ms}ms" if execution.duration_ms else "N/A"

        print(f"[{status_icon}] {execution.started_at[:19]} ({duration_str})")
        if execution.error:
            print(f"       Error: {execution.error[:60]}")
        print()


async def schedule_validate_command(args):
    """Validate a cron expression."""
    is_valid, error = CronParser.is_valid(args.cron)

    if not is_valid:
        print(f"Invalid cron expression: {error}", file=sys.stderr)
        sys.exit(1)

    # Calculate next runs
    current = datetime.now()
    next_runs = []
    for _ in range(5):
        next_run = CronParser.get_next_run(args.cron, current)
        next_runs.append(next_run)
        current = next_run

    if args.json:
        print(json.dumps({
            "valid": True,
            "cron": args.cron,
            "next_runs": [r.isoformat() for r in next_runs]
        }, indent=2))
        return

    print(f"Valid cron expression: {args.cron}")
    print()
    print("Next 5 run times:")
    for run in next_runs:
        print(f"  {run.strftime('%Y-%m-%d %H:%M (%A)')}")


# Settings commands

async def settings_encrypt_command(args):
    """Migrate existing plaintext API keys to encrypted format."""
    service = SettingsService(config.DATABASE_PATH)

    if args.status_only:
        # Just show encryption status
        status = await service.get_encryption_status()

        if args.json:
            print(json.dumps(status, indent=2))
            return

        print("Encryption Status")
        print("=" * 50)
        print(f"Encryption available: {'Yes' if status['encryption_available'] else 'No'}")
        print(f"All keys encrypted: {'Yes' if status['all_encrypted'] else 'No'}")
        print()
        print("API Key Status:")
        for key, info in status['keys'].items():
            status_icon = "OK" if info['is_encrypted'] else ("WARN" if info['has_value'] else "N/A")
            has_value_str = "set" if info['has_value'] else "not set"
            encrypted_str = "encrypted" if info['is_encrypted'] else "plaintext"
            if info['has_value']:
                print(f"  [{status_icon}] {key}: {has_value_str}, {encrypted_str}")
            else:
                print(f"  [N/A] {key}: {has_value_str}")
        return

    # Perform migration
    print("Migrating API keys to encrypted format...")
    result = await service.migrate_to_encrypted()

    if args.json:
        print(json.dumps(result, indent=2))
        return

    if result['success']:
        print()
        print("Migration completed successfully!")
        if result['migrated']:
            print(f"  Migrated: {', '.join(result['migrated'])}")
        if result['already_encrypted']:
            print(f"  Already encrypted: {', '.join(result['already_encrypted'])}")
        if result['skipped']:
            print(f"  Skipped (no value): {', '.join(result['skipped'])}")
    else:
        print()
        print(f"Migration failed: {result['error']}", file=sys.stderr)
        if result['migrated']:
            print(f"  Partially migrated: {', '.join(result['migrated'])}")
        sys.exit(1)


async def settings_status_command(args):
    """Show current settings (with masked API keys)."""
    service = SettingsService(config.DATABASE_PATH)

    display = await service.get_display_settings()
    enc_status = await service.get_encryption_status()

    if args.json:
        output = {
            "settings": display,
            "encryption": enc_status
        }
        print(json.dumps(output, indent=2))
        return

    print("Settings Status")
    print("=" * 50)
    print()
    print("API Keys:")
    print(f"  OpenAI:    {display['openai_api_key_masked'] or '(not set)'}")
    print(f"  Anthropic: {display['anthropic_api_key_masked'] or '(not set)'}")
    print()
    print("Configuration:")
    print(f"  Model:            {display['model']}")
    print(f"  Permission level: {display['permission_level']}")
    print()
    print("Encryption:")
    print(f"  Available: {'Yes' if enc_status['encryption_available'] else 'No'}")
    print(f"  All encrypted: {'Yes' if enc_status['all_encrypted'] else 'No'}")
    for key, info in enc_status['keys'].items():
        if info['has_value']:
            status = "encrypted" if info['is_encrypted'] else "PLAINTEXT"
            print(f"    {key}: {status}")


def main():
    parser = argparse.ArgumentParser(
        prog="assistant.cli",
        description="AI Assistant CLI"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Export command
    export_parser = subparsers.add_parser("export", help="Export conversation to JSON")
    export_parser.add_argument(
        "--output", "-o",
        help="Output file path (default: stdout)"
    )

    # Import command
    import_parser = subparsers.add_parser("import", help="Import conversation from JSON")
    import_parser.add_argument(
        "--input", "-i",
        required=True,
        help="Input file path"
    )
    import_parser.add_argument(
        "--mode", "-m",
        choices=["merge", "replace"],
        default="merge",
        help="Import mode: merge (skip duplicates) or replace (clear existing)"
    )

    # Alerts command with subcommands
    alerts_parser = subparsers.add_parser("alerts", help="Manage alerts")
    alerts_subparsers = alerts_parser.add_subparsers(dest="alerts_command", help="Alerts commands")

    # alerts list
    alerts_list_parser = alerts_subparsers.add_parser("list", help="List alerts")
    alerts_list_parser.add_argument(
        "--limit", "-l",
        type=int, default=100,
        help="Maximum number of alerts to show (default: 100)"
    )
    alerts_list_parser.add_argument(
        "--offset", "-o",
        type=int, default=0,
        help="Pagination offset (default: 0)"
    )
    alerts_list_parser.add_argument(
        "--severity", "-s",
        choices=["info", "warning", "error", "critical"],
        help="Filter by severity"
    )
    alerts_list_parser.add_argument(
        "--type", "-t",
        choices=["error_threshold", "rate_limit", "server_health", "disk_space", "api_error", "custom"],
        help="Filter by alert type"
    )
    alerts_list_parser.add_argument(
        "--acknowledged", "-a",
        choices=["true", "false"],
        help="Filter by acknowledgment status"
    )
    alerts_list_parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output in JSON format"
    )

    # alerts stats
    alerts_stats_parser = alerts_subparsers.add_parser("stats", help="Show alert statistics")
    alerts_stats_parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output in JSON format"
    )

    # alerts acknowledge
    alerts_ack_parser = alerts_subparsers.add_parser("acknowledge", help="Acknowledge an alert")
    alerts_ack_parser.add_argument(
        "alert_id",
        help="ID of the alert to acknowledge"
    )

    # alerts clear
    alerts_clear_parser = alerts_subparsers.add_parser("clear", help="Clear old alerts")
    alerts_clear_parser.add_argument(
        "--days", "-d",
        type=int, default=30,
        help="Delete alerts older than N days (default: 30)"
    )

    # Backup command with subcommands
    backup_parser = subparsers.add_parser("backup", help="Backup and restore assistant data")
    backup_subparsers = backup_parser.add_subparsers(dest="backup_command", help="Backup commands")

    # backup create
    backup_create_parser = backup_subparsers.add_parser("create", help="Create a backup")
    backup_create_parser.add_argument(
        "--output", "-o",
        help="Output file path (default: memory/backups/backup_TIMESTAMP.tar.gz)"
    )
    backup_create_parser.add_argument(
        "--include-benchmarks", "-b",
        action="store_true",
        help="Include benchmark data in backup"
    )
    backup_create_parser.add_argument(
        "--keep", "-k",
        type=int, default=10,
        help="Number of backups to keep for rotation (default: 10)"
    )

    # backup restore
    backup_restore_parser = backup_subparsers.add_parser("restore", help="Restore from a backup")
    backup_restore_parser.add_argument(
        "--input", "-i",
        required=True,
        help="Input backup file path"
    )
    backup_restore_parser.add_argument(
        "--preview", "-p",
        action="store_true",
        help="Preview what would be restored without making changes"
    )
    backup_restore_parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Force restore, overwriting existing files"
    )

    # backup list
    backup_list_parser = backup_subparsers.add_parser("list", help="List available backups")
    backup_list_parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output in JSON format"
    )

    # backup verify
    backup_verify_parser = backup_subparsers.add_parser("verify", help="Verify backup integrity")
    backup_verify_parser.add_argument(
        "--input", "-i",
        required=True,
        help="Backup file to verify"
    )

    # backup schedule
    backup_schedule_parser = backup_subparsers.add_parser("schedule", help="Show backup schedule configuration")
    backup_schedule_parser.add_argument(
        "--hour", "-H",
        type=int, default=3,
        help="Hour to run backup (0-23, default: 3)"
    )
    backup_schedule_parser.add_argument(
        "--minute", "-M",
        type=int, default=0,
        help="Minute to run backup (0-59, default: 0)"
    )
    backup_schedule_parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output in JSON format"
    )

    # Resources command with subcommands
    resources_parser = subparsers.add_parser("resources", help="Monitor system resources")
    resources_parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output in JSON format"
    )
    resources_subparsers = resources_parser.add_subparsers(dest="resources_command", help="Resources commands")

    # resources cleanup files
    resources_cleanup_files_parser = resources_subparsers.add_parser("cleanup", help="Clean up old files")
    resources_cleanup_files_parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Show what would be deleted without actually deleting"
    )
    resources_cleanup_files_parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output in JSON format"
    )

    # resources cleanup memory (as a separate subcommand under cleanup)
    resources_cleanup_memory_parser = resources_subparsers.add_parser("memory", help="Clean up memory (run garbage collection)")
    resources_cleanup_memory_parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output in JSON format"
    )

    # Logs command with subcommands
    logs_parser = subparsers.add_parser("logs", help="Manage log files")
    logs_subparsers = logs_parser.add_subparsers(dest="logs_command", help="Logs commands")

    # logs tail
    logs_tail_parser = logs_subparsers.add_parser("tail", help="Show last N lines of a log file")
    logs_tail_parser.add_argument(
        "--name", "-n",
        default="assistant",
        choices=["assistant", "error", "access"],
        help="Log file name (default: assistant)"
    )
    logs_tail_parser.add_argument(
        "--lines", "-l",
        type=int, default=50,
        help="Number of lines to show (default: 50)"
    )
    logs_tail_parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output in JSON format"
    )

    # logs list
    logs_list_parser = logs_subparsers.add_parser("list", help="List all log files")
    logs_list_parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output in JSON format"
    )

    # logs clear
    logs_clear_parser = logs_subparsers.add_parser("clear", help="Clear a log file")
    logs_clear_parser.add_argument(
        "--name", "-n",
        default="assistant",
        choices=["assistant", "error", "access"],
        help="Log file name (default: assistant)"
    )
    logs_clear_parser.add_argument(
        "--confirm", "-y",
        action="store_true",
        help="Confirm clearing the log file"
    )
    logs_clear_parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output in JSON format"
    )

    # logs cleanup
    logs_cleanup_parser = logs_subparsers.add_parser("cleanup", help="Delete old log files")
    logs_cleanup_parser.add_argument(
        "--days", "-d",
        type=int, default=30,
        help="Delete logs older than N days (default: 30)"
    )
    logs_cleanup_parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Show what would be deleted without actually deleting"
    )
    logs_cleanup_parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output in JSON format"
    )

    # Schedule command with subcommands
    schedule_parser = subparsers.add_parser("schedule", help="Manage scheduled tasks")
    schedule_subparsers = schedule_parser.add_subparsers(dest="schedule_command", help="Schedule commands")

    # schedule list
    schedule_list_parser = schedule_subparsers.add_parser("list", help="List scheduled tasks")
    schedule_list_parser.add_argument(
        "--status", "-s",
        choices=["pending", "running", "completed", "failed", "cancelled", "disabled"],
        help="Filter by task status"
    )
    schedule_list_parser.add_argument(
        "--enabled", "-e",
        choices=["true", "false"],
        help="Filter by enabled state"
    )
    schedule_list_parser.add_argument(
        "--limit", "-l",
        type=int, default=100,
        help="Maximum number of tasks to show (default: 100)"
    )
    schedule_list_parser.add_argument(
        "--offset", "-o",
        type=int, default=0,
        help="Pagination offset (default: 0)"
    )
    schedule_list_parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output in JSON format"
    )

    # schedule add
    schedule_add_parser = schedule_subparsers.add_parser("add", help="Add a new scheduled task")
    schedule_add_parser.add_argument(
        "--name", "-n",
        required=True,
        help="Task name"
    )
    schedule_add_parser.add_argument(
        "--type", "-t",
        required=True,
        choices=["one_time", "recurring"],
        help="Task type: one_time or recurring"
    )
    schedule_add_parser.add_argument(
        "--schedule", "-s",
        required=True,
        help="ISO datetime for one_time (e.g., 2026-02-05T15:00:00), cron expression for recurring (e.g., '0 7 * * *')"
    )
    schedule_add_parser.add_argument(
        "--action", "-a",
        required=True,
        choices=["notification", "http", "log"],
        help="Action type: notification, http, or log"
    )
    schedule_add_parser.add_argument(
        "--params", "-p",
        default="{}",
        help="Action parameters as JSON (e.g., '{\"title\":\"Hello\",\"message\":\"World\"}')"
    )
    schedule_add_parser.add_argument(
        "--metadata", "-m",
        default=None,
        help="Optional metadata as JSON"
    )
    schedule_add_parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output in JSON format"
    )

    # schedule remove
    schedule_remove_parser = schedule_subparsers.add_parser("remove", help="Remove a scheduled task")
    schedule_remove_parser.add_argument(
        "task_id",
        help="ID of the task to remove"
    )
    schedule_remove_parser.add_argument(
        "--confirm", "-y",
        action="store_true",
        help="Confirm deletion"
    )

    # schedule enable
    schedule_enable_parser = schedule_subparsers.add_parser("enable", help="Enable a disabled task")
    schedule_enable_parser.add_argument(
        "task_id",
        help="ID of the task to enable"
    )

    # schedule disable
    schedule_disable_parser = schedule_subparsers.add_parser("disable", help="Disable a task")
    schedule_disable_parser.add_argument(
        "task_id",
        help="ID of the task to disable"
    )

    # schedule history
    schedule_history_parser = schedule_subparsers.add_parser("history", help="Show task execution history")
    schedule_history_parser.add_argument(
        "task_id",
        help="ID of the task"
    )
    schedule_history_parser.add_argument(
        "--limit", "-l",
        type=int, default=50,
        help="Maximum number of executions to show (default: 50)"
    )
    schedule_history_parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output in JSON format"
    )

    # schedule validate (validate cron expression)
    schedule_validate_parser = schedule_subparsers.add_parser("validate", help="Validate a cron expression")
    schedule_validate_parser.add_argument(
        "cron",
        help="Cron expression to validate (e.g., '0 7 * * *')"
    )
    schedule_validate_parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output in JSON format"
    )

    # Settings command with subcommands
    settings_parser = subparsers.add_parser("settings", help="Manage settings and encryption")
    settings_subparsers = settings_parser.add_subparsers(dest="settings_command", help="Settings commands")

    # settings encrypt
    settings_encrypt_parser = settings_subparsers.add_parser("encrypt", help="Migrate API keys to encrypted format")
    settings_encrypt_parser.add_argument(
        "--status-only", "-s",
        action="store_true",
        help="Only show encryption status without migrating"
    )
    settings_encrypt_parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output in JSON format"
    )

    # settings status
    settings_status_parser = settings_subparsers.add_parser("status", help="Show settings status")
    settings_status_parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output in JSON format"
    )

    args = parser.parse_args()

    if args.command == "export":
        asyncio.run(export_command(args))
    elif args.command == "import":
        asyncio.run(import_command(args))
    elif args.command == "alerts":
        if args.alerts_command == "list":
            asyncio.run(alerts_list_command(args))
        elif args.alerts_command == "stats":
            asyncio.run(alerts_stats_command(args))
        elif args.alerts_command == "acknowledge":
            asyncio.run(alerts_acknowledge_command(args))
        elif args.alerts_command == "clear":
            asyncio.run(alerts_clear_command(args))
        else:
            alerts_parser.print_help()
            sys.exit(1)
    elif args.command == "backup":
        if args.backup_command == "create":
            asyncio.run(backup_create_command(args))
        elif args.backup_command == "restore":
            asyncio.run(backup_restore_command(args))
        elif args.backup_command == "list":
            asyncio.run(backup_list_command(args))
        elif args.backup_command == "verify":
            asyncio.run(backup_verify_command(args))
        elif args.backup_command == "schedule":
            asyncio.run(backup_schedule_command(args))
        else:
            backup_parser.print_help()
            sys.exit(1)
    elif args.command == "resources":
        if args.resources_command == "cleanup":
            asyncio.run(resources_cleanup_files_command(args))
        elif args.resources_command == "memory":
            asyncio.run(resources_cleanup_memory_command(args))
        elif args.resources_command is None:
            # Default: show resource status
            asyncio.run(resources_command(args))
        else:
            resources_parser.print_help()
            sys.exit(1)
    elif args.command == "logs":
        if args.logs_command == "tail":
            logs_tail_command(args)
        elif args.logs_command == "list":
            logs_list_command(args)
        elif args.logs_command == "clear":
            logs_clear_command(args)
        elif args.logs_command == "cleanup":
            logs_cleanup_command(args)
        else:
            logs_parser.print_help()
            sys.exit(1)
    elif args.command == "schedule":
        if args.schedule_command == "list":
            asyncio.run(schedule_list_command(args))
        elif args.schedule_command == "add":
            asyncio.run(schedule_add_command(args))
        elif args.schedule_command == "remove":
            asyncio.run(schedule_remove_command(args))
        elif args.schedule_command == "enable":
            asyncio.run(schedule_enable_command(args))
        elif args.schedule_command == "disable":
            asyncio.run(schedule_disable_command(args))
        elif args.schedule_command == "history":
            asyncio.run(schedule_history_command(args))
        elif args.schedule_command == "validate":
            asyncio.run(schedule_validate_command(args))
        else:
            schedule_parser.print_help()
            sys.exit(1)
    elif args.command == "settings":
        if args.settings_command == "encrypt":
            asyncio.run(settings_encrypt_command(args))
        elif args.settings_command == "status":
            asyncio.run(settings_status_command(args))
        else:
            settings_parser.print_help()
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
