"""Tests for the memory service (SQLite persistence)."""
import pytest
import tempfile
from pathlib import Path
import sys
import asyncio

sys.path.insert(0, str(Path(__file__).parent.parent))

from server.services.memory import MemoryService, DEFAULT_CONVERSATION_ID


@pytest.fixture
def memory_service(tmp_path):
    """Create a memory service with a temporary database."""
    db_path = tmp_path / "test_memory.db"
    service = MemoryService(db_path)
    return service


class TestConversationManagement:
    """Tests for conversation CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_conversation(self, memory_service):
        """Test creating a new conversation."""
        conv_id = await memory_service.create_conversation()
        assert conv_id is not None
        assert conv_id.startswith("conv_")

    @pytest.mark.asyncio
    async def test_create_conversation_with_title(self, memory_service):
        """Test creating a conversation with a custom title."""
        conv_id = await memory_service.create_conversation(title="Test Chat")
        assert conv_id is not None

        conv = await memory_service.get_conversation(conv_id)
        assert conv["title"] == "Test Chat"

    @pytest.mark.asyncio
    async def test_conversation_exists(self, memory_service):
        """Test checking if a conversation exists."""
        conv_id = await memory_service.create_conversation()

        assert await memory_service.conversation_exists(conv_id) is True
        assert await memory_service.conversation_exists("conv_nonexistent") is False

    @pytest.mark.asyncio
    async def test_list_conversations(self, memory_service):
        """Test listing all conversations."""
        # Create multiple conversations
        conv_id1 = await memory_service.create_conversation(title="Chat 1")
        conv_id2 = await memory_service.create_conversation(title="Chat 2")

        conversations = await memory_service.list_conversations()
        assert len(conversations) >= 2

        ids = [c["id"] for c in conversations]
        assert conv_id1 in ids
        assert conv_id2 in ids

    @pytest.mark.asyncio
    async def test_get_conversation(self, memory_service):
        """Test getting a specific conversation."""
        conv_id = await memory_service.create_conversation(title="My Chat")
        await memory_service.add_message(conv_id, "user", "Hello")
        await memory_service.add_message(conv_id, "assistant", "Hi there!")

        conv = await memory_service.get_conversation(conv_id)
        assert conv is not None
        assert conv["id"] == conv_id
        assert conv["title"] == "My Chat"
        assert len(conv["messages"]) == 2
        assert conv["messages"][0]["role"] == "user"
        assert conv["messages"][1]["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_get_nonexistent_conversation(self, memory_service):
        """Test getting a non-existent conversation returns None."""
        conv = await memory_service.get_conversation("conv_doesnotexist")
        assert conv is None


class TestMessageManagement:
    """Tests for message operations."""

    @pytest.mark.asyncio
    async def test_add_message(self, memory_service):
        """Test adding a message to a conversation."""
        conv_id = await memory_service.create_conversation()
        msg_id = await memory_service.add_message(conv_id, "user", "Hello world")

        assert msg_id is not None
        assert msg_id.startswith("msg_")

    @pytest.mark.asyncio
    async def test_get_conversation_messages(self, memory_service):
        """Test getting messages in OpenAI format."""
        conv_id = await memory_service.create_conversation()
        await memory_service.add_message(conv_id, "user", "What is 2+2?")
        await memory_service.add_message(conv_id, "assistant", "2+2 equals 4.")

        messages = await memory_service.get_conversation_messages(conv_id)

        # Should include system message + 2 conversation messages
        assert len(messages) == 3
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "What is 2+2?"
        assert messages[2]["role"] == "assistant"
        assert messages[2]["content"] == "2+2 equals 4."

    @pytest.mark.asyncio
    async def test_remove_last_message(self, memory_service):
        """Test removing the last message from a conversation."""
        conv_id = await memory_service.create_conversation()
        await memory_service.add_message(conv_id, "user", "First message")
        await memory_service.add_message(conv_id, "user", "Second message")

        # Remove last message
        await memory_service.remove_last_message(conv_id)

        conv = await memory_service.get_conversation(conv_id)
        assert len(conv["messages"]) == 1
        assert conv["messages"][0]["content"] == "First message"

    @pytest.mark.asyncio
    async def test_message_ordering(self, memory_service):
        """Test that messages are returned in chronological order."""
        conv_id = await memory_service.create_conversation()

        for i in range(5):
            await memory_service.add_message(conv_id, "user", f"Message {i}")

        messages = await memory_service.get_conversation_messages(conv_id)
        # Skip system message
        for i, msg in enumerate(messages[1:]):
            assert msg["content"] == f"Message {i}"


class TestFileMetadata:
    """Tests for file metadata operations."""

    @pytest.mark.asyncio
    async def test_save_and_get_file_metadata(self, memory_service):
        """Test saving and retrieving file metadata."""
        metadata = {
            "id": "file_123",
            "original_filename": "test.png",
            "stored_filename": "file_123.png",
            "content_type": "image/png",
            "size": 1024,
            "conversation_id": None,
            "uploaded_at": "2024-01-01T00:00:00"
        }

        await memory_service.save_file_metadata(metadata)

        retrieved = await memory_service.get_file_metadata("file_123")
        assert retrieved is not None
        assert retrieved["id"] == "file_123"
        assert retrieved["filename"] == "test.png"
        assert retrieved["content_type"] == "image/png"
        assert retrieved["size"] == 1024

    @pytest.mark.asyncio
    async def test_list_files(self, memory_service):
        """Test listing uploaded files."""
        metadata = {
            "id": "file_abc",
            "original_filename": "image.jpg",
            "stored_filename": "file_abc.jpg",
            "content_type": "image/jpeg",
            "size": 2048,
            "conversation_id": None,
            "uploaded_at": "2024-01-01T00:00:00"
        }

        await memory_service.save_file_metadata(metadata)

        files = await memory_service.list_files()
        assert len(files) >= 1
        assert any(f["id"] == "file_abc" for f in files)

    @pytest.mark.asyncio
    async def test_list_files_by_conversation(self, memory_service):
        """Test listing files filtered by conversation."""
        conv_id = await memory_service.create_conversation()

        metadata1 = {
            "id": "file_conv1",
            "original_filename": "doc1.pdf",
            "stored_filename": "file_conv1.pdf",
            "content_type": "application/pdf",
            "size": 1000,
            "conversation_id": conv_id,
            "uploaded_at": "2024-01-01T00:00:00"
        }
        metadata2 = {
            "id": "file_other",
            "original_filename": "doc2.pdf",
            "stored_filename": "file_other.pdf",
            "content_type": "application/pdf",
            "size": 2000,
            "conversation_id": "conv_different",
            "uploaded_at": "2024-01-01T00:00:00"
        }

        await memory_service.save_file_metadata(metadata1)
        await memory_service.save_file_metadata(metadata2)

        files = await memory_service.list_files(conversation_id=conv_id)
        assert len(files) == 1
        assert files[0]["id"] == "file_conv1"

    @pytest.mark.asyncio
    async def test_get_nonexistent_file(self, memory_service):
        """Test getting non-existent file returns None."""
        result = await memory_service.get_file_metadata("nonexistent")
        assert result is None


class TestDatabaseInitialization:
    """Tests for database initialization."""

    @pytest.mark.asyncio
    async def test_multiple_operations_initialize_once(self, memory_service):
        """Test that database initializes only once."""
        # Multiple operations should not fail
        await memory_service.create_conversation()
        await memory_service.create_conversation()
        await memory_service.list_conversations()

        assert memory_service._initialized is True


class TestMessageSearch:
    """Tests for message search functionality."""

    @pytest.mark.asyncio
    async def test_search_finds_matching_messages(self, memory_service):
        """Test that search finds messages containing the query."""
        conv_id = await memory_service.create_conversation(title="Test Chat")
        await memory_service.add_message(conv_id, "user", "Hello world")
        await memory_service.add_message(conv_id, "assistant", "Hi there!")
        await memory_service.add_message(conv_id, "user", "Tell me about Python programming")
        await memory_service.add_message(conv_id, "assistant", "Python is a great language!")

        results = await memory_service.search_messages("Python")
        assert len(results) == 2
        assert all("python" in r["content"].lower() for r in results)

    @pytest.mark.asyncio
    async def test_search_case_insensitive(self, memory_service):
        """Test that search is case-insensitive."""
        conv_id = await memory_service.create_conversation()
        await memory_service.add_message(conv_id, "user", "HELLO WORLD")
        await memory_service.add_message(conv_id, "user", "hello world")
        await memory_service.add_message(conv_id, "user", "Hello World")

        results = await memory_service.search_messages("hello")
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_search_with_conversation_filter(self, memory_service):
        """Test that search can filter by conversation."""
        conv_id1 = await memory_service.create_conversation(title="Chat 1")
        conv_id2 = await memory_service.create_conversation(title="Chat 2")

        await memory_service.add_message(conv_id1, "user", "Test message in chat 1")
        await memory_service.add_message(conv_id2, "user", "Test message in chat 2")

        # Search all
        all_results = await memory_service.search_messages("Test message")
        assert len(all_results) == 2

        # Search specific conversation
        filtered_results = await memory_service.search_messages("Test message", conversation_id=conv_id1)
        assert len(filtered_results) == 1
        assert filtered_results[0]["conversation_id"] == conv_id1

    @pytest.mark.asyncio
    async def test_search_returns_empty_for_no_matches(self, memory_service):
        """Test that search returns empty list when no matches."""
        conv_id = await memory_service.create_conversation()
        await memory_service.add_message(conv_id, "user", "Hello world")

        results = await memory_service.search_messages("xyznonexistent")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_respects_limit(self, memory_service):
        """Test that search respects the limit parameter."""
        conv_id = await memory_service.create_conversation()
        for i in range(10):
            await memory_service.add_message(conv_id, "user", f"Test message {i}")

        results = await memory_service.search_messages("Test message", limit=3)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_search_respects_offset(self, memory_service):
        """Test that search respects the offset parameter for pagination."""
        conv_id = await memory_service.create_conversation()
        for i in range(10):
            await memory_service.add_message(conv_id, "user", f"Unique keyword msg{i}")

        all_results = await memory_service.search_messages("Unique keyword")
        offset_results = await memory_service.search_messages("Unique keyword", offset=5)

        assert len(all_results) == 10
        assert len(offset_results) == 5

    @pytest.mark.asyncio
    async def test_search_includes_snippet(self, memory_service):
        """Test that search results include a snippet."""
        conv_id = await memory_service.create_conversation()
        await memory_service.add_message(conv_id, "user", "This is a long message about Python programming and how it helps with data science")

        results = await memory_service.search_messages("Python")
        assert len(results) == 1
        assert "snippet" in results[0]
        assert "Python" in results[0]["snippet"]

    @pytest.mark.asyncio
    async def test_search_includes_conversation_title(self, memory_service):
        """Test that search results include conversation title."""
        conv_id = await memory_service.create_conversation(title="My Special Chat")
        await memory_service.add_message(conv_id, "user", "Important message")

        results = await memory_service.search_messages("Important")
        assert len(results) == 1
        assert results[0]["conversation_title"] == "My Special Chat"


class TestMessageCount:
    """Tests for message count functionality."""

    @pytest.mark.asyncio
    async def test_get_message_count(self, memory_service):
        """Test getting total message count."""
        conv_id1 = await memory_service.create_conversation()
        conv_id2 = await memory_service.create_conversation()

        await memory_service.add_message(conv_id1, "user", "Msg 1")
        await memory_service.add_message(conv_id1, "user", "Msg 2")
        await memory_service.add_message(conv_id2, "user", "Msg 3")

        count = await memory_service.get_message_count()
        assert count == 3

    @pytest.mark.asyncio
    async def test_get_message_count_empty(self, memory_service):
        """Test message count is zero for empty database."""
        count = await memory_service.get_message_count()
        assert count == 0


class TestSingleConversation:
    """Tests for single infinite conversation model."""

    @pytest.mark.asyncio
    async def test_add_to_conversation(self, memory_service):
        """Test adding messages to the single conversation."""
        msg_id = await memory_service.add_to_conversation("user", "Hello")
        assert msg_id is not None
        assert msg_id.startswith("msg_")

        # Verify it's in the default conversation
        conv = await memory_service.get_conversation(DEFAULT_CONVERSATION_ID)
        assert conv is not None
        assert len(conv["messages"]) == 1
        assert conv["messages"][0]["content"] == "Hello"

    @pytest.mark.asyncio
    async def test_get_messages(self, memory_service):
        """Test getting messages from the single conversation."""
        await memory_service.add_to_conversation("user", "First message")
        await memory_service.add_to_conversation("assistant", "Response")
        await memory_service.add_to_conversation("user", "Second message")

        messages = await memory_service.get_messages()

        # Should include system message + 3 conversation messages
        assert len(messages) == 4
        assert messages[0]["role"] == "system"
        assert messages[1]["content"] == "First message"
        assert messages[2]["content"] == "Response"
        assert messages[3]["content"] == "Second message"

    @pytest.mark.asyncio
    async def test_get_messages_with_limit(self, memory_service):
        """Test getting limited number of recent messages."""
        for i in range(10):
            await memory_service.add_to_conversation("user", f"Message {i}")

        # Get only last 3 messages
        messages = await memory_service.get_messages(limit=3)

        # Should have system + 3 messages
        assert len(messages) == 4
        assert messages[0]["role"] == "system"
        # Should be the last 3 messages in chronological order
        assert messages[1]["content"] == "Message 7"
        assert messages[2]["content"] == "Message 8"
        assert messages[3]["content"] == "Message 9"

    @pytest.mark.asyncio
    async def test_remove_last_message_from_conversation(self, memory_service):
        """Test removing the last message from single conversation."""
        await memory_service.add_to_conversation("user", "First")
        await memory_service.add_to_conversation("user", "Second")

        await memory_service.remove_last_message_from_conversation()

        messages = await memory_service.get_messages()
        # System + 1 message
        assert len(messages) == 2
        assert messages[1]["content"] == "First"

    @pytest.mark.asyncio
    async def test_default_conversation_auto_created(self, memory_service):
        """Test that default conversation is created automatically."""
        # Before any operation, default conversation shouldn't exist
        exists = await memory_service.conversation_exists(DEFAULT_CONVERSATION_ID)
        assert exists is False

        # After using single conversation API, it should exist
        await memory_service.add_to_conversation("user", "Test")
        exists = await memory_service.conversation_exists(DEFAULT_CONVERSATION_ID)
        assert exists is True

    @pytest.mark.asyncio
    async def test_default_conversation_id_is_main(self, memory_service):
        """Test that the default conversation ID is 'main'."""
        assert DEFAULT_CONVERSATION_ID == "main"


class TestContextSummarization:
    """Tests for context summarization functionality (Issue #4)."""

    @pytest.mark.asyncio
    async def test_get_context_few_messages_no_summary(self, memory_service):
        """Test that few messages returns all verbatim without summarization."""
        # Add fewer than RECENT_MESSAGES_VERBATIM messages
        for i in range(5):
            await memory_service.add_to_conversation("user", f"Message {i}")
            await memory_service.add_to_conversation("assistant", f"Response {i}")

        messages, metadata = await memory_service.get_context_for_api()

        # Should have system + 10 messages (5 pairs)
        assert len(messages) == 11
        assert metadata["total_messages"] == 10
        assert metadata["summarized_count"] == 0
        assert metadata["verbatim_count"] == 10

    @pytest.mark.asyncio
    async def test_get_context_many_messages_uses_summary(self, memory_service, monkeypatch):
        """Test that many messages triggers summarization."""
        # Set a low threshold for testing
        monkeypatch.setattr("config.RECENT_MESSAGES_VERBATIM", 5)
        monkeypatch.setattr("config.MESSAGES_PER_SUMMARY_BATCH", 3)
        monkeypatch.setattr("config.MAX_SUMMARY_LENGTH", 200)

        # Add more messages than threshold
        for i in range(15):
            await memory_service.add_to_conversation("user", f"User message {i}")

        messages, metadata = await memory_service.get_context_for_api()

        assert metadata["total_messages"] == 15
        assert metadata["summarized_count"] == 10  # 15 - 5 recent
        assert metadata["verbatim_count"] == 5

        # Check that we have system prompt, summary context, and recent messages
        # System prompt is first
        assert messages[0]["role"] == "system"
        # Recent verbatim messages should be last 5
        verbatim_messages = [m for m in messages if m["role"] in ("user", "assistant") and
                            not m.get("content", "").startswith("[Previous conversation")]
        assert len(verbatim_messages) >= 5

    @pytest.mark.asyncio
    async def test_summaries_are_stored(self, memory_service, monkeypatch):
        """Test that summaries are persisted in database."""
        monkeypatch.setattr("config.RECENT_MESSAGES_VERBATIM", 5)
        monkeypatch.setattr("config.MESSAGES_PER_SUMMARY_BATCH", 3)

        for i in range(15):
            await memory_service.add_to_conversation("user", f"Message {i}")

        # First call creates summaries
        await memory_service.get_context_for_api()

        # Check summaries are stored
        summaries = await memory_service.get_summaries()
        assert len(summaries) > 0

        # Each summary should have required fields
        for s in summaries:
            assert "id" in s
            assert "summary" in s
            assert "message_count" in s

    @pytest.mark.asyncio
    async def test_summaries_reused_on_subsequent_calls(self, memory_service, monkeypatch):
        """Test that existing summaries are reused."""
        monkeypatch.setattr("config.RECENT_MESSAGES_VERBATIM", 5)
        monkeypatch.setattr("config.MESSAGES_PER_SUMMARY_BATCH", 3)

        for i in range(15):
            await memory_service.add_to_conversation("user", f"Message {i}")

        # First call creates summaries
        _, meta1 = await memory_service.get_context_for_api()
        summaries_after_first = await memory_service.get_summaries()

        # Second call should reuse summaries
        _, meta2 = await memory_service.get_context_for_api()
        summaries_after_second = await memory_service.get_summaries()

        # Should have same number of summaries (not creating duplicates)
        assert len(summaries_after_second) == len(summaries_after_first)

    @pytest.mark.asyncio
    async def test_clear_summaries(self, memory_service, monkeypatch):
        """Test clearing all summaries."""
        monkeypatch.setattr("config.RECENT_MESSAGES_VERBATIM", 5)
        monkeypatch.setattr("config.MESSAGES_PER_SUMMARY_BATCH", 3)

        for i in range(15):
            await memory_service.add_to_conversation("user", f"Message {i}")

        await memory_service.get_context_for_api()
        assert len(await memory_service.get_summaries()) > 0

        await memory_service.clear_summaries()
        assert len(await memory_service.get_summaries()) == 0

    @pytest.mark.asyncio
    async def test_summary_includes_message_content(self, memory_service, monkeypatch):
        """Test that summaries include content from original messages."""
        monkeypatch.setattr("config.RECENT_MESSAGES_VERBATIM", 2)
        monkeypatch.setattr("config.MESSAGES_PER_SUMMARY_BATCH", 3)

        # Add messages with identifiable content
        await memory_service.add_to_conversation("user", "UNIQUE_MARKER_ABC")
        await memory_service.add_to_conversation("assistant", "Response to marker")
        await memory_service.add_to_conversation("user", "Follow up")
        await memory_service.add_to_conversation("user", "Recent 1")
        await memory_service.add_to_conversation("user", "Recent 2")

        await memory_service.get_context_for_api()
        summaries = await memory_service.get_summaries()

        # At least one summary should contain reference to our unique content
        all_summaries_text = " ".join(s["summary"] for s in summaries)
        assert "UNIQUE_MARKER_ABC" in all_summaries_text or "U:" in all_summaries_text

    @pytest.mark.asyncio
    async def test_original_messages_preserved_after_summarization(self, memory_service, monkeypatch):
        """Test that original messages are preserved (Issue #4 requirement)."""
        monkeypatch.setattr("config.RECENT_MESSAGES_VERBATIM", 5)
        monkeypatch.setattr("config.MESSAGES_PER_SUMMARY_BATCH", 3)

        for i in range(15):
            await memory_service.add_to_conversation("user", f"Original message {i}")

        # Trigger summarization
        await memory_service.get_context_for_api()

        # Original messages should still be searchable
        results = await memory_service.search_messages("Original message 0")
        assert len(results) == 1
        assert "Original message 0" in results[0]["content"]

        # All messages should be in get_messages without limit
        all_messages = await memory_service.get_messages()
        assert len(all_messages) == 16  # 15 + system

    @pytest.mark.asyncio
    async def test_context_includes_summary_prefix(self, memory_service, monkeypatch):
        """Test that context includes a summary indicator."""
        monkeypatch.setattr("config.RECENT_MESSAGES_VERBATIM", 5)
        monkeypatch.setattr("config.MESSAGES_PER_SUMMARY_BATCH", 3)

        for i in range(15):
            await memory_service.add_to_conversation("user", f"Message {i}")

        messages, _ = await memory_service.get_context_for_api()

        # Should have a message with summary prefix
        summary_messages = [m for m in messages if "[Previous conversation summary" in m.get("content", "")]
        assert len(summary_messages) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
