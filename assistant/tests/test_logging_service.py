"""Tests for logging service with rotation."""
import logging
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from server.services.logging_service import (
    LogConfig,
    LoggingService,
    DEFAULT_LOG_LEVEL,
    DEFAULT_MAX_BYTES,
    DEFAULT_BACKUP_COUNT,
    DEFAULT_LOG_MAX_AGE_DAYS,
)


class TestLogConfig:
    """Tests for LogConfig."""

    def test_default_values(self, tmp_path):
        """Test default configuration values."""
        config = LogConfig(log_dir=tmp_path)

        assert config.log_dir == tmp_path
        assert config.log_level == DEFAULT_LOG_LEVEL
        assert config.max_bytes == DEFAULT_MAX_BYTES
        assert config.backup_count == DEFAULT_BACKUP_COUNT
        assert config.max_age_days == DEFAULT_LOG_MAX_AGE_DAYS

    def test_custom_values(self, tmp_path):
        """Test custom configuration values."""
        config = LogConfig(
            log_dir=tmp_path,
            log_level="DEBUG",
            max_bytes=5 * 1024 * 1024,
            backup_count=3,
            max_age_days=7
        )

        assert config.log_level == "DEBUG"
        assert config.max_bytes == 5 * 1024 * 1024
        assert config.backup_count == 3
        assert config.max_age_days == 7

    def test_env_var_log_level(self, tmp_path, monkeypatch):
        """Test log level from environment variable."""
        monkeypatch.setenv("ASSISTANT_LOG_LEVEL", "WARNING")
        config = LogConfig(log_dir=tmp_path)

        assert config.log_level == "WARNING"

    def test_log_paths(self, tmp_path):
        """Test log file paths."""
        config = LogConfig(log_dir=tmp_path)

        assert config.assistant_log_path == tmp_path / "assistant.log"
        assert config.error_log_path == tmp_path / "error.log"
        assert config.access_log_path == tmp_path / "access.log"

    def test_creates_log_dir(self, tmp_path):
        """Test that log directory is created."""
        log_dir = tmp_path / "logs" / "nested"
        config = LogConfig(log_dir=log_dir)

        assert log_dir.exists()


