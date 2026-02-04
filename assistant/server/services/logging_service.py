"""Logging service with rotation and multiple log files.

Provides:
- RotatingFileHandler for automatic file rotation (max 10MB, 5 backups)
- Separate log files: assistant.log, error.log, access.log
- Configurable log levels via ASSISTANT_LOG_LEVEL environment variable
- Old log cleanup (configurable age, default 30 days)
"""
import logging
import os
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

# Default log configuration
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10MB
DEFAULT_BACKUP_COUNT = 5
DEFAULT_LOG_MAX_AGE_DAYS = 30


class LogConfig:
    """Configuration for logging service."""

    def __init__(
        self,
        log_dir: Path,
        log_level: Optional[str] = None,
        max_bytes: int = DEFAULT_MAX_BYTES,
        backup_count: int = DEFAULT_BACKUP_COUNT,
        max_age_days: int = DEFAULT_LOG_MAX_AGE_DAYS,
    ):
        self.log_dir = Path(log_dir)
        self.log_level = log_level or os.getenv("ASSISTANT_LOG_LEVEL", DEFAULT_LOG_LEVEL).upper()
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.max_age_days = max_age_days

        # Ensure log directory exists
        self.log_dir.mkdir(parents=True, exist_ok=True)

    @property
    def assistant_log_path(self) -> Path:
        return self.log_dir / "assistant.log"

    @property
    def error_log_path(self) -> Path:
        return self.log_dir / "error.log"

    @property
    def access_log_path(self) -> Path:
        return self.log_dir / "access.log"


