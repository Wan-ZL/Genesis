"""Settings service for persisting user configuration."""
import aiosqlite
from datetime import datetime
from pathlib import Path
from typing import Optional
import json


class SettingsService:
    """Service for managing user settings in SQLite."""

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

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._initialized = False

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
                return row[0]
            return self.DEFAULTS.get(key)

    async def set(self, key: str, value: str):
        """Set a setting value."""
        await self._ensure_initialized()

        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO settings (key, value, updated_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = ?""",
                (key, value, now, value, now)
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
                settings[key] = value

        return settings

    async def set_multiple(self, settings: dict):
        """Set multiple settings at once."""
        await self._ensure_initialized()

        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            for key, value in settings.items():
                # Only allow known keys
                if key in self.DEFAULTS:
                    await db.execute(
                        """INSERT INTO settings (key, value, updated_at)
                           VALUES (?, ?, ?)
                           ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = ?""",
                        (key, str(value), now, str(value), now)
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
        }
