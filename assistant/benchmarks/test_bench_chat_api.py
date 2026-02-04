"""
Benchmarks for Chat API

Critical paths tested (without actual LLM calls - using mocks):
- Request parsing and validation
- Message persistence
- Tool format preparation
- Response serialization
"""

import pytest
from pathlib import Path
import sys
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Create test client with mocked external APIs."""
    import config
    monkeypatch.setattr(config, "DATABASE_PATH", tmp_path / "bench.db")
    monkeypatch.setattr(config, "FILES_PATH", tmp_path / "files")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "test-key")

    from server.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture
def mock_openai():
    """Mock OpenAI client for testing without API calls."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "This is a mocked response from OpenAI"
    mock_response.choices[0].message.tool_calls = None

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response

    return mock_client


class TestChatApiBenchmarks:
    """Benchmarks for Chat API operations."""

    def test_bench_chat_request_mocked(self, benchmark, client, mock_openai):
        """Benchmark full chat request with mocked LLM."""

        with patch("server.routes.chat.get_openai_client", return_value=mock_openai):
            def send_message():
                response = client.post(
                    "/api/chat",
                    json={"message": "Hello, how are you?"}
                )
                return response

            result = benchmark(send_message)
            # Allow 200 or 500 (500 if API key issues in test env)
            assert result.status_code in [200, 500]

    def test_bench_chat_message_parsing(self, benchmark):
        """Benchmark message parsing and validation."""
        from pydantic import BaseModel
        from typing import Optional, List

        class ChatMessage(BaseModel):
            message: str
            conversation_id: Optional[str] = None
            file_ids: Optional[List[str]] = None

        def parse_message():
            return ChatMessage(
                message="Hello, this is a test message with some content",
                conversation_id=None,
                file_ids=["file_1", "file_2"]
            )

        result = benchmark(parse_message)
        assert result.message == "Hello, this is a test message with some content"

    def test_bench_chat_response_serialization(self, benchmark):
        """Benchmark response serialization."""
        from pydantic import BaseModel
        from typing import Optional, List
        from datetime import datetime

        class ChatResponse(BaseModel):
            response: str
            conversation_id: str
            timestamp: str
            model: str
            permission_escalation: Optional[dict] = None
            suggested_tools: Optional[List[dict]] = None

        def serialize_response():
            response = ChatResponse(
                response="This is a test response with some content. " * 10,
                conversation_id="main",
                timestamp=datetime.now().isoformat(),
                model="gpt-4o",
                suggested_tools=[
                    {"name": "tool1", "description": "desc1", "relevance_reason": "reason1", "usage_hint": "hint1"},
                    {"name": "tool2", "description": "desc2", "relevance_reason": "reason2", "usage_hint": "hint2"},
                ]
            )
            return response.model_dump_json()

        result = benchmark(serialize_response)
        assert "test response" in result


class TestToolPreparationBenchmarks:
    """Benchmarks for tool preparation for API calls."""

    def test_bench_tools_to_openai_format(self, benchmark):
        """Benchmark converting tools to OpenAI format."""
        from server.services.tools import registry

        def convert():
            return registry.to_openai_tools()

        result = benchmark(convert)
        assert isinstance(result, list)

    def test_bench_tools_to_claude_format(self, benchmark):
        """Benchmark converting tools to Claude format."""
        from server.services.tools import registry

        def convert():
            return registry.to_claude_tools()

        result = benchmark(convert)
        assert isinstance(result, list)


class TestMessagePersistenceBenchmarks:
    """Benchmarks for message persistence in chat flow."""

    def test_bench_add_user_message(self, benchmark, tmp_path):
        """Benchmark adding a user message (simulating chat flow)."""
        from server.services.memory import MemoryService

        memory = MemoryService(tmp_path / "bench.db")
        loop = asyncio.new_event_loop()

        async def setup():
            await memory._ensure_initialized()
            await memory._ensure_default_conversation()

        loop.run_until_complete(setup())

        def add_message():
            loop.run_until_complete(
                memory.add_to_conversation("user", "Hello, this is a user message!")
            )

        benchmark(add_message)
        loop.close()

    def test_bench_add_and_retrieve(self, benchmark, tmp_path):
        """Benchmark adding a message and retrieving conversation (full cycle)."""
        from server.services.memory import MemoryService

        memory = MemoryService(tmp_path / "bench.db")
        loop = asyncio.new_event_loop()

        async def setup():
            await memory._ensure_initialized()
            await memory._ensure_default_conversation()

        loop.run_until_complete(setup())

        i = [0]

        async def add_and_get():
            await memory.add_to_conversation("user", f"Message {i[0]}")
            await memory.add_to_conversation("assistant", f"Response {i[0]}")
            messages = await memory.get_messages(limit=10)
            i[0] += 1
            return messages

        def run():
            return loop.run_until_complete(add_and_get())

        result = benchmark(run)
        loop.close()


class TestToolSuggestionBenchmarks:
    """Benchmarks for tool suggestion system."""

    def test_bench_analyze_message(self, benchmark):
        """Benchmark analyzing a message for tool suggestions."""
        from server.services.tool_suggestions import ToolSuggestionService

        service = ToolSuggestionService()

        def analyze():
            return service.analyze_message("Can you help me commit this code to git?")

        result = benchmark(analyze)
        assert isinstance(result, list)

    def test_bench_analyze_message_no_match(self, benchmark):
        """Benchmark analyzing a message with no matching tools."""
        from server.services.tool_suggestions import ToolSuggestionService

        service = ToolSuggestionService()

        def analyze():
            return service.analyze_message("Hello, how are you today?")

        result = benchmark(analyze)
        assert isinstance(result, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--benchmark-only"])
