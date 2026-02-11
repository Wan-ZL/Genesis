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

    @pytest.mark.asyncio
    async def test_get_display_settings_includes_repository_settings(self, settings_service):
        """Test that display settings includes repository settings."""
        display = await settings_service.get_display_settings()

        assert "repository_paths" in display
        assert "repository_max_file_size" in display
        # Check defaults
        assert display["repository_paths"] == ""
        assert display["repository_max_file_size"] == 1048576  # 1MB default

    @pytest.mark.asyncio
    async def test_set_and_get_repository_paths(self, settings_service):
        """Test setting and getting repository_paths."""
        await settings_service.set("repository_paths", "/path/one:/path/two")
        value = await settings_service.get("repository_paths")
        assert value == "/path/one:/path/two"

    @pytest.mark.asyncio
    async def test_set_and_get_repository_max_file_size(self, settings_service):
        """Test setting and getting repository_max_file_size."""
        await settings_service.set("repository_max_file_size", "2097152")
        value = await settings_service.get("repository_max_file_size")
        assert value == "2097152"

    @pytest.mark.asyncio
    async def test_display_settings_repository_max_file_size_as_int(self, settings_service):
        """Test that display settings returns repository_max_file_size as integer."""
        await settings_service.set("repository_max_file_size", "5242880")
        display = await settings_service.get_display_settings()
        assert display["repository_max_file_size"] == 5242880
        assert isinstance(display["repository_max_file_size"], int)

    @pytest.mark.asyncio
    async def test_display_settings_falls_back_to_config_module(self, settings_service):
        """Test that display settings falls back to config module when SQLite is empty.

        This tests Issue #27 fix: API keys from .env file should be shown in UI.
        """
        # Create a mock config module with API keys
        class MockConfig:
            OPENAI_API_KEY = "sk-test-openai-key-123456789"
            ANTHROPIC_API_KEY = "sk-ant-test-anthropic-key-987654321"

        # SQLite has no keys, should fall back to config module
        display = await settings_service.get_display_settings(config_module=MockConfig)

        # Should show keys from config module
        assert display["openai_api_key_set"] is True
        assert display["anthropic_api_key_set"] is True
        assert display["openai_api_key_masked"] == "****6789"
        assert display["anthropic_api_key_masked"] == "****4321"

    @pytest.mark.asyncio
    async def test_display_settings_sqlite_overrides_config(self, settings_service):
        """Test that SQLite values take precedence over config module.

        If user sets a key via UI, it should override the .env file value.
        """
        # Create a mock config module with API keys
        class MockConfig:
            OPENAI_API_KEY = "sk-env-key-from-dotenv-file"
            ANTHROPIC_API_KEY = ""

        # Set different key in SQLite
        await settings_service.set("openai_api_key", "sk-sqlite-key-from-ui-settings")

        display = await settings_service.get_display_settings(config_module=MockConfig)

        # Should use SQLite value, not config module
        assert display["openai_api_key_set"] is True
        assert display["openai_api_key_masked"] == "****ings"  # Last 4 of "settings"
        assert "dotenv" not in display["openai_api_key_masked"]

    @pytest.mark.asyncio
    async def test_display_settings_empty_in_both_sources(self, settings_service):
        """Test display when API keys are empty in both SQLite and config."""
        class MockConfig:
            OPENAI_API_KEY = ""
            ANTHROPIC_API_KEY = None

        display = await settings_service.get_display_settings(config_module=MockConfig)

        assert display["openai_api_key_set"] is False
        assert display["anthropic_api_key_set"] is False
        assert display["openai_api_key_masked"] == ""
        assert display["anthropic_api_key_masked"] == ""


