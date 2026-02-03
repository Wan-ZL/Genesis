"""Tests for settings service and API."""
import pytest
import tempfile
from pathlib import Path
from httpx import AsyncClient, ASGITransport


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
