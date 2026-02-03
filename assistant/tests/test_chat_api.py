"""Comprehensive tests for chat API endpoints.

Tests cover:
- Conversation creation and retrieval
- Message persistence
- API fallback behavior (Claude -> OpenAI)
- Error handling
- Multimodal message handling
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path
import sys
import tempfile
import os

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from server.main import app


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def mock_openai_response():
    """Mock OpenAI API response."""
    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock()]
    mock_completion.choices[0].message.content = "Hello! I'm a mocked AI assistant."
    return mock_completion


@pytest.fixture
def mock_claude_response():
    """Mock Claude API response."""
    mock_response = MagicMock()
    mock_response.content = [MagicMock()]
    mock_response.content[0].text = "Hello! I'm Claude, a mocked assistant."
    return mock_response


class TestChatEndpoint:
    """Tests for POST /api/chat endpoint."""

    def test_chat_creates_new_conversation(self, client, mock_openai_response):
        """Test that chat creates a new conversation when none specified."""
        with patch('server.routes.chat.get_openai_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_openai_response
            mock_get_client.return_value = mock_client

            # Disable Claude for this test
            with patch('server.routes.chat.config') as mock_config:
                mock_config.USE_CLAUDE = False
                mock_config.OPENAI_API_KEY = "test-key"
                mock_config.OPENAI_MODEL = "gpt-4o-mini"
                mock_config.DATABASE_PATH = Path(tempfile.gettempdir()) / "test_chat.db"
                mock_config.FILES_PATH = Path(tempfile.gettempdir()) / "test_files"

                response = client.post("/api/chat", json={"message": "Hello"})

        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        assert "conversation_id" in data
        assert data["conversation_id"].startswith("conv_")
        assert "timestamp" in data
        assert "model" in data

    def test_chat_uses_existing_conversation(self, client, mock_openai_response):
        """Test that chat uses existing conversation when ID provided."""
        with patch('server.routes.chat.get_openai_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_openai_response
            mock_get_client.return_value = mock_client

            with patch('server.routes.chat.config') as mock_config:
                mock_config.USE_CLAUDE = False
                mock_config.OPENAI_API_KEY = "test-key"
                mock_config.OPENAI_MODEL = "gpt-4o-mini"
                mock_config.DATABASE_PATH = Path(tempfile.gettempdir()) / "test_chat.db"
                mock_config.FILES_PATH = Path(tempfile.gettempdir()) / "test_files"

                # First message creates conversation
                response1 = client.post("/api/chat", json={"message": "Hello"})
                assert response1.status_code == 200
                conv_id = response1.json()["conversation_id"]

                # Second message uses same conversation
                response2 = client.post("/api/chat", json={
                    "message": "How are you?",
                    "conversation_id": conv_id
                })

        assert response2.status_code == 200
        assert response2.json()["conversation_id"] == conv_id

    def test_chat_returns_404_for_invalid_conversation(self, client):
        """Test that chat returns 404 for non-existent conversation."""
        response = client.post("/api/chat", json={
            "message": "Hello",
            "conversation_id": "conv_nonexistent123"
        })
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_chat_falls_back_to_openai_when_claude_fails(self, client, mock_openai_response, mock_claude_response):
        """Test that chat falls back to OpenAI when Claude fails."""
        with patch('server.routes.chat.get_anthropic_client') as mock_claude_client, \
             patch('server.routes.chat.get_openai_client') as mock_openai_client:

            # Claude client raises an exception
            claude_mock = MagicMock()
            claude_mock.messages.create.side_effect = Exception("Claude API error")
            mock_claude_client.return_value = claude_mock

            # OpenAI client works
            openai_mock = MagicMock()
            openai_mock.chat.completions.create.return_value = mock_openai_response
            mock_openai_client.return_value = openai_mock

            with patch('server.routes.chat.config') as mock_config:
                mock_config.USE_CLAUDE = True
                mock_config.ANTHROPIC_API_KEY = "test-key"
                mock_config.CLAUDE_MODEL = "claude-sonnet-4-20250514"
                mock_config.OPENAI_API_KEY = "test-key"
                mock_config.OPENAI_MODEL = "gpt-4o-mini"
                mock_config.DATABASE_PATH = Path(tempfile.gettempdir()) / "test_chat.db"
                mock_config.FILES_PATH = Path(tempfile.gettempdir()) / "test_files"

                response = client.post("/api/chat", json={"message": "Hello"})

        assert response.status_code == 200
        assert response.json()["model"] == "gpt-4o-mini"


class TestConversationsEndpoint:
    """Tests for conversation list/get endpoints."""

    def test_list_conversations(self, client):
        """Test listing all conversations."""
        response = client.get("/api/conversations")
        assert response.status_code == 200
        data = response.json()
        assert "conversations" in data
        assert isinstance(data["conversations"], list)

    def test_get_conversation(self, client, mock_openai_response):
        """Test getting a specific conversation."""
        # First create a conversation
        with patch('server.routes.chat.get_openai_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_openai_response
            mock_get_client.return_value = mock_client

            with patch('server.routes.chat.config') as mock_config:
                mock_config.USE_CLAUDE = False
                mock_config.OPENAI_API_KEY = "test-key"
                mock_config.OPENAI_MODEL = "gpt-4o-mini"
                mock_config.DATABASE_PATH = Path(tempfile.gettempdir()) / "test_chat.db"
                mock_config.FILES_PATH = Path(tempfile.gettempdir()) / "test_files"

                chat_response = client.post("/api/chat", json={"message": "Hello"})
                conv_id = chat_response.json()["conversation_id"]

        # Get the conversation
        response = client.get(f"/api/conversation/{conv_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == conv_id
        assert "messages" in data
        assert len(data["messages"]) >= 1

    def test_get_nonexistent_conversation(self, client):
        """Test getting a non-existent conversation returns 404."""
        response = client.get("/api/conversation/conv_doesnotexist")
        assert response.status_code == 404


class TestFileLoading:
    """Tests for file loading utilities (without calling real APIs)."""

    def test_load_file_for_claude_png(self, tmp_path):
        """Test loading PNG file for Claude API."""
        from server.routes.chat import load_file_for_claude
        import config

        # Create a test PNG file
        file_id = "testfile123"
        png_path = tmp_path / f"{file_id}.png"
        # Minimal valid PNG
        png_data = bytes([
            0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,
            0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,
            0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
            0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4,
            0x89, 0x00, 0x00, 0x00, 0x0A, 0x49, 0x44, 0x41,
            0x54, 0x08, 0xD7, 0x63, 0x00, 0x01, 0x00, 0x00,
            0x05, 0x00, 0x01, 0x0D, 0x0A, 0x2D, 0xB4, 0x00,
            0x00, 0x00, 0x00, 0x49, 0x45, 0x4E, 0x44, 0xAE,
            0x42, 0x60, 0x82
        ])
        png_path.write_bytes(png_data)

        # Mock FILES_PATH
        original_files_path = config.FILES_PATH
        config.FILES_PATH = tmp_path

        try:
            result = load_file_for_claude(file_id)
            assert result is not None
            assert result["type"] == "image"
            assert result["source"]["type"] == "base64"
            assert result["source"]["media_type"] == "image/png"
            assert len(result["source"]["data"]) > 0
        finally:
            config.FILES_PATH = original_files_path

    def test_load_file_for_claude_not_found(self, tmp_path):
        """Test loading non-existent file returns None."""
        from server.routes.chat import load_file_for_claude
        import config

        original_files_path = config.FILES_PATH
        config.FILES_PATH = tmp_path

        try:
            result = load_file_for_claude("nonexistent")
            assert result is None
        finally:
            config.FILES_PATH = original_files_path

    def test_load_file_for_openai_png(self, tmp_path):
        """Test loading PNG file for OpenAI API."""
        from server.routes.chat import load_file_for_openai
        import config

        file_id = "testfile456"
        png_path = tmp_path / f"{file_id}.png"
        png_data = bytes([
            0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,
            0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,
            0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
            0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4,
            0x89, 0x00, 0x00, 0x00, 0x0A, 0x49, 0x44, 0x41,
            0x54, 0x08, 0xD7, 0x63, 0x00, 0x01, 0x00, 0x00,
            0x05, 0x00, 0x01, 0x0D, 0x0A, 0x2D, 0xB4, 0x00,
            0x00, 0x00, 0x00, 0x49, 0x45, 0x4E, 0x44, 0xAE,
            0x42, 0x60, 0x82
        ])
        png_path.write_bytes(png_data)

        original_files_path = config.FILES_PATH
        config.FILES_PATH = tmp_path

        try:
            result = load_file_for_openai(file_id)
            assert result is not None
            assert result["type"] == "image_url"
            assert "image_url" in result
            assert result["image_url"]["url"].startswith("data:image/png;base64,")
        finally:
            config.FILES_PATH = original_files_path


class TestChatModels:
    """Tests for Pydantic models."""

    def test_chat_message_model(self):
        """Test ChatMessage model validation."""
        from server.routes.chat import ChatMessage

        # Valid message
        msg = ChatMessage(message="Hello")
        assert msg.message == "Hello"
        assert msg.conversation_id is None
        assert msg.file_ids is None

        # With optional fields
        msg2 = ChatMessage(
            message="Hello",
            conversation_id="conv_123",
            file_ids=["file1", "file2"]
        )
        assert msg2.conversation_id == "conv_123"
        assert len(msg2.file_ids) == 2

    def test_chat_response_model(self):
        """Test ChatResponse model."""
        from server.routes.chat import ChatResponse

        resp = ChatResponse(
            response="Hi there!",
            conversation_id="conv_123",
            timestamp="2024-01-01T00:00:00",
            model="gpt-4o-mini"
        )
        assert resp.response == "Hi there!"
        assert resp.model == "gpt-4o-mini"


class TestToolIntegration:
    """Tests for tool calling integration."""

    def test_openai_tool_calling(self, client):
        """Test that OpenAI tool calling flow works."""
        # Create mock tool call response followed by final response
        mock_tool_call = MagicMock()
        mock_tool_call.id = "call_123"
        mock_tool_call.function.name = "get_current_datetime"
        mock_tool_call.function.arguments = '{"format": "%Y-%m-%d"}'

        # First response with tool call
        mock_response1 = MagicMock()
        mock_response1.choices = [MagicMock()]
        mock_response1.choices[0].message.content = None
        mock_response1.choices[0].message.tool_calls = [mock_tool_call]

        # Second response after tool execution
        mock_response2 = MagicMock()
        mock_response2.choices = [MagicMock()]
        mock_response2.choices[0].message.content = "The current date is 2026-02-02."
        mock_response2.choices[0].message.tool_calls = None

        with patch('server.routes.chat.get_openai_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.completions.create.side_effect = [mock_response1, mock_response2]
            mock_get_client.return_value = mock_client

            with patch('server.routes.chat.config') as mock_config:
                mock_config.USE_CLAUDE = False
                mock_config.OPENAI_API_KEY = "test-key"
                mock_config.OPENAI_MODEL = "gpt-4o-mini"
                mock_config.DATABASE_PATH = Path(tempfile.gettempdir()) / "test_chat.db"
                mock_config.FILES_PATH = Path(tempfile.gettempdir()) / "test_files"

                response = client.post("/api/chat", json={"message": "What is the date?"})

        assert response.status_code == 200
        data = response.json()
        assert "2026-02-02" in data["response"]

    def test_tool_registry_is_imported(self):
        """Test that tool registry is available in chat module."""
        from server.routes.chat import tool_registry

        # Verify builtin tools are available
        tools = tool_registry.list_tools()
        assert "get_current_datetime" in tools
        assert "calculate" in tools

    def test_openai_tools_format_in_api_call(self, client):
        """Test that tools are passed to OpenAI API in correct format."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello!"
        mock_response.choices[0].message.tool_calls = None

        with patch('server.routes.chat.get_openai_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_get_client.return_value = mock_client

            with patch('server.routes.chat.config') as mock_config:
                mock_config.USE_CLAUDE = False
                mock_config.OPENAI_API_KEY = "test-key"
                mock_config.OPENAI_MODEL = "gpt-4o-mini"
                mock_config.DATABASE_PATH = Path(tempfile.gettempdir()) / "test_chat.db"
                mock_config.FILES_PATH = Path(tempfile.gettempdir()) / "test_files"

                response = client.post("/api/chat", json={"message": "Hello"})

        assert response.status_code == 200
        # Verify tools were passed to the API
        call_kwargs = mock_client.chat.completions.create.call_args
        assert "tools" in call_kwargs.kwargs
        assert len(call_kwargs.kwargs["tools"]) >= 2  # At least get_current_datetime and calculate


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
