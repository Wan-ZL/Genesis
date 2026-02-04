"""Tests for backup and restore service."""
import json
import pytest
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from server.services.backup import (
    BackupService,
    BackupStatus,
    BackupMetadata,
    BackupResult,
    RestorePreview,
    RestoreResult,
)


@pytest.fixture
def temp_memory_dir():
    """Create a temporary memory directory with test data."""
    with tempfile.TemporaryDirectory() as temp_dir:
        memory_dir = Path(temp_dir) / "memory"
        memory_dir.mkdir()

        # Create test database file
        db_path = memory_dir / "conversations.db"
        db_path.write_text("SQLite format 3 - test data")

        # Create test alerts database
        alerts_path = memory_dir / "alerts.db"
        alerts_path.write_text("SQLite format 3 - alerts data")

        # Create test capabilities file
        caps_path = memory_dir / "capabilities.json"
        caps_path.write_text(json.dumps({"tools": ["test_tool"]}))

        # Create test files directory
        files_dir = memory_dir / "files"
        files_dir.mkdir()
        (files_dir / "test_image.png").write_bytes(b"\x89PNG test data")
        (files_dir / "test_doc.pdf").write_bytes(b"%PDF test data")

        yield memory_dir


@pytest.fixture
def backup_service(temp_memory_dir):
    """Create a backup service with temporary directory."""
    return BackupService(temp_memory_dir, max_backups=3)


class TestBackupMetadata:
    """Tests for BackupMetadata dataclass."""

    def test_to_dict(self):
        """Test converting metadata to dictionary."""
        metadata = BackupMetadata(
            version="1.0",
            created_at="2026-02-04T12:00:00",
            assistant_version="0.1.0",
            files_included=["conversations.db", "files/"],
            total_size_bytes=1024,
            checksum="abc123",
        )
        result = metadata.to_dict()

        assert result["version"] == "1.0"
        assert result["created_at"] == "2026-02-04T12:00:00"
        assert result["assistant_version"] == "0.1.0"
        assert result["files_included"] == ["conversations.db", "files/"]
        assert result["total_size_bytes"] == 1024
        assert result["checksum"] == "abc123"

    def test_from_dict(self):
        """Test creating metadata from dictionary."""
        data = {
            "version": "1.0",
            "created_at": "2026-02-04T12:00:00",
            "assistant_version": "0.1.0",
            "files_included": ["conversations.db"],
            "total_size_bytes": 512,
            "checksum": "def456",
        }
        metadata = BackupMetadata.from_dict(data)

        assert metadata.version == "1.0"
        assert metadata.created_at == "2026-02-04T12:00:00"
        assert metadata.assistant_version == "0.1.0"
        assert metadata.files_included == ["conversations.db"]
        assert metadata.total_size_bytes == 512
        assert metadata.checksum == "def456"