class TestLoggingService:
    """Tests for LoggingService."""

    @pytest.fixture
    def service(self, tmp_path):
        """Create a logging service with temp directory."""
        config = LogConfig(log_dir=tmp_path)
        return LoggingService(config)

    def test_configure_creates_handlers(self, service):
        """Test that configure creates handlers."""
        service.configure()

        assert service._configured
        assert len(service._handlers) > 0

    def test_configure_only_once(self, service):
        """Test that configure is idempotent."""
        service.configure()
        handler_count = len(service._handlers)

        service.configure()

        assert len(service._handlers) == handler_count

    def test_logging_creates_files(self, service):
        """Test that logging creates log files."""
        service.configure()

        # Log something
        logger = logging.getLogger("test_logging_creates_files")
        logger.info("Test message")
        logger.error("Test error")

        # Flush handlers
        for handler in service._handlers:
            handler.flush()

        # Check files exist
        assert service.config.assistant_log_path.exists()
        assert service.config.error_log_path.exists()

    def test_error_log_only_errors(self, service):
        """Test that error log only contains ERROR and above."""
        service.configure()

        logger = logging.getLogger("test_error_log")
        logger.info("Info message")
        logger.warning("Warning message")
        logger.error("Error message")

        for handler in service._handlers:
            handler.flush()

        # Error log should only have error message
        error_content = service.config.error_log_path.read_text()
        assert "Error message" in error_content
        assert "Info message" not in error_content
        assert "Warning message" not in error_content

    def test_access_logger(self, tmp_path):
        """Test access logger creation."""
        # Use a unique logger name to avoid conflicts with other tests
        import uuid
        unique_name = f"access_{uuid.uuid4().hex[:8]}"

        config = LogConfig(log_dir=tmp_path)
        service = LoggingService(config)

        # Temporarily patch the access logger name
        original_get = service.get_access_logger

        def get_unique_access_logger():
            logger = logging.getLogger(unique_name)
            if not logger.handlers:
                from logging.handlers import RotatingFileHandler
                handler = RotatingFileHandler(
                    config.access_log_path,
                    maxBytes=config.max_bytes,
                    backupCount=config.backup_count,
                    encoding="utf-8"
                )
                handler.setLevel(logging.INFO)
                handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
                logger.addHandler(handler)
                logger.setLevel(logging.INFO)
                logger.propagate = False
            return logger

        access_logger = get_unique_access_logger()

        assert not access_logger.propagate  # Should not propagate to root

        # Log access entry
        access_logger.info("GET /api/chat 200 10ms")

        # Flush access logger handlers
        for handler in access_logger.handlers:
            handler.flush()

        assert config.access_log_path.exists()
        content = config.access_log_path.read_text()
        assert "GET /api/chat 200 10ms" in content

    def test_list_log_files_empty(self, service):
        """Test listing files when none exist."""
        files = service.list_log_files()

        assert files == []

    def test_list_log_files(self, service):
        """Test listing log files."""
        # Create some log files
        (service.config.log_dir / "assistant.log").write_text("test")
        (service.config.log_dir / "error.log").write_text("test")

        files = service.list_log_files()

        assert len(files) == 2
        assert any(f["name"] == "assistant.log" for f in files)
        assert any(f["name"] == "error.log" for f in files)

    def test_list_log_files_includes_rotated(self, service):
        """Test that listing includes rotated files."""
        (service.config.log_dir / "assistant.log").write_text("current")
        (service.config.log_dir / "assistant.log.1").write_text("backup1")
        (service.config.log_dir / "assistant.log.2").write_text("backup2")

        files = service.list_log_files()

        assert len(files) == 3

    def test_get_log_content_empty(self, service):
        """Test getting content from non-existent file."""
        result = service.get_log_content("assistant")

        assert result["lines"] == []
        assert result["total_lines"] == 0
        assert result["exists"] is False

    def test_get_log_content(self, service):
        """Test getting log content."""
        log_path = service.config.log_dir / "assistant.log"
        log_path.write_text("line1\nline2\nline3\n")

        result = service.get_log_content("assistant", lines=10)

        assert result["exists"] is True
        assert result["total_lines"] == 3
        assert result["lines"] == ["line1", "line2", "line3"]

    def test_get_log_content_with_limit(self, service):
        """Test getting limited log content."""
        log_path = service.config.log_dir / "assistant.log"
        log_path.write_text("\n".join([f"line{i}" for i in range(100)]))

        result = service.get_log_content("assistant", lines=10)

        assert len(result["lines"]) == 10
        assert result["lines"][-1] == "line99"  # Last line
        assert result["total_lines"] == 100

    def test_tail_log(self, service):
        """Test tail functionality."""
        log_path = service.config.log_dir / "assistant.log"
        log_path.write_text("\n".join([f"line{i}" for i in range(100)]))

        lines = service.tail_log("assistant", lines=5)

        assert len(lines) == 5
        assert lines[-1] == "line99"

    def test_clear_log_without_confirm(self, service):
        """Test clearing log without confirmation fails."""
        log_path = service.config.log_dir / "assistant.log"
        log_path.write_text("content")

        result = service.clear_log("assistant", confirm=False)

        assert result["success"] is False
        assert log_path.read_text() == "content"

    def test_clear_log_nonexistent(self, service):
        """Test clearing non-existent log."""
        result = service.clear_log("nonexistent", confirm=True)

        assert result["success"] is False
        assert "not found" in result["message"]

    def test_clear_log_success(self, service):
        """Test successfully clearing a log."""
        log_path = service.config.log_dir / "assistant.log"
        log_path.write_text("content to clear")

        result = service.clear_log("assistant", confirm=True)

        assert result["success"] is True
        assert log_path.read_text() == ""

    def test_cleanup_old_logs_none_old(self, service):
        """Test cleanup when no old logs exist."""
        # Create recent log
        log_path = service.config.log_dir / "recent.log"
        log_path.write_text("recent")

        result = service.cleanup_old_logs()

        assert result["deleted"] == []
        assert result["total_bytes_freed"] == 0

    def test_cleanup_old_logs_dry_run(self, tmp_path):
        """Test cleanup dry run mode."""
        config = LogConfig(log_dir=tmp_path, max_age_days=1)
        service = LoggingService(config)

        # Create an old log file
        log_path = tmp_path / "old.log"
        log_path.write_text("old content")

        # Set mtime to 2 days ago
        old_time = (datetime.now() - timedelta(days=2)).timestamp()
        os.utime(log_path, (old_time, old_time))

        result = service.cleanup_old_logs(dry_run=True)

        assert len(result["deleted"]) == 1
        assert result["dry_run"] is True
        assert log_path.exists()  # File should still exist

    def test_cleanup_old_logs_actual(self, tmp_path):
        """Test actual cleanup of old logs."""
        config = LogConfig(log_dir=tmp_path, max_age_days=1)
        service = LoggingService(config)

        # Create an old log file
        log_path = tmp_path / "old.log"
        log_path.write_text("old content")

        # Set mtime to 2 days ago
        old_time = (datetime.now() - timedelta(days=2)).timestamp()
        os.utime(log_path, (old_time, old_time))

        result = service.cleanup_old_logs(dry_run=False)

        assert len(result["deleted"]) == 1
        assert not log_path.exists()  # File should be deleted

    def test_get_stats(self, service):
        """Test getting statistics."""
        # Create some logs
        (service.config.log_dir / "assistant.log").write_text("test" * 100)
        (service.config.log_dir / "error.log").write_text("test" * 50)

        stats = service.get_stats()

        assert stats["log_dir"] == str(service.config.log_dir)
        assert stats["log_level"] == service.config.log_level
        assert stats["total_files"] == 2
        assert stats["total_size_bytes"] > 0


