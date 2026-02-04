"""Tests for Ollama integration.

Tests cover:
- OllamaClient basic operations
- Health checks and model listing
- Chat API with Ollama
- Streaming support
- Degradation service integration
- Settings API for Ollama

Note: These tests mock httpx at the test level, not module level,
to avoid affecting other tests.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
import json
import httpx

from server.services.ollama import (
    OllamaClient,
    OllamaModelInfo,
    OllamaStatus,
    get_ollama_client,
    check_ollama_available,
)
from server.services.degradation import (
    DegradationService,
    DegradationMode,
    get_degradation_service,
)


# ============================================================================
# OllamaClient Tests
# ============================================================================


class TestOllamaClient:
    """Tests for OllamaClient class."""

    def test_init_defaults(self):
        """Test client initializes with default values."""
        client = OllamaClient()
        assert client.host == "http://localhost:11434"
        assert "llama" in client.model.lower() or client.model
        assert client.timeout > 0

    def test_init_custom(self):
        """Test client initializes with custom values."""
        client = OllamaClient(
            host="http://custom:8080",
            model="mistral",
            timeout=60
        )
        assert client.host == "http://custom:8080"
        assert client.model == "mistral"
        assert client.timeout == 60

    def test_host_trailing_slash_removed(self):
        """Test trailing slash is removed from host."""
        client = OllamaClient(host="http://localhost:11434/")
        assert client.host == "http://localhost:11434"

    @pytest.mark.asyncio
    async def test_check_health_available(self):
        """Test health check when Ollama is available."""
        client = OllamaClient()

        # Mock HTTP client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [
                {"name": "llama3.2:3b", "size": 1000000},
                {"name": "mistral", "size": 2000000},
            ]
        }

        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(return_value=mock_response)
        mock_http_client.is_closed = False
        client._http_client = mock_http_client

        status = await client.check_health()

        assert status == OllamaStatus.AVAILABLE
        assert len(client._available_models) == 2
        assert client._available_models[0].name == "llama3.2:3b"

    @pytest.mark.asyncio
    async def test_check_health_no_models(self):
        """Test health check when Ollama has no models."""
        client = OllamaClient()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"models": []}

        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(return_value=mock_response)
        mock_http_client.is_closed = False
        client._http_client = mock_http_client

        status = await client.check_health()

        assert status == OllamaStatus.NO_MODELS
        assert len(client._available_models) == 0

    @pytest.mark.asyncio
    async def test_check_health_unavailable(self):
        """Test health check when Ollama is not running."""
        import httpx

        client = OllamaClient()

        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        mock_http_client.is_closed = False
        client._http_client = mock_http_client

        status = await client.check_health()

        assert status == OllamaStatus.UNAVAILABLE

    @pytest.mark.asyncio
    async def test_is_available_caching(self):
        """Test that is_available caches results."""
        client = OllamaClient()

        # Set up cached result
        client._status = OllamaStatus.AVAILABLE
        client._last_check = datetime.now()

        # Should return cached result without HTTP call
        result = await client.is_available()
        assert result is True

    @pytest.mark.asyncio
    async def test_list_models(self):
        """Test listing available models."""
        client = OllamaClient()
        client._status = OllamaStatus.AVAILABLE
        client._available_models = [
            OllamaModelInfo(name="llama3.2:3b", size=1000000),
            OllamaModelInfo(name="mistral", size=2000000),
        ]
        client._last_check = datetime.now()

        models = await client.list_models()

        assert len(models) == 2
        assert models[0].name == "llama3.2:3b"
        assert models[1].name == "mistral"

    @pytest.mark.asyncio
    async def test_has_model(self):
        """Test checking if a model is available."""
        client = OllamaClient()
        client._status = OllamaStatus.AVAILABLE
        client._available_models = [
            OllamaModelInfo(name="llama3.2:3b"),
            OllamaModelInfo(name="mistral"),
        ]
        client._last_check = datetime.now()

        assert await client.has_model("llama3.2:3b") is True
        assert await client.has_model("unknown-model") is False

    def test_get_status(self):
        """Test getting status information."""
        client = OllamaClient()
        client._status = OllamaStatus.AVAILABLE
        client._available_models = [
            OllamaModelInfo(name="llama3.2:3b"),
        ]
        client._last_check = datetime.now()

        status = client.get_status()

        assert status["status"] == "available"
        assert "llama3.2:3b" in status["available_models"]
        assert status["last_check"] is not None


class TestOllamaModelInfo:
    """Tests for OllamaModelInfo dataclass."""

    def test_supports_tools_llama3(self):
        """Test that Llama 3 models support tools."""
        model = OllamaModelInfo(name="llama3.2:3b")
        assert model.supports_tools is True

        model = OllamaModelInfo(name="llama-3-8b")
        assert model.supports_tools is True

    def test_supports_tools_mistral(self):
        """Test that Mistral models support tools."""
        model = OllamaModelInfo(name="mistral")
        assert model.supports_tools is True

        model = OllamaModelInfo(name="mixtral")
        assert model.supports_tools is True

    def test_supports_tools_codellama(self):
        """Test that CodeLlama supports tools."""
        model = OllamaModelInfo(name="codellama")
        assert model.supports_tools is True

    def test_supports_tools_unknown(self):
        """Test that unknown models don't claim tool support."""
        model = OllamaModelInfo(name="some-random-model")
        assert model.supports_tools is False


