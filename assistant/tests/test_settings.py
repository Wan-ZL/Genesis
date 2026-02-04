"""Tests for settings service and API."""
import pytest
import tempfile
from pathlib import Path
from httpx import AsyncClient, ASGITransport

from server.services.encryption import CRYPTOGRAPHY_AVAILABLE, is_encrypted


class TestSettingsService:
    """Tests for SettingsService."""

    @pytest.fixture
    def settings_service(self):
        """Create a settings service with temp database."""
        from server.services.settings import SettingsService
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            return SettingsService(Path(f.name))

    @pytest.mark.asyncio
    async def test_get_default_value(self, settings_service):
        """Test getting default value for unset key."""
        value = await settings_service.get("model")
        assert value == "gpt-4o"

    @pytest.mark.asyncio
    async def test_set_and_get(self, settings_service):
        """Test setting and getting a value."""
        await settings_service.set("model", "claude-sonnet-4-20250514")
        value = await settings_service.get("model")
        assert value == "claude-sonnet-4-20250514"

    @pytest.mark.asyncio
    async def test_get_all_defaults(self, settings_service):
        """Test get_all returns defaults for fresh database."""
        settings = await settings_service.get_all()
        assert settings["model"] == "gpt-4o"
        assert settings["openai_api_key"] == ""
        assert settings["anthropic_api_key"] == ""
        assert settings["permission_level"] == 1

    @pytest.mark.asyncio
    async def test_set_multiple(self, settings_service):
        """Test setting multiple values at once."""
        await settings_service.set_multiple({
            "model": "gpt-4o-mini",
            "permission_level": 2
        })
        settings = await settings_service.get_all()
        assert settings["model"] == "gpt-4o-mini"
        assert settings["permission_level"] == "2"  # Stored as string

    @pytest.mark.asyncio
    async def test_set_multiple_ignores_unknown_keys(self, settings_service):
        """Test that unknown keys are ignored."""
        await settings_service.set_multiple({
            "model": "gpt-4o",
            "unknown_key": "some_value"
        })
        settings = await settings_service.get_all()
        assert "unknown_key" not in settings

    def test_mask_api_key_empty(self, settings_service):
        """Test masking empty key."""
        assert settings_service.mask_api_key("") == ""
        assert settings_service.mask_api_key(None) == ""

    def test_mask_api_key_short(self, settings_service):
        """Test masking short key."""
        assert settings_service.mask_api_key("abc") == "****"

    def test_mask_api_key_normal(self, settings_service):
        """Test masking normal key."""
        result = settings_service.mask_api_key("sk-1234567890abcdef")
        assert result == "****cdef"
        assert "1234" not in result

    @pytest.mark.asyncio
    async def test_get_display_settings(self, settings_service):
        """Test display settings with masked keys."""
        await settings_service.set("openai_api_key", "sk-test123456789")
        display = await settings_service.get_display_settings()

        assert display["openai_api_key_set"] is True
        assert display["openai_api_key_masked"] == "****6789"
        assert "sk-test" not in display["openai_api_key_masked"]
        assert display["anthropic_api_key_set"] is False
        assert "available_models" in display

    @pytest.mark.asyncio
    async def test_available_models(self, settings_service):
        """Test available models list."""
        display = await settings_service.get_display_settings()
        models = display["available_models"]

        assert len(models) >= 2
        model_ids = [m["id"] for m in models]
        assert "gpt-4o" in model_ids
        assert "claude-sonnet-4-20250514" in model_ids


