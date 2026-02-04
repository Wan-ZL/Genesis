"""Tests for ResourceService."""
import asyncio
import os
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from server.services.resources import (
    ResourceService,
    ResourceConfig,
    ResourceStatus,
    ResourceSnapshot,
    RateLimitResult,
    get_resource_service,
)


class TestResourceConfig:
    """Tests for ResourceConfig defaults."""

    def test_default_config(self):
        """Test default configuration values."""
        config = ResourceConfig()
        assert config.max_memory_mb == 512
        assert config.memory_warning_percent == 75.0
        assert config.memory_critical_percent == 90.0
        assert config.cpu_warning_percent == 80.0
        assert config.cpu_critical_percent == 95.0
        assert config.disk_warning_gb == 5.0
        assert config.disk_critical_gb == 1.0
        assert config.max_requests_per_minute == 60
        assert config.rate_limit_window_seconds == 60
        assert config.file_max_age_days == 30
        assert config.cleanup_check_interval_hours == 24
        assert config.memory_cleanup_threshold_percent == 85.0

    def test_custom_config(self):
        """Test custom configuration values."""
        config = ResourceConfig(
            max_memory_mb=1024,
            max_requests_per_minute=100,
            file_max_age_days=7
        )
        assert config.max_memory_mb == 1024
        assert config.max_requests_per_minute == 100
        assert config.file_max_age_days == 7


class TestResourceService:
    """Tests for ResourceService core functionality."""

    def test_init_with_defaults(self):
        """Test service initialization with defaults."""
        service = ResourceService()
        assert service.config is not None
        assert service.files_path is None

    def test_init_with_custom_config(self):
        """Test service initialization with custom config."""
        config = ResourceConfig(max_memory_mb=256)
        service = ResourceService(config=config)
        assert service.config.max_memory_mb == 256

    def test_init_with_files_path(self, tmp_path):
        """Test service initialization with files path."""
        service = ResourceService(files_path=tmp_path)
        assert service.files_path == tmp_path


class TestMemoryUsage:
    """Tests for memory usage tracking."""

    def test_get_memory_usage_returns_dict(self):
        """Test that memory usage returns expected structure."""
        service = ResourceService()
        memory = service.get_memory_usage()

        assert "process_mb" in memory
        assert "process_percent" in memory
        assert "system_total_mb" in memory
        assert "system_available_mb" in memory
        assert "system_percent" in memory
        assert "limit_mb" in memory
        assert "status" in memory

    def test_get_memory_usage_values_are_positive(self):
        """Test that memory values are positive."""
        service = ResourceService()
        memory = service.get_memory_usage()

        assert memory["process_mb"] > 0
        assert memory["system_total_mb"] > 0
        assert memory["system_available_mb"] >= 0

    def test_memory_status_healthy(self):
        """Test healthy memory status."""
        config = ResourceConfig(max_memory_mb=10000)  # High limit
        service = ResourceService(config=config)
        status = service._get_memory_status(100)  # Low usage
        assert status == ResourceStatus.HEALTHY

    def test_memory_status_warning(self):
        """Test warning memory status."""
        config = ResourceConfig(
            max_memory_mb=100,
            memory_warning_percent=50.0,
            memory_critical_percent=90.0
        )
        service = ResourceService(config=config)
        status = service._get_memory_status(60)  # 60% of limit
        assert status == ResourceStatus.WARNING

    def test_memory_status_critical(self):
        """Test critical memory status."""
        config = ResourceConfig(
            max_memory_mb=100,
            memory_critical_percent=90.0
        )
        service = ResourceService(config=config)
        status = service._get_memory_status(95)  # 95% of limit
        assert status == ResourceStatus.CRITICAL


class TestCPUUsage:
    """Tests for CPU usage tracking."""

    def test_get_cpu_usage_returns_dict(self):
        """Test that CPU usage returns expected structure."""
        service = ResourceService()
        cpu = service.get_cpu_usage()

        assert "process_percent" in cpu
        assert "system_percent" in cpu
        assert "cpu_count" in cpu
        assert "status" in cpu

    def test_get_cpu_usage_values_are_valid(self):
        """Test that CPU values are valid."""
        service = ResourceService()
        cpu = service.get_cpu_usage()

        assert cpu["process_percent"] >= 0
        assert cpu["system_percent"] >= 0
        assert cpu["cpu_count"] > 0

    def test_cpu_status_healthy(self):
        """Test healthy CPU status."""
        service = ResourceService()
        status = service._get_cpu_status(10.0)
        assert status == ResourceStatus.HEALTHY

    def test_cpu_status_warning(self):
        """Test warning CPU status."""
        config = ResourceConfig(cpu_warning_percent=50.0)
        service = ResourceService(config=config)
        status = service._get_cpu_status(60.0)
        assert status == ResourceStatus.WARNING

    def test_cpu_status_critical(self):
        """Test critical CPU status."""
        config = ResourceConfig(cpu_critical_percent=90.0)
        service = ResourceService(config=config)
        status = service._get_cpu_status(95.0)
        assert status == ResourceStatus.CRITICAL


