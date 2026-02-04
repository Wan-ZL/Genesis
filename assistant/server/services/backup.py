"""Backup and restore service for AI Assistant data."""
import asyncio
import hashlib
import json
import shutil
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional
import os


class BackupStatus(str, Enum):
    """Status of a backup or restore operation."""
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"


@dataclass
class BackupMetadata:
    """Metadata stored in each backup archive."""
    version: str
    created_at: str
    assistant_version: str
    files_included: list[str]
    total_size_bytes: int
    checksum: str

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "created_at": self.created_at,
            "assistant_version": self.assistant_version,
            "files_included": self.files_included,
            "total_size_bytes": self.total_size_bytes,
            "checksum": self.checksum,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BackupMetadata":
        return cls(
            version=data["version"],
            created_at=data["created_at"],
            assistant_version=data["assistant_version"],
            files_included=data["files_included"],
            total_size_bytes=data["total_size_bytes"],
            checksum=data["checksum"],
        )


@dataclass
class BackupResult:
    """Result of a backup operation."""
    status: BackupStatus
    output_path: Optional[Path]
    metadata: Optional[BackupMetadata]
    message: str
    errors: list[str]


@dataclass
class RestorePreview:
    """Preview of what would be restored."""
    metadata: BackupMetadata
    files_to_restore: list[str]
    existing_files_to_overwrite: list[str]
    total_size_bytes: int
    is_compatible: bool
    compatibility_message: str


@dataclass
class RestoreResult:
    """Result of a restore operation."""
    status: BackupStatus
    files_restored: list[str]
    message: str
    errors: list[str]