class TestSettingsAPI:
    """Tests for settings API endpoints."""

    @pytest.fixture
    def app(self):
        """Create test app with isolated settings service."""
        import tempfile
        from pathlib import Path
        from server.services.settings import SettingsService
        import server.routes.settings as settings_route

        # Create a fresh temp database and settings service for each test
        temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        original_service = settings_route.settings_service
        settings_route.settings_service = SettingsService(Path(temp_db.name))

        from server.main import app
        yield app

        # Restore original service
        settings_route.settings_service = original_service

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

    @pytest.mark.asyncio
    async def test_get_settings_includes_repository_settings(self, app):
        """Test GET /api/settings includes repository settings."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.get("/api/settings")

        assert response.status_code == 200
        data = response.json()
        assert "repository_paths" in data
        assert "repository_max_file_size" in data
        # Check defaults
        assert data["repository_paths"] == ""
        assert data["repository_max_file_size"] == 1048576

    @pytest.mark.asyncio
    async def test_update_repository_paths(self, app):
        """Test updating repository_paths."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/settings",
                json={"repository_paths": "/home/user/projects:/opt/code"}
            )

        assert response.status_code == 200
        data = response.json()
        assert "repository_paths" in data["updated_keys"]
        assert data["settings"]["repository_paths"] == "/home/user/projects:/opt/code"

    @pytest.mark.asyncio
    async def test_update_repository_max_file_size(self, app):
        """Test updating repository_max_file_size."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/settings",
                json={"repository_max_file_size": 5242880}  # 5MB
            )

        assert response.status_code == 200
        data = response.json()
        assert "repository_max_file_size" in data["updated_keys"]
        assert data["settings"]["repository_max_file_size"] == 5242880

    @pytest.mark.asyncio
    async def test_update_repository_max_file_size_too_small(self, app):
        """Test that repository_max_file_size below 1KB is rejected."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/settings",
                json={"repository_max_file_size": 512}  # Less than 1KB
            )

        assert response.status_code == 400
        assert "at least 1024 bytes" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_update_repository_max_file_size_too_large(self, app):
        """Test that repository_max_file_size above 100MB is rejected."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/settings",
                json={"repository_max_file_size": 200 * 1024 * 1024}  # 200MB
            )

        assert response.status_code == 400
        assert "cannot exceed 100MB" in response.json()["detail"]


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


@pytest.mark.skipif(not CRYPTOGRAPHY_AVAILABLE, reason="cryptography not installed")
class TestEncryptedValueLeakPrevention:
    """Tests for Issue #19: Ensure encrypted values never leak to external APIs.

    These tests verify that when decryption fails (e.g., encryption service
    unavailable, wrong key, corrupted data), the code returns empty strings
    instead of leaking the encrypted ENC:v1:... values.
    """

    @pytest.fixture
    def temp_db(self):
        """Create a temp database path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "test.db"

    @pytest.mark.asyncio
    async def test_encrypted_value_not_leaked_when_encryption_unavailable(self, temp_db):
        """Test that encrypted values are not leaked when encryption service fails."""
        from server.services.settings import SettingsService
        from server.services.encryption import ENCRYPTED_PREFIX
        import aiosqlite
        from datetime import datetime

        # Create settings service and store encrypted value
        svc1 = SettingsService(temp_db)
        await svc1.set("openai_api_key", "sk-test-key-12345")

        # Verify it's encrypted in DB
        async with aiosqlite.connect(temp_db) as db:
            cursor = await db.execute(
                "SELECT value FROM settings WHERE key = ?",
                ("openai_api_key",)
            )
            row = await cursor.fetchone()
            assert row[0].startswith(ENCRYPTED_PREFIX)

        # Create a new service WITHOUT encryption (simulating encryption unavailable)
        svc2 = SettingsService(temp_db)
        svc2._encryption_available = False  # Force disable encryption

        # Get should return empty string, NOT the encrypted value
        value = await svc2.get("openai_api_key")
        assert value == "", "Should return empty when decryption unavailable"
        assert not value.startswith(ENCRYPTED_PREFIX), "Should never return encrypted value"

    @pytest.mark.asyncio
    async def test_encrypted_value_not_leaked_in_get_all(self, temp_db):
        """Test that get_all doesn't leak encrypted values when decryption fails."""
        from server.services.settings import SettingsService
        from server.services.encryption import ENCRYPTED_PREFIX
        import aiosqlite
        from datetime import datetime

        # Create and encrypt
        svc1 = SettingsService(temp_db)
        await svc1.set("openai_api_key", "sk-openai-secret")
        await svc1.set("anthropic_api_key", "sk-ant-secret")

        # Create service without encryption
        svc2 = SettingsService(temp_db)
        svc2._encryption_available = False

        settings = await svc2.get_all()

        # Both keys should be empty, not encrypted values
        assert settings["openai_api_key"] == ""
        assert settings["anthropic_api_key"] == ""
        assert not any(
            v.startswith(ENCRYPTED_PREFIX) if isinstance(v, str) else False
            for v in settings.values()
        ), "No encrypted values should leak through get_all()"

    @pytest.mark.asyncio
    async def test_api_key_validation_rejects_encrypted_values(self):
        """Test that _validate_api_key rejects encrypted-looking values."""
        from server.routes.settings import _validate_api_key
        from server.services.encryption import ENCRYPTED_PREFIX

        # Valid keys should pass
        is_valid, reason = _validate_api_key("openai_api_key", "sk-test123")
        assert is_valid is True

        # Encrypted values must be rejected
        encrypted_value = f"{ENCRYPTED_PREFIX}abc123:def456:ghi789"
        is_valid, reason = _validate_api_key("openai_api_key", encrypted_value)
        assert is_valid is False
        assert reason == "encrypted_value"

    @pytest.mark.asyncio
    async def test_startup_validation_detects_decryption_failure(self, temp_db, caplog):
        """Test that startup validation logs error when decryption fails."""
        from server.services.settings import SettingsService
        from server.routes import settings as settings_routes
        from server.services.encryption import ENCRYPTED_PREFIX
        import aiosqlite
        from datetime import datetime
        import logging

        # Create encrypted key with one service
        svc1 = SettingsService(temp_db)
        await svc1.set("openai_api_key", "sk-test-key")

        # Verify it's encrypted
        async with aiosqlite.connect(temp_db) as db:
            cursor = await db.execute(
                "SELECT value FROM settings WHERE key = ?",
                ("openai_api_key",)
            )
            row = await cursor.fetchone()
            assert row[0].startswith(ENCRYPTED_PREFIX)

        # Create new service and disable encryption
        svc2 = SettingsService(temp_db)
        svc2._encryption_available = False
        settings_routes.settings_service = svc2

        # Run startup validation with logging capture
        with caplog.at_level(logging.ERROR):
            await settings_routes.load_settings_on_startup()

        # Should have logged error about decryption failure
        assert any("decrypt" in record.message.lower() for record in caplog.records)

    @pytest.mark.asyncio
    async def test_chat_api_rejects_encrypted_api_key(self):
        """Test that chat API client creation rejects encrypted API keys."""
        from server.routes.chat import _validate_api_key_safe
        from server.services.encryption import ENCRYPTED_PREFIX

        # Valid key should pass
        assert _validate_api_key_safe("sk-valid-key", "OpenAI") is True

        # Empty key should fail
        assert _validate_api_key_safe("", "OpenAI") is False
        assert _validate_api_key_safe(None, "OpenAI") is False

        # Encrypted key must be blocked
        encrypted = f"{ENCRYPTED_PREFIX}salt:nonce:ciphertext"
        assert _validate_api_key_safe(encrypted, "OpenAI") is False

    @pytest.mark.asyncio
    async def test_chat_client_returns_none_for_encrypted_key(self):
        """Test that get_anthropic_client and get_openai_client return None for encrypted keys."""
        from server.routes.chat import get_anthropic_client, get_openai_client
        from server.services.encryption import ENCRYPTED_PREFIX
        from unittest.mock import patch
        import config

        encrypted_key = f"{ENCRYPTED_PREFIX}salt:nonce:cipher"

        # Test with encrypted OpenAI key
        with patch.object(config, 'OPENAI_API_KEY', encrypted_key):
            client = get_openai_client()
            assert client is None, "Should return None for encrypted API key"

        # Test with encrypted Anthropic key
        with patch.object(config, 'ANTHROPIC_API_KEY', encrypted_key):
            client = get_anthropic_client()
            assert client is None, "Should return None for encrypted API key"