class TestSettingsAPI:
    """Tests for settings API endpoints."""

    @pytest.fixture
    def app(self):
        """Create test app."""
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        # Create temp database
        temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)

        with patch('config.DATABASE_PATH', Path(temp_db.name)):
            from server.main import app
            return app

    @pytest.mark.asyncio
    async def test_get_settings(self, app):
        """Test GET /api/settings."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.get("/api/settings")

        assert response.status_code == 200
        data = response.json()
        assert "model" in data
        assert "available_models" in data
        assert "openai_api_key_set" in data
        assert "anthropic_api_key_set" in data

    @pytest.mark.asyncio
    async def test_update_model(self, app):
        """Test updating model selection."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/settings",
                json={"model": "gpt-4o-mini"}
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "updated"
        assert "model" in data["updated_keys"]
        assert data["settings"]["model"] == "gpt-4o-mini"

    @pytest.mark.asyncio
    async def test_update_invalid_model(self, app):
        """Test updating with invalid model fails."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/settings",
                json={"model": "invalid-model"}
            )

        assert response.status_code == 400
        assert "Invalid model" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_update_permission_level(self, app):
        """Test updating permission level."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/settings",
                json={"permission_level": 2}
            )

        assert response.status_code == 200
        data = response.json()
        assert data["settings"]["permission_level"] == 2

    @pytest.mark.asyncio
    async def test_update_invalid_permission(self, app):
        """Test updating with invalid permission fails."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/settings",
                json={"permission_level": 5}
            )

        assert response.status_code == 400
        assert "Permission level" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_update_api_key(self, app):
        """Test updating API key."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/settings",
                json={"openai_api_key": "sk-test123456789"}
            )

        assert response.status_code == 200
        data = response.json()
        assert data["settings"]["openai_api_key_set"] is True
        # Key should be masked in response
        assert data["settings"]["openai_api_key_masked"] == "****6789"

    @pytest.mark.asyncio
    async def test_update_multiple_settings(self, app):
        """Test updating multiple settings at once."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/settings",
                json={
                    "model": "gpt-4o-mini",
                    "permission_level": 1,
                    "openai_api_key": "sk-newkey1234"
                }
            )

        assert response.status_code == 200
        data = response.json()
        assert "model" in data["updated_keys"]
        assert "permission_level" in data["updated_keys"]
        assert "openai_api_key" in data["updated_keys"]


class TestSettingsStartup:
    """Tests for settings loading on startup."""

    @pytest.mark.asyncio
    async def test_load_settings_on_startup(self):
        """Test that load_settings_on_startup loads saved settings."""
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        import config

        # Create temp database
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            temp_db_path = Path(f.name)

        # Save original config values
        original_openai_key = config.OPENAI_API_KEY
        original_model = config.OPENAI_MODEL

        try:
            with patch('config.DATABASE_PATH', temp_db_path):
                # Manually import after patching
                from server.services.settings import SettingsService
                from server.routes import settings as settings_routes

                # Patch the settings service in routes
                settings_routes.settings_service = SettingsService(temp_db_path)

                # Save some settings to database
                await settings_routes.settings_service.set_multiple({
                    "openai_api_key": "sk-startup-test-key",
                    "model": "gpt-4o-mini"
                })

                # Clear config values to simulate fresh start
                config.OPENAI_API_KEY = ""
                config.OPENAI_MODEL = "gpt-4o"

                # Load settings from startup
                await settings_routes.load_settings_on_startup()

                # Verify config was updated
                assert config.OPENAI_API_KEY == "sk-startup-test-key"
                assert config.OPENAI_MODEL == "gpt-4o-mini"

        finally:
            # Restore original values
            config.OPENAI_API_KEY = original_openai_key
            config.OPENAI_MODEL = original_model

    @pytest.mark.asyncio
    async def test_load_settings_handles_empty_database(self):
        """Test that load_settings_on_startup handles empty database gracefully."""
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        # Create temp database
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            temp_db_path = Path(f.name)

        with patch('config.DATABASE_PATH', temp_db_path):
            from server.services.settings import SettingsService
            from server.routes import settings as settings_routes

            # Patch with fresh service
            settings_routes.settings_service = SettingsService(temp_db_path)

            # Should not raise any errors
            await settings_routes.load_settings_on_startup()


@pytest.mark.skipif(not CRYPTOGRAPHY_AVAILABLE, reason="cryptography not installed")
class TestSettingsEncryption:
    """Tests for settings encryption functionality."""

    @pytest.fixture
    def settings_service(self):
        """Create a settings service with temp database."""
        from server.services.settings import SettingsService
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            yield SettingsService(db_path)

    @pytest.mark.asyncio
    async def test_api_keys_encrypted_on_set(self, settings_service):
        """Test that API keys are encrypted when set."""
        await settings_service.set("openai_api_key", "sk-test123456789")

        # Read raw value from database
        import aiosqlite
        async with aiosqlite.connect(settings_service.db_path) as db:
            cursor = await db.execute(
                "SELECT value FROM settings WHERE key = ?",
                ("openai_api_key",)
            )
            row = await cursor.fetchone()

        # Raw value should be encrypted
        assert row is not None
        assert is_encrypted(row[0])

        # But get() should return decrypted value
        value = await settings_service.get("openai_api_key")
        assert value == "sk-test123456789"

    @pytest.mark.asyncio
    async def test_non_sensitive_keys_not_encrypted(self, settings_service):
        """Test that non-sensitive keys are stored as plaintext."""
        await settings_service.set("model", "gpt-4o-mini")

        # Read raw value from database
        import aiosqlite
        async with aiosqlite.connect(settings_service.db_path) as db:
            cursor = await db.execute(
                "SELECT value FROM settings WHERE key = ?",
                ("model",)
            )
            row = await cursor.fetchone()

        # Model should be stored as plaintext
        assert row is not None
        assert row[0] == "gpt-4o-mini"
        assert not is_encrypted(row[0])

    @pytest.mark.asyncio
    async def test_set_multiple_encrypts_sensitive_keys(self, settings_service):
        """Test that set_multiple encrypts sensitive keys."""
        await settings_service.set_multiple({
            "openai_api_key": "sk-test-multi",
            "anthropic_api_key": "sk-ant-multi",
            "model": "gpt-4o"
        })

        # Read raw values
        import aiosqlite
        async with aiosqlite.connect(settings_service.db_path) as db:
            cursor = await db.execute("SELECT key, value FROM settings")
            rows = {row[0]: row[1] for row in await cursor.fetchall()}

        # API keys should be encrypted
        assert is_encrypted(rows["openai_api_key"])
        assert is_encrypted(rows["anthropic_api_key"])
        # Model should not be encrypted
        assert rows["model"] == "gpt-4o"

    @pytest.mark.asyncio
    async def test_get_all_decrypts_sensitive_keys(self, settings_service):
        """Test that get_all decrypts all sensitive keys."""
        await settings_service.set_multiple({
            "openai_api_key": "sk-openai-test",
            "anthropic_api_key": "sk-anthropic-test"
        })

        settings = await settings_service.get_all()

        assert settings["openai_api_key"] == "sk-openai-test"
        assert settings["anthropic_api_key"] == "sk-anthropic-test"

    @pytest.mark.asyncio
    async def test_display_settings_includes_encryption_flag(self, settings_service):
        """Test that display settings shows encryption status."""
        display = await settings_service.get_display_settings()
        assert "encryption_enabled" in display
        assert display["encryption_enabled"] is True

    @pytest.mark.asyncio
    async def test_migrate_to_encrypted(self, settings_service):
        """Test migration of plaintext keys to encrypted."""
        # First, set a plaintext value directly in DB
        import aiosqlite
        from datetime import datetime

        await settings_service._ensure_initialized()
        async with aiosqlite.connect(settings_service.db_path) as db:
            await db.execute(
                """INSERT INTO settings (key, value, updated_at)
                   VALUES (?, ?, ?)""",
                ("openai_api_key", "sk-plaintext-key", datetime.now().isoformat())
            )
            await db.commit()

        # Verify it's not encrypted
        assert not await settings_service.is_key_encrypted("openai_api_key")

        # Run migration
        result = await settings_service.migrate_to_encrypted()

        assert result["success"] is True
        assert "openai_api_key" in result["migrated"]

        # Verify it's now encrypted
        assert await settings_service.is_key_encrypted("openai_api_key")

        # Verify we can still read it
        value = await settings_service.get("openai_api_key")
        assert value == "sk-plaintext-key"

    @pytest.mark.asyncio
    async def test_migrate_skips_already_encrypted(self, settings_service):
        """Test that migration skips already encrypted keys."""
        # Set key normally (will be encrypted)
        await settings_service.set("openai_api_key", "sk-already-encrypted")

        # Run migration
        result = await settings_service.migrate_to_encrypted()

        assert result["success"] is True
        assert "openai_api_key" in result["already_encrypted"]
        assert "openai_api_key" not in result["migrated"]

    @pytest.mark.asyncio
    async def test_migrate_skips_empty_keys(self, settings_service):
        """Test that migration skips empty keys."""
        result = await settings_service.migrate_to_encrypted()

        assert result["success"] is True
        assert "openai_api_key" in result["skipped"]
        assert "anthropic_api_key" in result["skipped"]

    @pytest.mark.asyncio
    async def test_get_encryption_status(self, settings_service):
        """Test getting encryption status for all keys."""
        await settings_service.set("openai_api_key", "sk-test")

        status = await settings_service.get_encryption_status()

        assert status["encryption_available"] is True
        assert status["keys"]["openai_api_key"]["has_value"] is True
        assert status["keys"]["openai_api_key"]["is_encrypted"] is True
        assert status["keys"]["anthropic_api_key"]["has_value"] is False
        assert status["all_encrypted"] is True

    @pytest.mark.asyncio
    async def test_encryption_status_false_for_plaintext(self, settings_service):
        """Test that encryption status shows false for plaintext keys."""
        # Insert plaintext directly
        import aiosqlite
        from datetime import datetime

        await settings_service._ensure_initialized()
        async with aiosqlite.connect(settings_service.db_path) as db:
            await db.execute(
                """INSERT INTO settings (key, value, updated_at)
                   VALUES (?, ?, ?)""",
                ("openai_api_key", "sk-plaintext", datetime.now().isoformat())
            )
            await db.commit()

        status = await settings_service.get_encryption_status()

        assert status["keys"]["openai_api_key"]["has_value"] is True
        assert status["keys"]["openai_api_key"]["is_encrypted"] is False
        assert status["all_encrypted"] is False