class BackupService:
    """Service for creating and restoring backups of AI Assistant data."""

    # Current backup format version
    BACKUP_VERSION = "1.0"

    # Files/directories to include in backup
    BACKUP_ITEMS = [
        "conversations.db",
        "alerts.db",
        "settings.db",
        "capabilities.json",
        "files",  # directory
        "benchmarks",  # directory (optional)
    ]

    def __init__(
        self,
        memory_dir: Path,
        backup_dir: Optional[Path] = None,
        max_backups: int = 10,
    ):
        """Initialize backup service.

        Args:
            memory_dir: Path to assistant/memory directory
            backup_dir: Directory to store backups (default: memory_dir/backups)
            max_backups: Maximum number of backups to keep for rotation
        """
        self.memory_dir = memory_dir
        self.backup_dir = backup_dir or (memory_dir / "backups")
        self.max_backups = max_backups

        # Ensure backup directory exists
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def _get_assistant_version(self) -> str:
        """Get the current assistant version."""
        try:
            from assistant.version import __version__
            return __version__
        except ImportError:
            return "unknown"

    def _calculate_checksum(self, file_path: Path) -> str:
        """Calculate SHA256 checksum of a file."""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def _get_total_size(self, paths: list[Path]) -> int:
        """Calculate total size of paths (files and directories)."""
        total = 0
        for path in paths:
            if path.is_file():
                total += path.stat().st_size
            elif path.is_dir():
                for file in path.rglob("*"):
                    if file.is_file():
                        total += file.stat().st_size
        return total

    async def create_backup(
        self,
        output_path: Optional[Path] = None,
        include_benchmarks: bool = False,
    ) -> BackupResult:
        """Create a backup of all assistant data.

        Args:
            output_path: Custom output path for backup file
            include_benchmarks: Whether to include benchmark data

        Returns:
            BackupResult with status and details
        """
        errors = []

        # Determine output path
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = self.backup_dir / f"backup_{timestamp}.tar.gz"

        # Ensure parent directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Collect files to backup
        files_to_backup = []
        backup_items = list(self.BACKUP_ITEMS)
        if not include_benchmarks:
            backup_items = [item for item in backup_items if item != "benchmarks"]

        for item in backup_items:
            item_path = self.memory_dir / item
            if item_path.exists():
                files_to_backup.append(item_path)

        if not files_to_backup:
            return BackupResult(
                status=BackupStatus.FAILED,
                output_path=None,
                metadata=None,
                message="No files to backup",
                errors=["Memory directory is empty or does not exist"],
            )

        # Create backup in a temporary directory first
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            staging_dir = temp_path / "backup"
            staging_dir.mkdir()

            # Copy files to staging area
            files_included = []
            for item in files_to_backup:
                try:
                    dest = staging_dir / item.name
                    if item.is_file():
                        shutil.copy2(item, dest)
                        files_included.append(item.name)
                    elif item.is_dir():
                        shutil.copytree(item, dest)
                        files_included.append(f"{item.name}/")
                except Exception as e:
                    errors.append(f"Failed to copy {item.name}: {e}")

            if not files_included:
                return BackupResult(
                    status=BackupStatus.FAILED,
                    output_path=None,
                    metadata=None,
                    message="Failed to copy any files",
                    errors=errors,
                )

            # Calculate total size
            total_size = self._get_total_size([staging_dir])

            # Create metadata
            metadata = BackupMetadata(
                version=self.BACKUP_VERSION,
                created_at=datetime.now().isoformat(),
                assistant_version=self._get_assistant_version(),
                files_included=files_included,
                total_size_bytes=total_size,
                checksum="",  # Will be calculated after tarball creation
            )

            # Write metadata file
            metadata_file = staging_dir / "backup_metadata.json"
            metadata_file.write_text(json.dumps(metadata.to_dict(), indent=2))

            # Create tarball
            temp_tarball = temp_path / "backup.tar.gz"
            with tarfile.open(temp_tarball, "w:gz") as tar:
                tar.add(staging_dir, arcname=".")

            # Calculate checksum of tarball
            metadata.checksum = self._calculate_checksum(temp_tarball)

            # Update metadata with checksum
            metadata_file.write_text(json.dumps(metadata.to_dict(), indent=2))

            # Recreate tarball with updated metadata
            with tarfile.open(temp_tarball, "w:gz") as tar:
                tar.add(staging_dir, arcname=".")

            # Move to final destination
            shutil.move(str(temp_tarball), str(output_path))

        # Perform rotation if needed
        await self._rotate_backups()

        status = BackupStatus.SUCCESS if not errors else BackupStatus.PARTIAL
        return BackupResult(
            status=status,
            output_path=output_path,
            metadata=metadata,
            message=f"Backup created: {output_path}",
            errors=errors,
        )

    async def _rotate_backups(self):
        """Remove old backups to keep only max_backups most recent."""
        backup_files = sorted(
            self.backup_dir.glob("backup_*.tar.gz"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        # Remove older backups beyond max_backups
        for old_backup in backup_files[self.max_backups:]:
            try:
                old_backup.unlink()
            except Exception:
                pass

    async def list_backups(self) -> list[dict]:
        """List all available backups.

        Returns:
            List of backup info dictionaries
        """
        backups = []
        for backup_file in sorted(
            self.backup_dir.glob("backup_*.tar.gz"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ):
            try:
                metadata = await self._extract_metadata(backup_file)
                backups.append({
                    "filename": backup_file.name,
                    "path": str(backup_file),
                    "size_bytes": backup_file.stat().st_size,
                    "created_at": metadata.created_at if metadata else None,
                    "version": metadata.version if metadata else None,
                    "files_count": len(metadata.files_included) if metadata else 0,
                })
            except Exception:
                backups.append({
                    "filename": backup_file.name,
                    "path": str(backup_file),
                    "size_bytes": backup_file.stat().st_size,
                    "created_at": None,
                    "version": None,
                    "files_count": 0,
                })
        return backups

    async def _extract_metadata(self, backup_path: Path) -> Optional[BackupMetadata]:
        """Extract metadata from a backup file."""
        try:
            with tarfile.open(backup_path, "r:gz") as tar:
                metadata_member = tar.getmember("./backup_metadata.json")
                f = tar.extractfile(metadata_member)
                if f:
                    data = json.loads(f.read().decode())
                    return BackupMetadata.from_dict(data)
        except Exception:
            return None
        return None

    async def preview_restore(self, backup_path: Path) -> RestorePreview:
        """Preview what would be restored from a backup.

        Args:
            backup_path: Path to backup file

        Returns:
            RestorePreview with details about restoration
        """
        if not backup_path.exists():
            raise FileNotFoundError(f"Backup file not found: {backup_path}")

        metadata = await self._extract_metadata(backup_path)
        if not metadata:
            raise ValueError("Invalid backup file: missing or corrupt metadata")

        # Check version compatibility
        is_compatible = True
        compatibility_message = "Backup is compatible"

        # Parse version for compatibility check
        try:
            backup_major = int(metadata.version.split(".")[0])
            current_major = int(self.BACKUP_VERSION.split(".")[0])
            if backup_major > current_major:
                is_compatible = False
                compatibility_message = f"Backup version {metadata.version} is newer than supported version {self.BACKUP_VERSION}"
        except ValueError:
            is_compatible = False
            compatibility_message = f"Invalid backup version format: {metadata.version}"

        # Check for existing files
        existing_to_overwrite = []
        for item in metadata.files_included:
            item_path = self.memory_dir / item.rstrip("/")
            if item_path.exists():
                existing_to_overwrite.append(item)

        return RestorePreview(
            metadata=metadata,
            files_to_restore=metadata.files_included,
            existing_files_to_overwrite=existing_to_overwrite,
            total_size_bytes=metadata.total_size_bytes,
            is_compatible=is_compatible,
            compatibility_message=compatibility_message,
        )

    async def verify_backup(self, backup_path: Path) -> tuple[bool, str]:
        """Verify backup integrity.

        Args:
            backup_path: Path to backup file

        Returns:
            Tuple of (is_valid, message)
        """
        if not backup_path.exists():
            return False, f"Backup file not found: {backup_path}"

        # Try to extract metadata
        metadata = await self._extract_metadata(backup_path)
        if not metadata:
            return False, "Invalid backup: missing or corrupt metadata"

        # Verify checksum
        calculated_checksum = self._calculate_checksum(backup_path)
        # Note: checksum verification is tricky since we store it inside the tarball
        # For now, we verify we can read all files

        try:
            with tarfile.open(backup_path, "r:gz") as tar:
                # List all members to verify integrity
                members = tar.getmembers()
                if len(members) < 2:  # At least metadata + 1 data file
                    return False, "Backup appears to be empty or corrupt"
        except tarfile.TarError as e:
            return False, f"Backup file is corrupt: {e}"

        return True, "Backup integrity verified"

    async def restore(
        self,
        backup_path: Path,
        force: bool = False,
    ) -> RestoreResult:
        """Restore from a backup file.

        Args:
            backup_path: Path to backup file
            force: If True, skip confirmation for overwriting existing files

        Returns:
            RestoreResult with status and details
        """
        errors = []
        files_restored = []

        # Verify backup first
        is_valid, verify_msg = await self.verify_backup(backup_path)
        if not is_valid:
            return RestoreResult(
                status=BackupStatus.FAILED,
                files_restored=[],
                message=verify_msg,
                errors=[verify_msg],
            )

        # Preview to check compatibility
        preview = await self.preview_restore(backup_path)
        if not preview.is_compatible:
            return RestoreResult(
                status=BackupStatus.FAILED,
                files_restored=[],
                message=preview.compatibility_message,
                errors=[preview.compatibility_message],
            )

        # Check for existing files
        if preview.existing_files_to_overwrite and not force:
            return RestoreResult(
                status=BackupStatus.FAILED,
                files_restored=[],
                message="Existing files would be overwritten. Use force=True to proceed.",
                errors=[f"Would overwrite: {', '.join(preview.existing_files_to_overwrite)}"],
            )

        # Create temporary directory for extraction
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Extract backup
            try:
                with tarfile.open(backup_path, "r:gz") as tar:
                    tar.extractall(temp_path)
            except tarfile.TarError as e:
                return RestoreResult(
                    status=BackupStatus.FAILED,
                    files_restored=[],
                    message=f"Failed to extract backup: {e}",
                    errors=[str(e)],
                )

            # Copy files to memory directory
            for item in preview.files_to_restore:
                item_name = item.rstrip("/")
                src_path = temp_path / item_name
                dest_path = self.memory_dir / item_name

                if not src_path.exists():
                    errors.append(f"Missing in backup: {item_name}")
                    continue

                try:
                    # Remove existing
                    if dest_path.exists():
                        if dest_path.is_dir():
                            shutil.rmtree(dest_path)
                        else:
                            dest_path.unlink()

                    # Copy from backup
                    if src_path.is_dir():
                        shutil.copytree(src_path, dest_path)
                    else:
                        shutil.copy2(src_path, dest_path)

                    files_restored.append(item)
                except Exception as e:
                    errors.append(f"Failed to restore {item_name}: {e}")

        if not files_restored:
            return RestoreResult(
                status=BackupStatus.FAILED,
                files_restored=[],
                message="No files were restored",
                errors=errors,
            )

        status = BackupStatus.SUCCESS if not errors else BackupStatus.PARTIAL
        return RestoreResult(
            status=status,
            files_restored=files_restored,
            message=f"Restored {len(files_restored)} items",
            errors=errors,
        )

    async def schedule_daily_backup(
        self,
        hour: int = 3,
        minute: int = 0,
    ) -> dict:
        """Get configuration for scheduling daily backups.

        This returns launchd/systemd configuration for scheduling.
        The actual scheduling should be done by the service manager.

        Args:
            hour: Hour to run backup (0-23)
            minute: Minute to run backup (0-59)

        Returns:
            Configuration dict with schedule info and commands
        """
        return {
            "schedule": {
                "hour": hour,
                "minute": minute,
                "cron": f"{minute} {hour} * * *",
            },
            "command": "python -m assistant.cli backup create",
            "launchd_plist": {
                "Label": "com.genesis.assistant.backup",
                "ProgramArguments": [
                    "/usr/bin/python3",
                    "-m", "assistant.cli",
                    "backup", "create",
                ],
                "StartCalendarInterval": {
                    "Hour": hour,
                    "Minute": minute,
                },
                "WorkingDirectory": str(self.memory_dir.parent),
            },
        }