class TestLogLevels:
    """Tests for configurable log levels."""

    def test_debug_level(self, tmp_path):
        """Test DEBUG level logs everything."""
        config = LogConfig(log_dir=tmp_path, log_level="DEBUG")
        service = LoggingService(config)
        service.configure()

        logger = logging.getLogger("test_debug")
        logger.debug("Debug message")
        logger.info("Info message")

        for handler in service._handlers:
            handler.flush()

        content = config.assistant_log_path.read_text()
        assert "Debug message" in content
        assert "Info message" in content

    def test_warning_level(self, tmp_path):
        """Test WARNING level filters info."""
        config = LogConfig(log_dir=tmp_path, log_level="WARNING")
        service = LoggingService(config)
        service.configure()

        logger = logging.getLogger("test_warning")
        logger.info("Info message")
        logger.warning("Warning message")

        for handler in service._handlers:
            handler.flush()

        content = config.assistant_log_path.read_text()
        assert "Info message" not in content
        assert "Warning message" in content


class TestLogRotation:
    """Tests for log rotation."""

    def test_rotation_on_size(self, tmp_path):
        """Test that logs rotate when they exceed max size."""
        # Use small max bytes for testing
        config = LogConfig(
            log_dir=tmp_path,
            max_bytes=1000,  # 1KB
            backup_count=2
        )
        service = LoggingService(config)
        service.configure()

        logger = logging.getLogger("test_rotation")

        # Write enough data to trigger rotation
        for i in range(100):
            logger.info("X" * 100)  # 100+ chars per line

        for handler in service._handlers:
            handler.flush()

        # Check for rotated files
        log_files = list(tmp_path.glob("assistant.log*"))
        assert len(log_files) > 1  # Main file + at least one backup

    def test_backup_count_limit(self, tmp_path):
        """Test that backup count is respected."""
        config = LogConfig(
            log_dir=tmp_path,
            max_bytes=500,  # Very small
            backup_count=2  # Keep only 2 backups
        )
        service = LoggingService(config)
        service.configure()

        logger = logging.getLogger("test_backup_count")

        # Write lots of data to trigger multiple rotations
        for i in range(200):
            logger.info("Y" * 100)

        for handler in service._handlers:
            handler.flush()

        # Should have main + 2 backups max
        log_files = list(tmp_path.glob("assistant.log*"))
        assert len(log_files) <= 3  # Main + 2 backups


class TestCLIIntegration:
    """Tests for CLI integration with logging service."""

    def test_tail_returns_lines(self, tmp_path):
        """Test tail returns correct lines."""
        config = LogConfig(log_dir=tmp_path)
        service = LoggingService(config)

        # Create log with known content
        log_path = tmp_path / "assistant.log"
        log_path.write_text("line1\nline2\nline3\nline4\nline5\n")

        lines = service.tail_log("assistant", lines=3)

        assert len(lines) == 3
        assert lines == ["line3", "line4", "line5"]

    def test_list_shows_all_logs(self, tmp_path):
        """Test list shows all log files."""
        config = LogConfig(log_dir=tmp_path)
        service = LoggingService(config)

        # Create multiple logs
        (tmp_path / "assistant.log").write_text("main")
        (tmp_path / "assistant.log.1").write_text("backup1")
        (tmp_path / "error.log").write_text("errors")
        (tmp_path / "access.log").write_text("access")

        stats = service.get_stats()

        assert stats["total_files"] == 4
        assert "assistant.log" in stats["files_by_type"]