class TestBackupCreate:
    """Tests for backup creation."""

    @pytest.mark.asyncio
    async def test_create_backup_success(self, backup_service, temp_memory_dir):
        """Test successful backup creation."""
        result = await backup_service.create_backup()

        assert result.status == BackupStatus.SUCCESS
        assert result.output_path is not None
        assert result.output_path.exists()
        assert result.metadata is not None
        assert result.metadata.version == "1.0"
        assert len(result.metadata.files_included) > 0

    @pytest.mark.asyncio
    async def test_create_backup_custom_output(self, backup_service, temp_memory_dir):
        """Test backup with custom output path."""
        custom_path = temp_memory_dir / "custom_backup.tar.gz"
        result = await backup_service.create_backup(output_path=custom_path)

        assert result.status == BackupStatus.SUCCESS
        assert result.output_path == custom_path
        assert custom_path.exists()

    @pytest.mark.asyncio
    async def test_create_backup_includes_files(self, backup_service, temp_memory_dir):
        """Test that backup includes expected files."""
        result = await backup_service.create_backup()

        assert result.status == BackupStatus.SUCCESS
        assert "conversations.db" in result.metadata.files_included
        assert "files/" in result.metadata.files_included

    @pytest.mark.asyncio
    async def test_create_backup_tarball_valid(self, backup_service, temp_memory_dir):
        """Test that created tarball is valid."""
        result = await backup_service.create_backup()

        assert result.status == BackupStatus.SUCCESS

        # Verify tarball can be opened
        with tarfile.open(result.output_path, "r:gz") as tar:
            members = tar.getnames()
            assert "./backup_metadata.json" in members
            assert "./conversations.db" in members

    @pytest.mark.asyncio
    async def test_create_backup_empty_dir(self):
        """Test backup with empty memory directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            empty_dir = Path(temp_dir) / "empty"
            empty_dir.mkdir()
            service = BackupService(empty_dir)

            result = await service.create_backup()

            assert result.status == BackupStatus.FAILED
            assert "No files to backup" in result.message

    @pytest.mark.asyncio
    async def test_create_backup_with_benchmarks(self, temp_memory_dir):
        """Test backup with benchmarks included."""
        # Create benchmark data
        bench_dir = temp_memory_dir / "benchmarks"
        bench_dir.mkdir()
        (bench_dir / "baseline.json").write_text('{"results": []}')

        service = BackupService(temp_memory_dir)
        result = await service.create_backup(include_benchmarks=True)

        assert result.status == BackupStatus.SUCCESS
        assert "benchmarks/" in result.metadata.files_included

    @pytest.mark.asyncio
    async def test_create_backup_without_benchmarks(self, temp_memory_dir):
        """Test backup excludes benchmarks by default."""
        # Create benchmark data
        bench_dir = temp_memory_dir / "benchmarks"
        bench_dir.mkdir()
        (bench_dir / "baseline.json").write_text('{"results": []}')

        service = BackupService(temp_memory_dir)
        result = await service.create_backup(include_benchmarks=False)

        assert result.status == BackupStatus.SUCCESS
        assert "benchmarks/" not in result.metadata.files_included


class TestBackupRotation:
    """Tests for backup rotation."""

    @pytest.mark.asyncio
    async def test_rotation_keeps_max_backups(self, temp_memory_dir):
        """Test that rotation keeps only max_backups."""
        import time
        service = BackupService(temp_memory_dir, max_backups=3)

        # Create 5 backups with distinct timestamps
        for i in range(5):
            output = temp_memory_dir / "backups" / f"backup_0000000{i}.tar.gz"
            await service.create_backup(output_path=output)
            time.sleep(0.01)  # Ensure distinct mtime

        backups = await service.list_backups()
        assert len(backups) == 3

    @pytest.mark.asyncio
    async def test_rotation_removes_oldest(self, temp_memory_dir):
        """Test that rotation removes oldest backups."""
        import time
        service = BackupService(temp_memory_dir, max_backups=2)

        # Create backups with specific names to ensure unique timestamps
        backup1 = await service.create_backup(
            output_path=temp_memory_dir / "backups" / "backup_00000001.tar.gz"
        )
        time.sleep(0.01)
        backup2 = await service.create_backup(
            output_path=temp_memory_dir / "backups" / "backup_00000002.tar.gz"
        )
        time.sleep(0.01)
        backup3 = await service.create_backup(
            output_path=temp_memory_dir / "backups" / "backup_00000003.tar.gz"
        )

        # Only 2 newest should remain
        backups = await service.list_backups()
        assert len(backups) == 2

        # First backup should be removed
        assert not backup1.output_path.exists()


class TestBackupList:
    """Tests for listing backups."""

    @pytest.mark.asyncio
    async def test_list_backups_empty(self, backup_service):
        """Test listing with no backups."""
        backups = await backup_service.list_backups()
        assert backups == []

    @pytest.mark.asyncio
    async def test_list_backups_with_data(self, backup_service, temp_memory_dir):
        """Test listing with existing backups."""
        import time
        # Create with distinct names
        await backup_service.create_backup(
            output_path=temp_memory_dir / "backups" / "backup_00000001.tar.gz"
        )
        time.sleep(0.01)
        await backup_service.create_backup(
            output_path=temp_memory_dir / "backups" / "backup_00000002.tar.gz"
        )

        backups = await backup_service.list_backups()
        assert len(backups) == 2
        assert "filename" in backups[0]
        assert "size_bytes" in backups[0]
        assert "created_at" in backups[0]

    @pytest.mark.asyncio
    async def test_list_backups_sorted_newest_first(self, backup_service, temp_memory_dir):
        """Test that backups are sorted newest first."""
        import time
        # Create with distinct names and mtimes
        await backup_service.create_backup(
            output_path=temp_memory_dir / "backups" / "backup_00000001.tar.gz"
        )
        time.sleep(0.02)
        await backup_service.create_backup(
            output_path=temp_memory_dir / "backups" / "backup_00000002.tar.gz"
        )

        backups = await backup_service.list_backups()
        # Newest should be first (higher timestamp)
        assert len(backups) == 2
        assert backups[0]["filename"] == "backup_00000002.tar.gz"


class TestBackupVerify:
    """Tests for backup verification."""

    @pytest.mark.asyncio
    async def test_verify_valid_backup(self, backup_service):
        """Test verifying a valid backup."""
        result = await backup_service.create_backup()
        is_valid, message = await backup_service.verify_backup(result.output_path)

        assert is_valid
        assert "verified" in message.lower()

    @pytest.mark.asyncio
    async def test_verify_nonexistent_file(self, backup_service, temp_memory_dir):
        """Test verifying nonexistent file."""
        fake_path = temp_memory_dir / "nonexistent.tar.gz"
        is_valid, message = await backup_service.verify_backup(fake_path)

        assert not is_valid
        assert "not found" in message.lower()

    @pytest.mark.asyncio
    async def test_verify_corrupt_file(self, backup_service, temp_memory_dir):
        """Test verifying corrupt file."""
        corrupt_path = temp_memory_dir / "corrupt.tar.gz"
        corrupt_path.write_bytes(b"not a tarball")

        is_valid, message = await backup_service.verify_backup(corrupt_path)

        assert not is_valid
        assert "corrupt" in message.lower() or "invalid" in message.lower()


class TestRestorePreview:
    """Tests for restore preview."""

    @pytest.mark.asyncio
    async def test_preview_valid_backup(self, backup_service):
        """Test previewing a valid backup."""
        result = await backup_service.create_backup()
        preview = await backup_service.preview_restore(result.output_path)

        assert preview.is_compatible
        assert len(preview.files_to_restore) > 0
        assert preview.metadata is not None

    @pytest.mark.asyncio
    async def test_preview_shows_overwrite_files(self, backup_service, temp_memory_dir):
        """Test that preview shows files that would be overwritten."""
        result = await backup_service.create_backup()

        # Files already exist
        preview = await backup_service.preview_restore(result.output_path)

        assert len(preview.existing_files_to_overwrite) > 0

    @pytest.mark.asyncio
    async def test_preview_nonexistent_file(self, backup_service, temp_memory_dir):
        """Test preview with nonexistent file."""
        fake_path = temp_memory_dir / "nonexistent.tar.gz"

        with pytest.raises(FileNotFoundError):
            await backup_service.preview_restore(fake_path)

    @pytest.mark.asyncio
    async def test_preview_invalid_backup(self, backup_service, temp_memory_dir):
        """Test preview with invalid backup."""
        invalid_path = temp_memory_dir / "invalid.tar.gz"
        invalid_path.write_bytes(b"not a tarball")

        with pytest.raises(ValueError):
            await backup_service.preview_restore(invalid_path)


class TestRestore:
    """Tests for restore functionality."""

    @pytest.mark.asyncio
    async def test_restore_success_force(self, backup_service, temp_memory_dir):
        """Test successful restore with force flag."""
        # Create backup
        backup_result = await backup_service.create_backup()
        assert backup_result.status == BackupStatus.SUCCESS

        # Modify original file
        (temp_memory_dir / "conversations.db").write_text("modified data")

        # Restore
        result = await backup_service.restore(backup_result.output_path, force=True)

        assert result.status == BackupStatus.SUCCESS
        assert len(result.files_restored) > 0

    @pytest.mark.asyncio
    async def test_restore_without_force_fails(self, backup_service, temp_memory_dir):
        """Test restore without force fails when files exist."""
        backup_result = await backup_service.create_backup()

        # Files already exist, should fail without force
        result = await backup_service.restore(backup_result.output_path, force=False)

        assert result.status == BackupStatus.FAILED
        # Check that message mentions overwriting or force
        assert "overwrite" in result.message.lower() or "force" in result.message.lower()

    @pytest.mark.asyncio
    async def test_restore_to_empty_dir(self, temp_memory_dir):
        """Test restore to empty directory."""
        # Create backup
        service = BackupService(temp_memory_dir)
        backup_result = await service.create_backup()

        # Create new empty directory
        with tempfile.TemporaryDirectory() as new_temp:
            new_memory = Path(new_temp) / "memory"
            new_memory.mkdir()
            new_service = BackupService(new_memory)

            result = await new_service.restore(backup_result.output_path)

            assert result.status == BackupStatus.SUCCESS
            assert (new_memory / "conversations.db").exists()

    @pytest.mark.asyncio
    async def test_restore_verifies_first(self, backup_service, temp_memory_dir):
        """Test that restore verifies backup before restoring."""
        corrupt_path = temp_memory_dir / "corrupt.tar.gz"
        corrupt_path.write_bytes(b"not a tarball")

        result = await backup_service.restore(corrupt_path, force=True)

        assert result.status == BackupStatus.FAILED

    @pytest.mark.asyncio
    async def test_restore_preserves_data(self, temp_memory_dir):
        """Test that restore correctly preserves backup data."""
        # Create specific test data
        original_data = "original database content"
        (temp_memory_dir / "conversations.db").write_text(original_data)

        service = BackupService(temp_memory_dir)
        backup_result = await service.create_backup()

        # Modify the file
        (temp_memory_dir / "conversations.db").write_text("modified content")

        # Restore
        result = await service.restore(backup_result.output_path, force=True)

        assert result.status == BackupStatus.SUCCESS
        restored_data = (temp_memory_dir / "conversations.db").read_text()
        assert restored_data == original_data


class TestScheduleConfiguration:
    """Tests for backup schedule configuration."""

    @pytest.mark.asyncio
    async def test_schedule_daily_backup(self, backup_service):
        """Test daily backup schedule configuration."""
        config = await backup_service.schedule_daily_backup(hour=3, minute=0)

        assert config["schedule"]["hour"] == 3
        assert config["schedule"]["minute"] == 0
        assert config["schedule"]["cron"] == "0 3 * * *"

    @pytest.mark.asyncio
    async def test_schedule_custom_time(self, backup_service):
        """Test custom schedule time."""
        config = await backup_service.schedule_daily_backup(hour=14, minute=30)

        assert config["schedule"]["hour"] == 14
        assert config["schedule"]["minute"] == 30
        assert config["schedule"]["cron"] == "30 14 * * *"

    @pytest.mark.asyncio
    async def test_schedule_contains_command(self, backup_service):
        """Test schedule contains correct command."""
        config = await backup_service.schedule_daily_backup()

        assert "backup" in config["command"]
        assert "create" in config["command"]


class TestEdgeCases:
    """Tests for edge cases."""

    @pytest.mark.asyncio
    async def test_backup_with_large_files(self, temp_memory_dir):
        """Test backup with larger files."""
        # Create a 1MB file
        large_file = temp_memory_dir / "files" / "large_file.bin"
        large_file.parent.mkdir(exist_ok=True)
        large_file.write_bytes(b"x" * (1024 * 1024))

        service = BackupService(temp_memory_dir)
        result = await service.create_backup()

        assert result.status == BackupStatus.SUCCESS
        assert result.metadata.total_size_bytes >= 1024 * 1024

    @pytest.mark.asyncio
    async def test_backup_with_special_characters(self, temp_memory_dir):
        """Test backup with special characters in filenames."""
        files_dir = temp_memory_dir / "files"
        files_dir.mkdir(exist_ok=True)
        (files_dir / "file with spaces.txt").write_text("test")
        (files_dir / "file-with-dashes.txt").write_text("test")

        service = BackupService(temp_memory_dir)
        result = await service.create_backup()

        assert result.status == BackupStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_backup_with_nested_directories(self, temp_memory_dir):
        """Test backup with nested directories."""
        nested = temp_memory_dir / "files" / "nested" / "deep"
        nested.mkdir(parents=True)
        (nested / "file.txt").write_text("deep file")

        service = BackupService(temp_memory_dir)
        result = await service.create_backup()

        assert result.status == BackupStatus.SUCCESS

        # Verify nested file is in backup
        with tarfile.open(result.output_path, "r:gz") as tar:
            names = tar.getnames()
            assert any("nested" in name for name in names)

    @pytest.mark.asyncio
    async def test_concurrent_backups(self, backup_service):
        """Test multiple concurrent backups."""
        import asyncio

        # Run 3 concurrent backups
        results = await asyncio.gather(
            backup_service.create_backup(),
            backup_service.create_backup(),
            backup_service.create_backup(),
        )

        # All should succeed (though some may be rotated away)
        success_count = sum(1 for r in results if r.status == BackupStatus.SUCCESS)
        assert success_count == 3


class TestChecksumCalculation:
    """Tests for checksum calculation."""

    def test_calculate_checksum(self, backup_service, temp_memory_dir):
        """Test checksum calculation."""
        test_file = temp_memory_dir / "test.txt"
        test_file.write_text("test content")

        checksum = backup_service._calculate_checksum(test_file)

        assert len(checksum) == 64  # SHA256 hex length
        assert checksum.isalnum()

    def test_checksum_consistency(self, backup_service, temp_memory_dir):
        """Test checksum is consistent for same content."""
        test_file = temp_memory_dir / "test.txt"
        test_file.write_text("consistent content")

        checksum1 = backup_service._calculate_checksum(test_file)
        checksum2 = backup_service._calculate_checksum(test_file)

        assert checksum1 == checksum2

    def test_checksum_different_for_different_content(self, backup_service, temp_memory_dir):
        """Test checksum differs for different content."""
        file1 = temp_memory_dir / "file1.txt"
        file2 = temp_memory_dir / "file2.txt"
        file1.write_text("content 1")
        file2.write_text("content 2")

        checksum1 = backup_service._calculate_checksum(file1)
        checksum2 = backup_service._calculate_checksum(file2)

        assert checksum1 != checksum2