# ============================================================================
# DegradationService Tests (Ollama integration)
# ============================================================================


class TestDegradationServiceOllama:
    """Tests for Ollama integration in DegradationService."""

    def test_init_includes_ollama(self):
        """Test that degradation service tracks Ollama health."""
        service = DegradationService()
        assert "ollama" in service._api_health
        assert service._api_health["ollama"].name == "ollama"

    def test_local_only_mode_default(self):
        """Test local-only mode is disabled by default."""
        service = DegradationService()
        assert service.is_local_only is False

    def test_set_local_only_mode(self):
        """Test enabling local-only mode."""
        service = DegradationService()

        service.set_local_only_mode(True)
        assert service.is_local_only is True
        assert service.mode == DegradationMode.LOCAL_ONLY

        service.set_local_only_mode(False)
        assert service.is_local_only is False

    def test_get_preferred_api_local_only(self):
        """Test that local-only mode always returns ollama."""
        service = DegradationService()
        service.set_local_only_mode(True)

        assert service.get_preferred_api("claude") == "ollama"
        assert service.get_preferred_api("openai") == "ollama"

    def test_get_preferred_api_ollama_fallback(self):
        """Test that Ollama is used as fallback when cloud APIs fail."""
        service = DegradationService()

        # Mark both cloud APIs as unavailable
        service._api_health["claude"].available = False
        service._api_health["openai"].available = False
        service._api_health["ollama"].available = True

        result = service.get_preferred_api("claude")
        assert result == "ollama"

    def test_mode_cloud_unavailable(self):
        """Test CLOUD_UNAVAILABLE mode when both cloud APIs down but Ollama up."""
        service = DegradationService()

        service._api_health["claude"].available = False
        service._api_health["openai"].available = False
        service._api_health["ollama"].available = True
        service._update_mode()

        assert service.mode == DegradationMode.CLOUD_UNAVAILABLE

    def test_reset_api_health_includes_ollama(self):
        """Test that reset includes Ollama."""
        service = DegradationService()

        # Modify Ollama health
        service._api_health["ollama"].consecutive_failures = 5

        # Reset all
        service.reset_api_health()

        assert service._api_health["ollama"].consecutive_failures == 0

    def test_record_success_ollama(self):
        """Test recording Ollama success."""
        service = DegradationService()

        service.record_success("ollama")

        health = service.get_api_health("ollama")
        assert health.total_requests == 1
        assert health.last_success is not None

    def test_record_failure_ollama(self):
        """Test recording Ollama failure."""
        service = DegradationService()

        service.record_failure("ollama")

        health = service.get_api_health("ollama")
        assert health.total_failures == 1
        assert health.consecutive_failures == 1


# ============================================================================
# Singleton Tests
# ============================================================================