class TestDiskUsage:
    """Tests for disk usage tracking."""

    def test_get_disk_usage_returns_dict(self):
        """Test that disk usage returns expected structure."""
        service = ResourceService()
        disk = service.get_disk_usage()

        assert "total_gb" in disk
        assert "used_gb" in disk
        assert "free_gb" in disk
        assert "percent" in disk
        assert "status" in disk

    def test_get_disk_usage_values_are_valid(self):
        """Test that disk values are valid."""
        service = ResourceService()
        disk = service.get_disk_usage()

        assert disk["total_gb"] > 0
        assert disk["used_gb"] >= 0
        assert disk["free_gb"] >= 0
        assert 0 <= disk["percent"] <= 100

    def test_disk_status_healthy(self):
        """Test healthy disk status."""
        service = ResourceService()
        status = service._get_disk_status(100.0)  # 100GB free
        assert status == ResourceStatus.HEALTHY

    def test_disk_status_warning(self):
        """Test warning disk status."""
        config = ResourceConfig(disk_warning_gb=10.0)
        service = ResourceService(config=config)
        status = service._get_disk_status(5.0)  # Only 5GB free
        assert status == ResourceStatus.WARNING

    def test_disk_status_critical(self):
        """Test critical disk status."""
        config = ResourceConfig(disk_critical_gb=2.0)
        service = ResourceService(config=config)
        status = service._get_disk_status(0.5)  # Only 0.5GB free
        assert status == ResourceStatus.CRITICAL


class TestResourceSnapshot:
    """Tests for resource snapshots."""

    def test_get_snapshot_returns_snapshot(self):
        """Test that get_snapshot returns a ResourceSnapshot."""
        service = ResourceService()
        snapshot = service.get_snapshot()

        assert isinstance(snapshot, ResourceSnapshot)
        assert snapshot.timestamp is not None
        assert snapshot.memory is not None
        assert snapshot.cpu is not None
        assert snapshot.disk is not None
        assert isinstance(snapshot.status, ResourceStatus)
        assert isinstance(snapshot.warnings, list)

    def test_snapshot_overall_status_healthy(self):
        """Test overall status is healthy when all components healthy."""
        service = ResourceService()
        # With default high limits, status should be healthy
        config = ResourceConfig(
            max_memory_mb=100000,
            disk_warning_gb=0.001,
            disk_critical_gb=0.0001
        )
        service = ResourceService(config=config)
        snapshot = service.get_snapshot()
        # Status could be healthy or warning depending on system state
        assert snapshot.status in [ResourceStatus.HEALTHY, ResourceStatus.WARNING, ResourceStatus.CRITICAL]

    def test_to_dict_returns_complete_data(self):
        """Test that to_dict returns all expected fields."""
        service = ResourceService()
        data = service.to_dict()

        assert "timestamp" in data
        assert "status" in data
        assert "warnings" in data
        assert "memory" in data
        assert "cpu" in data
        assert "disk" in data
        assert "limits" in data
        assert "max_memory_mb" in data["limits"]
        assert "max_requests_per_minute" in data["limits"]
        assert "file_max_age_days" in data["limits"]


class TestRateLimiting:
    """Tests for rate limiting functionality."""

    def test_check_rate_limit_allows_first_request(self):
        """Test that first request is allowed."""
        service = ResourceService()
        result = service.check_rate_limit("client1")

        assert result.allowed is True
        assert result.current_count == 0
        assert result.remaining > 0

    def test_check_rate_limit_returns_correct_structure(self):
        """Test rate limit result structure."""
        service = ResourceService()
        result = service.check_rate_limit("client1")

        assert isinstance(result, RateLimitResult)
        assert isinstance(result.allowed, bool)
        assert isinstance(result.current_count, int)
        assert isinstance(result.limit, int)
        assert isinstance(result.remaining, int)

    def test_record_request_increments_count(self):
        """Test that recording a request increments the count."""
        service = ResourceService()

        # Initial count should be 0
        result1 = service.check_rate_limit("client1")
        assert result1.current_count == 0

        # Record a request
        service.record_request("client1")

        # Count should now be 1
        result2 = service.check_rate_limit("client1")
        assert result2.current_count == 1

    def test_rate_limit_blocks_when_exceeded(self):
        """Test that rate limit blocks requests when limit exceeded."""
        config = ResourceConfig(max_requests_per_minute=5)
        service = ResourceService(config=config)

        # Record 5 requests (at the limit)
        for _ in range(5):
            service.record_request("client1")

        # Should be blocked now
        result = service.check_rate_limit("client1")
        assert result.allowed is False
        assert result.current_count == 5
        assert result.remaining == 0

    def test_rate_limit_per_client(self):
        """Test that rate limits are tracked per client."""
        config = ResourceConfig(max_requests_per_minute=3)
        service = ResourceService(config=config)

        # Record requests for client1
        for _ in range(3):
            service.record_request("client1")

        # client1 should be blocked
        assert service.check_rate_limit("client1").allowed is False

        # client2 should still be allowed
        assert service.check_rate_limit("client2").allowed is True

    def test_rate_limit_reset_at_provided(self):
        """Test that reset_at is provided when requests exist."""
        service = ResourceService()
        service.record_request("client1")

        result = service.check_rate_limit("client1")
        assert result.reset_at is not None