class LoggingService:
    """Service for managing application logging with rotation."""

    def __init__(self, config: LogConfig):
        self.config = config
        self._configured = False
        self._handlers: list[logging.Handler] = []

    def configure(self) -> None:
        """Configure logging with rotating file handlers."""
        if self._configured:
            return

        # Get numeric level
        log_level = getattr(logging, self.config.log_level, logging.INFO)

        # Common format
        detailed_format = logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        simple_format = logging.Formatter(
            "%(asctime)s %(levelname)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        # Get root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)

        # Clear existing handlers
        root_logger.handlers.clear()

        # Console handler (stdout)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        console_handler.setFormatter(simple_format)
        root_logger.addHandler(console_handler)
        self._handlers.append(console_handler)

        # Main log file (assistant.log) - all messages at configured level
        main_handler = RotatingFileHandler(
            self.config.assistant_log_path,
            maxBytes=self.config.max_bytes,
            backupCount=self.config.backup_count,
            encoding="utf-8"
        )
        main_handler.setLevel(log_level)
        main_handler.setFormatter(detailed_format)
        root_logger.addHandler(main_handler)
        self._handlers.append(main_handler)

        # Error log file (error.log) - only ERROR and above
        error_handler = RotatingFileHandler(
            self.config.error_log_path,
            maxBytes=self.config.max_bytes,
            backupCount=self.config.backup_count,
            encoding="utf-8"
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(detailed_format)
        root_logger.addHandler(error_handler)
        self._handlers.append(error_handler)

        self._configured = True

    def get_access_logger(self) -> logging.Logger:
        """Get a dedicated access logger for HTTP requests."""
        access_logger = logging.getLogger("access")

        # Only add handler if not already added
        if not access_logger.handlers:
            access_format = logging.Formatter(
                '%(asctime)s %(message)s',
                datefmt="%Y-%m-%d %H:%M:%S"
            )

            access_handler = RotatingFileHandler(
                self.config.access_log_path,
                maxBytes=self.config.max_bytes,
                backupCount=self.config.backup_count,
                encoding="utf-8"
            )
            access_handler.setLevel(logging.INFO)
            access_handler.setFormatter(access_format)
            access_logger.addHandler(access_handler)
            # Set logger level (not just handler level)
            access_logger.setLevel(logging.INFO)
            # Don't propagate to root (avoid duplication)
            access_logger.propagate = False
            self._handlers.append(access_handler)

        return access_logger

    def list_log_files(self) -> list[dict]:
        """List all log files with metadata."""
        log_files = []

        for path in self.config.log_dir.glob("*.log*"):
            if path.is_file():
                stat = path.stat()
                log_files.append({
                    "path": str(path),
                    "name": path.name,
                    "size_bytes": stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                })

        # Sort by modified time, newest first
        log_files.sort(key=lambda x: x["modified_at"], reverse=True)
        return log_files

    def get_log_content(
        self,
        log_name: str = "assistant",
        lines: int = 100,
        offset: int = 0
    ) -> dict:
        """Get content from a log file.

        Args:
            log_name: Name of log file (assistant, error, access)
            lines: Number of lines to return
            offset: Number of lines from end to skip (for pagination)

        Returns:
            dict with lines, total_lines, and file info
        """
        log_path = self.config.log_dir / f"{log_name}.log"

        if not log_path.exists():
            return {
                "lines": [],
                "total_lines": 0,
                "file": str(log_path),
                "exists": False
            }

        # Read all lines
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()

        total_lines = len(all_lines)

        # Get requested slice from end
        if offset > 0:
            end_idx = -offset
            start_idx = end_idx - lines
        else:
            end_idx = None
            start_idx = -lines

        if start_idx >= 0:
            start_idx = 0

        if end_idx is not None:
            selected = all_lines[start_idx:end_idx]
        else:
            selected = all_lines[start_idx:]

        return {
            "lines": [line.rstrip("\n") for line in selected],
            "total_lines": total_lines,
            "file": str(log_path),
            "exists": True
        }

    def tail_log(self, log_name: str = "assistant", lines: int = 50) -> list[str]:
        """Get last N lines from a log file (like tail -f)."""
        result = self.get_log_content(log_name, lines=lines)
        return result["lines"]

    def clear_log(self, log_name: str, confirm: bool = False) -> dict:
        """Clear a log file.

        Args:
            log_name: Name of log file to clear
            confirm: Must be True to actually clear

        Returns:
            dict with success status and message
        """
        if not confirm:
            return {
                "success": False,
                "message": "Must set confirm=True to clear logs"
            }

        log_path = self.config.log_dir / f"{log_name}.log"

        if not log_path.exists():
            return {
                "success": False,
                "message": f"Log file not found: {log_path}"
            }

        # Truncate the file
        try:
            with open(log_path, "w", encoding="utf-8") as f:
                f.truncate(0)
            return {
                "success": True,
                "message": f"Cleared {log_path}"
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error clearing log: {e}"
            }

    def cleanup_old_logs(self, dry_run: bool = False) -> dict:
        """Delete log files older than max_age_days.

        Args:
            dry_run: If True, just report what would be deleted

        Returns:
            dict with deleted files and summary
        """
        cutoff = datetime.now() - timedelta(days=self.config.max_age_days)
        deleted = []
        errors = []
        total_bytes = 0

        for path in self.config.log_dir.glob("*.log*"):
            if not path.is_file():
                continue

            # Check if file is older than cutoff
            mtime = datetime.fromtimestamp(path.stat().st_mtime)
            if mtime < cutoff:
                file_info = {
                    "path": str(path),
                    "name": path.name,
                    "size_bytes": path.stat().st_size,
                    "modified_at": mtime.isoformat()
                }

                if not dry_run:
                    try:
                        size = path.stat().st_size
                        path.unlink()
                        total_bytes += size
                        deleted.append(file_info)
                    except Exception as e:
                        errors.append({
                            "path": str(path),
                            "error": str(e)
                        })
                else:
                    total_bytes += path.stat().st_size
                    deleted.append(file_info)

        return {
            "deleted": deleted,
            "total_bytes_freed": total_bytes,
            "dry_run": dry_run,
            "errors": errors,
            "cutoff_date": cutoff.isoformat()
        }

    def get_stats(self) -> dict:
        """Get logging statistics."""
        log_files = self.list_log_files()
        total_size = sum(f["size_bytes"] for f in log_files)

        # Count by type
        by_type = {}
        for f in log_files:
            name = f["name"]
            # Extract base name (before any rotation suffix)
            if ".log" in name:
                base = name.split(".log")[0] + ".log"
            else:
                base = name
            by_type[base] = by_type.get(base, 0) + 1

        return {
            "log_dir": str(self.config.log_dir),
            "log_level": self.config.log_level,
            "max_bytes": self.config.max_bytes,
            "backup_count": self.config.backup_count,
            "max_age_days": self.config.max_age_days,
            "total_files": len(log_files),
            "total_size_bytes": total_size,
            "files_by_type": by_type,
            "files": log_files
        }


# Global instance for easy access
_logging_service: Optional[LoggingService] = None


def get_logging_service(log_dir: Optional[Path] = None) -> LoggingService:
    """Get the global logging service instance."""
    global _logging_service

    if _logging_service is None:
        if log_dir is None:
            # Default to assistant/logs/
            from pathlib import Path
            log_dir = Path(__file__).parent.parent.parent / "logs"

        config = LogConfig(log_dir=log_dir)
        _logging_service = LoggingService(config)

    return _logging_service


def configure_logging(log_dir: Optional[Path] = None) -> LoggingService:
    """Configure logging and return the service."""
    service = get_logging_service(log_dir)
    service.configure()
    return service