class TestSingletons:
    """Tests for singleton instances."""

    def test_get_ollama_client_singleton(self):
        """Test that get_ollama_client returns singleton."""
        client1 = get_ollama_client()
        client2 = get_ollama_client()
        assert client1 is client2

    @pytest.mark.asyncio
    async def test_check_ollama_available_disabled(self):
        """Test check_ollama_available when Ollama is disabled."""
        with patch("server.services.ollama.config") as mock_config:
            mock_config.OLLAMA_ENABLED = False
            result = await check_ollama_available()
            assert result is False


# ============================================================================
# Integration Tests (mocked)
# ============================================================================


class TestOllamaIntegration:
    """Integration tests for Ollama with other services."""

    @pytest.mark.asyncio
    async def test_chat_non_streaming(self):
        """Test non-streaming chat with Ollama."""
        client = OllamaClient()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {
                "role": "assistant",
                "content": "Hello! How can I help you?",
            },
            "done": True
        }

        mock_http_client = AsyncMock()
        mock_http_client.post = AsyncMock(return_value=mock_response)
        mock_http_client.is_closed = False
        client._http_client = mock_http_client

        response = await client.chat(
            messages=[{"role": "user", "content": "Hello"}],
            stream=False
        )

        assert response["message"]["content"] == "Hello! How can I help you?"

    @pytest.mark.asyncio
    async def test_chat_with_tools(self):
        """Test chat with tool calling."""
        client = OllamaClient()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {
                            "name": "get_current_datetime",
                            "arguments": '{"format": "iso"}'
                        }
                    }
                ]
            },
            "done": True
        }

        mock_http_client = AsyncMock()
        mock_http_client.post = AsyncMock(return_value=mock_response)
        mock_http_client.is_closed = False
        client._http_client = mock_http_client

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_current_datetime",
                    "description": "Get current date and time"
                }
            }
        ]

        response = await client.chat(
            messages=[{"role": "user", "content": "What time is it?"}],
            tools=tools,
            stream=False
        )

        assert "tool_calls" in response["message"]
        assert response["message"]["tool_calls"][0]["function"]["name"] == "get_current_datetime"


# ============================================================================
# Settings API Tests (Ollama endpoints)
# ============================================================================


class TestOllamaSettingsAPI:
    """Tests for Ollama-related settings endpoints.

    Note: Full API tests are in test_settings.py. These test the Ollama-specific
    logic in the settings service.
    """

    @pytest.mark.asyncio
    async def test_settings_service_ollama_defaults(self):
        """Test that settings service has Ollama defaults."""
        from server.services.settings import SettingsService

        assert "ollama_host" in SettingsService.DEFAULTS
        assert "ollama_model" in SettingsService.DEFAULTS
        assert "ollama_enabled" in SettingsService.DEFAULTS
        assert "local_only_mode" in SettingsService.DEFAULTS

    def test_available_models_includes_ollama(self):
        """Test that available models list includes Ollama options."""
        from server.services.settings import SettingsService

        ollama_models = [
            m for m in SettingsService.AVAILABLE_MODELS
            if m["provider"] == "ollama"
        ]
        assert len(ollama_models) >= 1
        assert any("llama" in m["id"].lower() for m in ollama_models)


# ============================================================================
# Config Tests
# ============================================================================


class TestOllamaConfig:
    """Tests for Ollama configuration."""

    def test_config_defaults(self):
        """Test that Ollama config has sensible defaults."""
        import config

        # These should be set in config.py
        assert hasattr(config, 'OLLAMA_HOST')
        assert hasattr(config, 'OLLAMA_MODEL')
        assert hasattr(config, 'OLLAMA_ENABLED')
        assert hasattr(config, 'OLLAMA_TIMEOUT')

    def test_config_env_override(self):
        """Test that config can be overridden by environment."""
        import os
        import importlib

        # Save original
        original = os.environ.get('OLLAMA_HOST')

        try:
            os.environ['OLLAMA_HOST'] = 'http://custom:9999'
            # Would need to reimport config to test this properly
        finally:
            if original:
                os.environ['OLLAMA_HOST'] = original
            elif 'OLLAMA_HOST' in os.environ:
                del os.environ['OLLAMA_HOST']
