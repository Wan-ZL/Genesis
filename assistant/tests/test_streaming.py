"""Tests for streaming chat API endpoints.

Tests cover:
- SSE event format
- Streaming response structure
- Error handling during streaming
- Tool call handling in streams
- Memory persistence after streaming
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path
import sys
import tempfile
import json

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from server.main import app
from server.routes.chat import format_sse, StreamEvent


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


class TestSSEFormatting:
    """Tests for SSE event formatting utilities."""

    def test_format_sse_basic(self):
        """Test basic SSE formatting."""
        result = format_sse("token", {"text": "Hello"})
        assert "event: token\n" in result
        assert 'data: {"text": "Hello"}' in result
        assert result.endswith("\n\n")

    def test_format_sse_complex_data(self):
        """Test SSE formatting with complex data."""
        data = {
            "model": "gpt-4o",
            "provider": "openai",
            "nested": {"key": "value"}
        }
        result = format_sse("start", data)
        assert "event: start\n" in result
        # Parse the data back to verify it's valid JSON
        data_line = result.split("data: ")[1].split("\n")[0]
        parsed = json.loads(data_line)
        assert parsed["model"] == "gpt-4o"
        assert parsed["nested"]["key"] == "value"

    def test_format_sse_unicode(self):
        """Test SSE formatting with unicode characters."""
        result = format_sse("token", {"text": "Hello 世界 🌍"})
        assert "Hello 世界 🌍" in result

    def test_format_sse_special_characters(self):
        """Test SSE formatting with special characters."""
        result = format_sse("token", {"text": "Line1\nLine2\tTabbed"})
        # JSON should properly escape these
        data_line = result.split("data: ")[1].split("\n\n")[0]
        parsed = json.loads(data_line)
        assert parsed["text"] == "Line1\nLine2\tTabbed"


class TestStreamEventTypes:
    """Tests for different stream event types."""

    def test_start_event_format(self):
        """Test start event structure."""
        result = format_sse("start", {"model": "claude-sonnet-4", "provider": "anthropic"})
        assert "event: start" in result
        data = json.loads(result.split("data: ")[1].split("\n")[0])
        assert "model" in data
        assert "provider" in data

    def test_token_event_format(self):
        """Test token event structure."""
        result = format_sse("token", {"text": "Hello"})
        assert "event: token" in result
        data = json.loads(result.split("data: ")[1].split("\n")[0])
        assert data["text"] == "Hello"

    def test_tool_call_event_format(self):
        """Test tool_call event structure."""
        result = format_sse("tool_call", {"name": "web_fetch", "input": {"url": "https://example.com"}})
        assert "event: tool_call" in result
        data = json.loads(result.split("data: ")[1].split("\n")[0])
        assert data["name"] == "web_fetch"
        assert "input" in data

    def test_tool_result_event_format(self):
        """Test tool_result event structure."""
        result = format_sse("tool_result", {"name": "web_fetch", "success": True, "result": "Page content"})
        assert "event: tool_result" in result
        data = json.loads(result.split("data: ")[1].split("\n")[0])
        assert data["success"] is True

    def test_done_event_format(self):
        """Test done event structure."""
        result = format_sse("done", {"total_text": "Full response", "model": "gpt-4o"})
        assert "event: done" in result
        data = json.loads(result.split("data: ")[1].split("\n")[0])
        assert "total_text" in data
        assert "model" in data

    def test_error_event_format(self):
        """Test error event structure."""
        result = format_sse("error", {"message": "API rate limit exceeded"})
        assert "event: error" in result
        data = json.loads(result.split("data: ")[1].split("\n")[0])
        assert "message" in data


class TestStreamingEndpoint:
    """Tests for POST /api/chat/stream endpoint."""

    def test_streaming_endpoint_exists(self, client):
        """Test that the streaming endpoint exists."""
        # Without valid API keys, it should return an error but not 404
        response = client.post("/api/chat/stream", json={"message": "Hello"})
        # Should not be 404 - endpoint exists
        assert response.status_code != 404

    def test_streaming_response_headers(self, client):
        """Test that streaming response has correct headers."""
        with patch('server.routes.chat.get_openai_client') as mock_get_client:
            # Mock the OpenAI client to return a simple stream
            mock_client = MagicMock()

            # Create a mock stream that yields chunks
            def mock_stream():
                chunk = MagicMock()
                chunk.choices = [MagicMock()]
                chunk.choices[0].delta.content = "Hello"
                chunk.choices[0].delta.tool_calls = None
                yield chunk

                # Final chunk
                final_chunk = MagicMock()
                final_chunk.choices = [MagicMock()]
                final_chunk.choices[0].delta.content = None
                final_chunk.choices[0].delta.tool_calls = None
                yield final_chunk

            mock_client.chat.completions.create.return_value = mock_stream()
            mock_get_client.return_value = mock_client

            with patch('server.routes.chat.config') as mock_config:
                mock_config.USE_CLAUDE = False
                mock_config.OPENAI_API_KEY = "test-key"
                mock_config.OPENAI_MODEL = "gpt-4o"
                mock_config.DATABASE_PATH = Path(tempfile.gettempdir()) / "test_stream.db"
                mock_config.FILES_PATH = Path(tempfile.gettempdir()) / "test_files"

                response = client.post("/api/chat/stream", json={"message": "Hello"})

        # Check headers
        assert response.headers.get("content-type", "").startswith("text/event-stream")

    def test_streaming_message_stored_in_memory(self, client):
        """Test that streaming response is stored in memory."""
        with patch('server.routes.chat.memory') as mock_memory:
            mock_memory.add_to_conversation = AsyncMock()
            mock_memory.add_message = AsyncMock()
            mock_memory.get_context_for_api = AsyncMock(return_value=(
                [{"role": "user", "content": "Hello"}],
                {"summarized_count": 0, "verbatim_count": 1, "total_messages": 1}
            ))
            mock_memory._ensure_initialized = AsyncMock()
            mock_memory._ensure_default_conversation = AsyncMock()
            mock_memory.get_conversation = AsyncMock(return_value={"title": "Existing", "messages": [{"role": "user"}]})
            mock_memory.auto_title_conversation = AsyncMock()

            with patch('server.routes.chat.get_openai_client') as mock_get_client:
                mock_client = MagicMock()

                def mock_stream():
                    chunk = MagicMock()
                    chunk.choices = [MagicMock()]
                    chunk.choices[0].delta.content = "World"
                    chunk.choices[0].delta.tool_calls = None
                    yield chunk

                mock_client.chat.completions.create.return_value = mock_stream()
                mock_get_client.return_value = mock_client

                with patch('server.routes.chat.config') as mock_config:
                    mock_config.USE_CLAUDE = False
                    mock_config.OPENAI_API_KEY = "test-key"
                    mock_config.OPENAI_MODEL = "gpt-4o"

                    # Consume the streaming response
                    response = client.post("/api/chat/stream", json={"message": "Hello"})
                    content = response.content.decode()

            # User message should have been stored
            mock_memory.add_message.assert_called()


class TestStreamingWithTools:
    """Tests for streaming with tool calls."""

    def test_tool_call_event_emitted(self):
        """Test that tool calls emit appropriate events."""
        # Test the format of tool call events
        tool_call_event = format_sse("tool_call", {
            "name": "calculate",
            "input": {"expression": "2+2"}
        })

        data = json.loads(tool_call_event.split("data: ")[1].split("\n")[0])
        assert data["name"] == "calculate"
        assert data["input"]["expression"] == "2+2"

    def test_tool_result_success_event(self):
        """Test successful tool result event."""
        result_event = format_sse("tool_result", {
            "name": "calculate",
            "success": True,
            "result": "4"
        })

        data = json.loads(result_event.split("data: ")[1].split("\n")[0])
        assert data["success"] is True
        assert data["result"] == "4"

    def test_tool_result_error_event(self):
        """Test failed tool result event."""
        result_event = format_sse("tool_result", {
            "name": "web_fetch",
            "success": False,
            "error": "Connection timeout"
        })

        data = json.loads(result_event.split("data: ")[1].split("\n")[0])
        assert data["success"] is False
        assert "error" in data

    def test_permission_escalation_event(self):
        """Test permission escalation in tool result."""
        result_event = format_sse("tool_result", {
            "name": "run_shell_command",
            "success": False,
            "permission_escalation": {
                "current_level_name": "LOCAL",
                "required_level_name": "SYSTEM"
            }
        })

        data = json.loads(result_event.split("data: ")[1].split("\n")[0])
        assert "permission_escalation" in data


class TestStreamingEdgeCases:
    """Tests for edge cases in streaming."""

    def test_empty_message_handling(self, client):
        """Test handling of empty messages."""
        response = client.post("/api/chat/stream", json={"message": ""})
        # Should handle gracefully
        assert response.status_code in [200, 400, 422]

    def test_very_long_message(self, client):
        """Test handling of very long messages."""
        long_message = "x" * 10000
        response = client.post("/api/chat/stream", json={"message": long_message})
        # Should accept the request (may fail later due to missing API key)
        assert response.status_code != 413  # Not "payload too large"

    def test_file_ids_parameter(self, client):
        """Test streaming with file_ids parameter."""
        response = client.post("/api/chat/stream", json={
            "message": "Analyze this file",
            "file_ids": ["test-file-id"]
        })
        # Should accept the request format
        assert response.status_code != 422  # Not "unprocessable entity"


class TestStreamEventModel:
    """Tests for StreamEvent Pydantic model."""

    def test_stream_event_valid(self):
        """Test creating valid StreamEvent."""
        event = StreamEvent(event="token", data={"text": "Hello"})
        assert event.event == "token"
        assert event.data["text"] == "Hello"

    def test_stream_event_complex_data(self):
        """Test StreamEvent with complex nested data."""
        event = StreamEvent(
            event="done",
            data={
                "total_text": "Full response",
                "model": "gpt-4o",
                "nested": {"key": ["value1", "value2"]}
            }
        )
        assert event.data["nested"]["key"][0] == "value1"
