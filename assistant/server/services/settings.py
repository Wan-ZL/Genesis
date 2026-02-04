"""Settings service for persisting user configuration."""
import aiosqlite
from datetime import datetime
from pathlib import Path
from typing import Optional
import json
import logging

from server.services.encryption import (
    EncryptionService,
    get_encryption_service,
    init_encryption_service,
    is_encrypted,
    CRYPTOGRAPHY_AVAILABLE
)


logger = logging.getLogger(__name__)


# Keys that contain sensitive data and should be encrypted
SENSITIVE_KEYS = {"openai_api_key", "anthropic_api_key"}


class SettingsService:
    """Service for managing user settings in SQLite.

    Sensitive settings (API keys) are encrypted at rest using AES-256-GCM.
    """

    # Default settings
    DEFAULTS = {
        "openai_api_key": "",
        "anthropic_api_key": "",
        "model": "gpt-4o",  # Default model
        "permission_level": 1,  # LOCAL by default
    }

    # Available models
    AVAILABLE_MODELS = [
        {"id": "gpt-4o", "name": "GPT-4o (OpenAI)", "provider": "openai"},
        {"id": "gpt-4o-mini", "name": "GPT-4o Mini (OpenAI)", "provider": "openai"},
        {"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet 4 (Anthropic)", "provider": "anthropic"},
        {"id": "claude-3-5-haiku-20241022", "name": "Claude 3.5 Haiku (Anthropic)", "provider": "anthropic"},
    ]

    def __init__(self, db_path: Path, encryption_service: Optional[EncryptionService] = None):
        """Initialize settings service.

        Args:
            db_path: Path to SQLite database
            encryption_service: Optional encryption service. If not provided,
                              will use the singleton instance when encrypting.
        """
        self.db_path = db_path
        self._initialized = False
        self._encryption_service = encryption_service
        self._encryption_available = CRYPTOGRAPHY_AVAILABLE

    def _get_encryption_service(self) -> Optional[EncryptionService]:
        """Get encryption service, initializing if needed."""
        if self._encryption_service:
            return self._encryption_service

        if not self._encryption_available:
            return None

        try:
            # Initialize with key file in memory directory
            key_file = self.db_path.parent / ".encryption_key_salt"
            return get_encryption_service(key_file)
        except ImportError:
            self._encryption_available = False
            return None

    def _encrypt_if_sensitive(self, key: str, value: str) -> str:
        """Encrypt value if it's a sensitive key and encryption is available."""
        if key not in SENSITIVE_KEYS or not value:
            return value

        enc_service = self._get_encryption_service()
        if enc_service:
            try:
                return enc_service.encrypt(value)
            except Exception as e:
                logger.warning(f"Encryption failed for {key}: {e}")
                return value
        return value

    def _decrypt_if_sensitive(self, key: str, value: str) -> str:
        """Decrypt value if it's a sensitive key and encrypted."""
        if key not in SENSITIVE_KEYS or not value:
            return value

        if not is_encrypted(value):
            return value

        enc_service = self._get_encryption_service()
        if enc_service:
            try:
                return enc_service.decrypt(value)
            except Exception as e:
                logger.warning(f"Decryption failed for {key}: {e}")
                return ""  # Return empty for failed decryption
        return value

    async def _ensure_initialized(self):
        """Ensure database table exists."""
        if self._initialized:
            return

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP
                )
            """)
            await db.commit()
        self._initialized = True

    async def get(self, key: str) -> Optional[str]:
        """Get a setting value by key."""
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT value FROM settings WHERE key = ?",
                (key,)
            )
            row = await cursor.fetchone()
            if row:
                value = row[0]
                return self._decrypt_if_sensitive(key, value)
            return self.DEFAULTS.get(key)

    async def set(self, key: str, value: str):
        """Set a setting value."""
        await self._ensure_initialized()

        # Encrypt sensitive values
        stored_value = self._encrypt_if_sensitive(key, value)

        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO settings (key, value, updated_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = ?""",
                (key, stored_value, now, stored_value, now)
            )
            await db.commit()

    async def get_all(self) -> dict:
        """Get all settings as a dictionary."""
        await self._ensure_initialized()

        # Start with defaults
        settings = dict(self.DEFAULTS)

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT key, value FROM settings")
            rows = await cursor.fetchall()
            for key, value in rows:
                settings[key] = self._decrypt_if_sensitive(key, value)

        return settings

    async def set_multiple(self, settings: dict):
        """Set multiple settings at once."""
        await self._ensure_initialized()

        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            for key, value in settings.items():
                # Only allow known keys
                if key in self.DEFAULTS:
                    # Encrypt sensitive values
                    stored_value = self._encrypt_if_sensitive(key, str(value))
                    await db.execute(
                        """INSERT INTO settings (key, value, updated_at)
                           VALUES (?, ?, ?)
                           ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = ?""",
                        (key, stored_value, now, stored_value, now)
                    )
            await db.commit()

    def mask_api_key(self, key: str) -> str:
        """Mask an API key for display (show only last 4 chars)."""
        if not key or len(key) < 8:
            return "****" if key else ""
        return "****" + key[-4:]

    async def get_display_settings(self) -> dict:
        """Get settings with masked API keys for display."""
        settings = await self.get_all()
        return {
            "openai_api_key_masked": self.mask_api_key(settings.get("openai_api_key", "")),
            "anthropic_api_key_masked": self.mask_api_key(settings.get("anthropic_api_key", "")),
            "openai_api_key_set": bool(settings.get("openai_api_key")),
            "anthropic_api_key_set": bool(settings.get("anthropic_api_key")),
            "model": settings.get("model", "gpt-4o"),
            "permission_level": int(settings.get("permission_level", 1)),
            "available_models": self.AVAILABLE_MODELS,
            "encryption_enabled": self._encryption_available,
        }

    async def migrate_to_encrypted(self) -> dict:
        """Migrate existing plaintext keys to encrypted format.

        Returns:
            Migration result with counts of migrated keys.
        """
        await self._ensure_initialized()

        if not self._encryption_available:
            return {
                "success": False,
                "error": "Encryption not available (cryptography library not installed)",
                "migrated": [],
                "skipped": [],
                "already_encrypted": []
            }

        enc_service = self._get_encryption_service()
        if not enc_service:
            return {
                "success": False,
                "error": "Could not initialize encryption service",
                "migrated": [],
                "skipped": [],
                "already_encrypted": []
            }

        migrated = []
        skipped = []
        already_encrypted = []

        async with aiosqlite.connect(self.db_path) as db:
            # Get all sensitive keys
            for key in SENSITIVE_KEYS:
                cursor = await db.execute(
                    "SELECT value FROM settings WHERE key = ?",
                    (key,)
                )
                row = await cursor.fetchone()

                if not row or not row[0]:
                    skipped.append(key)
                    continue

                value = row[0]

                if is_encrypted(value):
                    already_encrypted.append(key)
                    continue

                # Encrypt the value
                try:
                    encrypted = enc_service.encrypt(value)
                    now = datetime.now().isoformat()
                    await db.execute(
                        "UPDATE settings SET value = ?, updated_at = ? WHERE key = ?",
                        (encrypted, now, key)
                    )
                    migrated.append(key)
                except Exception as e:
                    logger.error(f"Failed to encrypt {key}: {e}")
                    return {
                        "success": False,
                        "error": f"Failed to encrypt {key}: {e}",
                        "migrated": migrated,
                        "skipped": skipped,
                        "already_encrypted": already_encrypted
                    }

            await db.commit()

        return {
            "success": True,
            "migrated": migrated,
            "skipped": skipped,
            "already_encrypted": already_encrypted
        }

    async def is_key_encrypted(self, key: str) -> bool:
        """Check if a specific key's value is encrypted.

        Args:
            key: The setting key to check

        Returns:
            True if the value is encrypted, False otherwise
        """
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT value FROM settings WHERE key = ?",
                (key,)
            )
            row = await cursor.fetchone()
            if row and row[0]:
                return is_encrypted(row[0])
        return False

    async def get_encryption_status(self) -> dict:
        """Get encryption status for all sensitive keys.

        Returns:
            Dict with encryption status per key and overall status.
        """
        await self._ensure_initialized()

        status = {
            "encryption_available": self._encryption_available,
            "keys": {}
        }

        for key in SENSITIVE_KEYS:
            is_enc = await self.is_key_encrypted(key)
            has_value = bool(await self.get(key))
            status["keys"][key] = {
                "has_value": has_value,
                "is_encrypted": is_enc
            }

        # Overall: all set keys should be encrypted
        all_encrypted = all(
            (not s["has_value"]) or s["is_encrypted"]
            for s in status["keys"].values()
        )
        status["all_encrypted"] = all_encrypted

        return status