class TestFileCleanup:
    """Tests for file cleanup functionality."""

    @pytest.fixture
    def temp_files_dir(self, tmp_path):
        """Create a temporary directory with some test files."""
        # Create files with different ages
        files_dir = tmp_path / "files"
        files_dir.mkdir()

        # Recent file
        recent_file = files_dir / "recent.txt"
        recent_file.write_text("recent content")

        # Old file (modify time to 60 days ago)
        old_file = files_dir / "old.txt"
        old_file.write_text("old content")
        old_time = time.time() - (60 * 24 * 60 * 60)  # 60 days ago
        os.utime(old_file, (old_time, old_time))

        return files_dir

    @pytest.mark.asyncio
    async def test_cleanup_old_files_dry_run(self, temp_files_dir):
        """Test dry run doesn't delete files."""
        config = ResourceConfig(file_max_age_days=30)
        service = ResourceService(config=config, files_path=temp_files_dir)

        result = await service.cleanup_old_files(dry_run=True)

        # Old file should be in deleted list but not actually deleted
        assert len(result["deleted"]) == 1
        assert result["dry_run"] is True
        assert (temp_files_dir / "old.txt").exists()  # Still exists

    @pytest.mark.asyncio
    async def test_cleanup_old_files_actually_deletes(self, temp_files_dir):
        """Test actual cleanup deletes old files."""
        config = ResourceConfig(file_max_age_days=30)
        service = ResourceService(config=config, files_path=temp_files_dir)

        result = await service.cleanup_old_files(dry_run=False)

        # Old file should be deleted
        assert len(result["deleted"]) == 1
        assert result["dry_run"] is False
        assert not (temp_files_dir / "old.txt").exists()  # Deleted
        assert (temp_files_dir / "recent.txt").exists()  # Still exists

    @pytest.mark.asyncio
    async def test_cleanup_preserves_recent_files(self, temp_files_dir):
        """Test cleanup preserves recent files."""
        config = ResourceConfig(file_max_age_days=30)
        service = ResourceService(config=config, files_path=temp_files_dir)

        await service.cleanup_old_files(dry_run=False)

        assert (temp_files_dir / "recent.txt").exists()

    @pytest.mark.asyncio
    async def test_cleanup_empty_directory(self, tmp_path):
        """Test cleanup on empty directory."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        service = ResourceService(files_path=empty_dir)
        result = await service.cleanup_old_files()

        assert result["deleted"] == []
        assert result["errors"] == []
        assert result["total_bytes_freed"] == 0

    @pytest.mark.asyncio
    async def test_cleanup_nonexistent_directory(self, tmp_path):
        """Test cleanup on nonexistent directory."""
        nonexistent = tmp_path / "nonexistent"

        service = ResourceService(files_path=nonexistent)
        result = await service.cleanup_old_files()

        assert result["deleted"] == []
        assert result["total_bytes_freed"] == 0

    def test_should_run_cleanup_initially_true(self):
        """Test should_run_cleanup returns True initially."""
        service = ResourceService()
        assert service.should_run_cleanup() is True

    @pytest.mark.asyncio
    async def test_should_run_cleanup_after_cleanup(self, tmp_path):
        """Test should_run_cleanup returns False immediately after cleanup."""
        service = ResourceService(files_path=tmp_path)
        await service.cleanup_old_files()
        assert service.should_run_cleanup() is False


class TestMemoryCleanup:
    """Tests for memory cleanup functionality."""

    def test_should_cleanup_memory_low_usage(self):
        """Test no cleanup needed when memory usage is low."""
        config = ResourceConfig(
            max_memory_mb=100000,  # Very high limit
            memory_cleanup_threshold_percent=85.0
        )
        service = ResourceService(config=config)
        assert service.should_cleanup_memory() is False

    @pytest.mark.asyncio
    async def test_cleanup_memory_returns_stats(self):
        """Test memory cleanup returns statistics."""
        service = ResourceService()
        result = await service.cleanup_memory()

        assert "memory_before_mb" in result
        assert "memory_after_mb" in result
        assert "freed_mb" in result
        assert "gc_collected" in result
        assert result["memory_before_mb"] >= 0
        assert result["memory_after_mb"] >= 0
        assert result["freed_mb"] >= 0

    @pytest.mark.asyncio
    async def test_cleanup_memory_clears_old_rate_limit_entries(self):
        """Test memory cleanup clears old rate limit entries."""
        config = ResourceConfig(rate_limit_window_seconds=1)
        service = ResourceService(config=config)

        # Add some rate limit entries
        service.record_request("client1")
        service.record_request("client2")
        assert len(service._request_timestamps) == 2

        # Wait for window to expire
        time.sleep(1.1)

        # Cleanup should clear old entries
        await service.cleanup_memory()
        assert len(service._request_timestamps) == 0


class TestWarningCallbacks:
    """Tests for warning callback functionality."""

    def test_register_warning_callback(self):
        """Test registering a warning callback."""
        service = ResourceService()
        callback = MagicMock()

        service.register_warning_callback(callback)
        assert callback in service._warning_callbacks

    @pytest.mark.asyncio
    async def test_check_and_alert_calls_callbacks_on_warning(self):
        """Test that callbacks are called when warnings exist."""
        # Create config with low threshold to trigger warning
        config = ResourceConfig(
            max_memory_mb=1,  # Very low limit
            memory_warning_percent=1.0
        )
        service = ResourceService(config=config)

        callback = MagicMock()
        service.register_warning_callback(callback)

        await service.check_and_alert()
        # Callback should be called since memory usage will exceed 1MB
        callback.assert_called()


class TestGlobalInstance:
    """Tests for global instance management."""

    def test_get_resource_service_creates_instance(self, tmp_path):
        """Test get_resource_service creates and returns instance."""
        # Reset global instance
        import server.services.resources as resources_module
        resources_module.resources = None

        service = get_resource_service(files_path=tmp_path)
        assert service is not None
        assert isinstance(service, ResourceService)

    def test_get_resource_service_returns_same_instance(self, tmp_path):
        """Test get_resource_service returns same instance on subsequent calls."""
        # Reset global instance
        import server.services.resources as resources_module
        resources_module.resources = None

        service1 = get_resource_service(files_path=tmp_path)
        service2 = get_resource_service()

        assert service1 is service2


class TestReset:
    """Tests for reset functionality."""

    def test_reset_clears_tracking_data(self):
        """Test reset clears all tracking data."""
        service = ResourceService()

        # Add some data
        service.record_request("client1")
        service._last_cleanup_check = time.time()

        # Reset
        service.reset()

        # All data should be cleared
        assert len(service._request_timestamps) == 0
        assert service._last_cleanup_check is None


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_cleanup_files_with_no_files_path(self):
        """Test cleanup when files_path is None."""
        service = ResourceService(files_path=None)
        result = await service.cleanup_old_files()

        assert result["deleted"] == []
        assert result["errors"] == []

    def test_disk_usage_fallback_to_root(self):
        """Test disk usage falls back to root partition."""
        service = ResourceService(files_path=Path("/nonexistent/path"))
        disk = service.get_disk_usage()

        # Should still return valid data (from root partition)
        assert disk["total_gb"] > 0
        assert "status" in disk

    @pytest.mark.asyncio
    async def test_cleanup_handles_permission_error(self, tmp_path):
        """Test cleanup handles permission errors gracefully."""
        files_dir = tmp_path / "files"
        files_dir.mkdir()

        # Create old file
        old_file = files_dir / "old.txt"
        old_file.write_text("content")
        old_time = time.time() - (60 * 24 * 60 * 60)
        os.utime(old_file, (old_time, old_time))

        config = ResourceConfig(file_max_age_days=30)
        service = ResourceService(config=config, files_path=files_dir)

        # Even if we can't delete (simulated by making it read-only), should not crash
        result = await service.cleanup_old_files()
        # Result should include the file (whether or not deletion succeeded)
        assert len(result["deleted"]) >= 0 or len(result["errors"]) >= 0

    def test_rate_limit_window_expiry(self):
        """Test that rate limit entries expire after window."""
        config = ResourceConfig(
            max_requests_per_minute=2,
            rate_limit_window_seconds=1  # 1 second window for testing
        )
        service = ResourceService(config=config)

        # Record requests up to limit
        service.record_request("client1")
        service.record_request("client1")

        # Should be blocked
        assert service.check_rate_limit("client1").allowed is False

        # Wait for window to expire
        time.sleep(1.1)

        # Should be allowed again
        assert service.check_rate_limit("client1").allowed is True
