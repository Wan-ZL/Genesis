"""Tests for multi-conversation support (Issue #32).

Tests cover:
- Conversation creation, listing, deletion, renaming
- Auto-title generation from first user message
- List conversations with preview snippets
- Conversation management API endpoints
- Backward compatibility with "main" conversation
"""
import pytest
import sys
from pathlib import Path
from unittest.mock import patch, AsyncMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from server.services.memory import MemoryService, DEFAULT_CONVERSATION_ID


@pytest.fixture
def memory_service(tmp_path):
    """Create a memory service with a temporary database."""
    db_path = tmp_path / "test_conversations.db"
    service = MemoryService(db_path)
    return service


class TestConversationCreation:
    """Tests for creating new conversations."""

    @pytest.mark.asyncio
    async def test_create_conversation_returns_id(self, memory_service):
        """Test that creating a conversation returns a valid ID."""
        conv_id = await memory_service.create_conversation()
        assert conv_id is not None
        assert conv_id.startswith("conv_")

    @pytest.mark.asyncio
    async def test_create_conversation_with_title(self, memory_service):
        """Test creating a conversation with a specific title."""
        conv_id = await memory_service.create_conversation(title="My Chat")
        conv = await memory_service.get_conversation(conv_id)
        assert conv["title"] == "My Chat"

    @pytest.mark.asyncio
    async def test_create_conversation_default_title(self, memory_service):
        """Test creating a conversation with default title."""
        conv_id = await memory_service.create_conversation()
        conv = await memory_service.get_conversation(conv_id)
        assert conv["title"] == "New conversation"

    @pytest.mark.asyncio
    async def test_create_multiple_conversations(self, memory_service):
        """Test creating multiple conversations."""
        ids = []
        for i in range(5):
            conv_id = await memory_service.create_conversation(title=f"Chat {i}")
            ids.append(conv_id)

        # All IDs should be unique
        assert len(set(ids)) == 5

        # All should exist
        for conv_id in ids:
            assert await memory_service.conversation_exists(conv_id)


class TestConversationDeletion:
    """Tests for deleting conversations."""

    @pytest.mark.asyncio
    async def test_delete_conversation(self, memory_service):
        """Test deleting a conversation removes it and its messages."""
        conv_id = await memory_service.create_conversation(title="To Delete")
        await memory_service.add_message(conv_id, "user", "Hello")
        await memory_service.add_message(conv_id, "assistant", "Hi")

        result = await memory_service.delete_conversation(conv_id)
        assert result is True

        # Conversation should no longer exist
        assert await memory_service.conversation_exists(conv_id) is False
        conv = await memory_service.get_conversation(conv_id)
        assert conv is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_conversation(self, memory_service):
        """Test deleting a non-existent conversation returns False."""
        result = await memory_service.delete_conversation("conv_nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_does_not_affect_other_conversations(self, memory_service):
        """Test that deleting one conversation doesn't affect others."""
        conv1 = await memory_service.create_conversation(title="Keep")
        conv2 = await memory_service.create_conversation(title="Delete")

        await memory_service.add_message(conv1, "user", "Keep this")
        await memory_service.add_message(conv2, "user", "Delete this")

        await memory_service.delete_conversation(conv2)

        # conv1 should still exist with its messages
        conv = await memory_service.get_conversation(conv1)
        assert conv is not None
        assert len(conv["messages"]) == 1
        assert conv["messages"][0]["content"] == "Keep this"


class TestConversationRenaming:
    """Tests for renaming conversations."""

    @pytest.mark.asyncio
    async def test_rename_conversation(self, memory_service):
        """Test renaming a conversation."""
        conv_id = await memory_service.create_conversation(title="Old Title")

        result = await memory_service.rename_conversation(conv_id, "New Title")
        assert result is True

        conv = await memory_service.get_conversation(conv_id)
        assert conv["title"] == "New Title"

    @pytest.mark.asyncio
    async def test_rename_nonexistent_conversation(self, memory_service):
        """Test renaming a non-existent conversation returns False."""
        result = await memory_service.rename_conversation("conv_nonexistent", "Title")
        assert result is False


class TestAutoTitle:
    """Tests for auto-generating conversation titles."""

    @pytest.mark.asyncio
    async def test_auto_title_short_message(self, memory_service):
        """Test auto-title from a short message."""
        conv_id = await memory_service.create_conversation(title="New Conversation")
        await memory_service.auto_title_conversation(conv_id, "Hello world")

        conv = await memory_service.get_conversation(conv_id)
        assert conv["title"] == "Hello world"

    @pytest.mark.asyncio
    async def test_auto_title_long_message_truncates(self, memory_service):
        """Test auto-title truncates long messages at ~50 chars."""
        conv_id = await memory_service.create_conversation(title="New Conversation")
        long_msg = "This is a very long message that should be truncated at around fifty characters or so for the title"
        await memory_service.auto_title_conversation(conv_id, long_msg)

        conv = await memory_service.get_conversation(conv_id)
        assert len(conv["title"]) <= 60  # Allow for "..."
        assert conv["title"].endswith("...")

    @pytest.mark.asyncio
    async def test_auto_title_truncates_at_word_boundary(self, memory_service):
        """Test auto-title tries to truncate at word boundary."""
        conv_id = await memory_service.create_conversation(title="New Conversation")
        msg = "Hello world this is a test message that is longer than fifty characters"
        await memory_service.auto_title_conversation(conv_id, msg)

        conv = await memory_service.get_conversation(conv_id)
        # Should not end with a partial word (before "...")
        title_without_ellipsis = conv["title"].rstrip(".")
        assert not title_without_ellipsis.endswith(" ")  # No trailing space before ...

    @pytest.mark.asyncio
    async def test_auto_title_empty_message_does_nothing(self, memory_service):
        """Test auto-title with empty message doesn't change title."""
        conv_id = await memory_service.create_conversation(title="Original")
        await memory_service.auto_title_conversation(conv_id, "")

        conv = await memory_service.get_conversation(conv_id)
        assert conv["title"] == "Original"

    @pytest.mark.asyncio
    async def test_auto_title_exactly_50_chars(self, memory_service):
        """Test auto-title with exactly 50 character message."""
        conv_id = await memory_service.create_conversation(title="New Conversation")
        msg = "A" * 50
        await memory_service.auto_title_conversation(conv_id, msg)

        conv = await memory_service.get_conversation(conv_id)
        assert conv["title"] == msg  # Exactly 50 chars, no truncation


class TestListConversations:
    """Tests for listing conversations with metadata."""

    @pytest.mark.asyncio
    async def test_list_conversations_returns_all(self, memory_service):
        """Test listing returns all conversations."""
        await memory_service.create_conversation(title="Chat 1")
        await memory_service.create_conversation(title="Chat 2")
        await memory_service.create_conversation(title="Chat 3")

        convs = await memory_service.list_conversations()
        assert len(convs) == 3

    @pytest.mark.asyncio
    async def test_list_conversations_sorted_by_recent(self, memory_service):
        """Test conversations are sorted by most recently active."""
        conv1 = await memory_service.create_conversation(title="Oldest")
        conv2 = await memory_service.create_conversation(title="Middle")
        conv3 = await memory_service.create_conversation(title="Newest")

        # Add message to conv1 to make it most recent
        await memory_service.add_message(conv1, "user", "Updated!")

        convs = await memory_service.list_conversations()
        # conv1 should be first (most recently updated)
        assert convs[0]["id"] == conv1

    @pytest.mark.asyncio
    async def test_list_conversations_includes_message_count(self, memory_service):
        """Test conversation listing includes message counts."""
        conv_id = await memory_service.create_conversation(title="Chat")
        await memory_service.add_message(conv_id, "user", "Hello")
        await memory_service.add_message(conv_id, "assistant", "Hi")
        await memory_service.add_message(conv_id, "user", "How are you?")

        convs = await memory_service.list_conversations()
        conv = next(c for c in convs if c["id"] == conv_id)
        assert conv["message_count"] == 3

    @pytest.mark.asyncio
    async def test_list_conversations_includes_preview(self, memory_service):
        """Test conversation listing includes preview of last user message."""
        conv_id = await memory_service.create_conversation(title="Chat")
        await memory_service.add_message(conv_id, "user", "First message")
        await memory_service.add_message(conv_id, "assistant", "Response")
        await memory_service.add_message(conv_id, "user", "Second message")

        convs = await memory_service.list_conversations()
        conv = next(c for c in convs if c["id"] == conv_id)
        assert "preview" in conv
        assert conv["preview"] == "Second message"

    @pytest.mark.asyncio
    async def test_list_conversations_preview_truncated(self, memory_service):
        """Test that long preview messages are truncated."""
        conv_id = await memory_service.create_conversation(title="Chat")
        long_msg = "A" * 200
        await memory_service.add_message(conv_id, "user", long_msg)

        convs = await memory_service.list_conversations()
        conv = next(c for c in convs if c["id"] == conv_id)
        assert len(conv["preview"]) <= 84  # 80 + "..."
        assert conv["preview"].endswith("...")

    @pytest.mark.asyncio
    async def test_list_conversations_empty_preview(self, memory_service):
        """Test conversation with no messages has empty preview."""
        conv_id = await memory_service.create_conversation(title="Empty Chat")

        convs = await memory_service.list_conversations()
        conv = next(c for c in convs if c["id"] == conv_id)
        assert conv["preview"] == ""


class TestMultiConversationMessages:
    """Tests for sending messages to different conversations."""

    @pytest.mark.asyncio
    async def test_messages_go_to_correct_conversation(self, memory_service):
        """Test that messages are stored in the right conversation."""
        conv1 = await memory_service.create_conversation(title="Chat 1")
        conv2 = await memory_service.create_conversation(title="Chat 2")

        await memory_service.add_message(conv1, "user", "Hello from chat 1")
        await memory_service.add_message(conv2, "user", "Hello from chat 2")

        msgs1 = await memory_service.get_conversation_messages(conv1)
        msgs2 = await memory_service.get_conversation_messages(conv2)

        # Each should have system + 1 message
        assert len(msgs1) == 2
        assert len(msgs2) == 2
        assert msgs1[1]["content"] == "Hello from chat 1"
        assert msgs2[1]["content"] == "Hello from chat 2"

    @pytest.mark.asyncio
    async def test_default_conversation_still_works(self, memory_service):
        """Test that the default 'main' conversation still works."""
        await memory_service.add_to_conversation("user", "Default conversation")

        msgs = await memory_service.get_messages()
        assert len(msgs) == 2  # system + 1
        assert msgs[1]["content"] == "Default conversation"

    @pytest.mark.asyncio
    async def test_add_message_updates_conversation_timestamp(self, memory_service):
        """Test that adding a message updates the conversation's updated_at."""
        conv_id = await memory_service.create_conversation(title="Chat")

        conv_before = await memory_service.get_conversation(conv_id)
        original_updated = conv_before["updated_at"]

        import asyncio
        await asyncio.sleep(0.01)  # Small delay to ensure different timestamp

        await memory_service.add_message(conv_id, "user", "New message")

        conv_after = await memory_service.get_conversation(conv_id)
        assert conv_after["updated_at"] >= original_updated


class TestConversationAPIEndpoints:
    """Tests for the REST API endpoints using FastAPI test client."""

    @pytest.fixture
    def app(self, tmp_path, monkeypatch):
        """Create a FastAPI test app with temp database."""
        monkeypatch.setattr("config.DATABASE_PATH", tmp_path / "test.db")
        monkeypatch.setattr("config.FILES_PATH", tmp_path / "files")
        (tmp_path / "files").mkdir(exist_ok=True)

        # Reset the memory service in chat module
        from server.services.memory import MemoryService
        from server.routes import chat
        chat.memory = MemoryService(tmp_path / "test.db")

        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(chat.router, prefix="/api")
        return app

    @pytest.fixture
    def client(self, app):
        """Create a test client."""
        from fastapi.testclient import TestClient
        return TestClient(app)

    def test_list_conversations_endpoint(self, client):
        """Test GET /api/conversations returns conversation list."""
        response = client.get("/api/conversations")
        assert response.status_code == 200
        data = response.json()
        assert "conversations" in data
        # Should have at least the default conversation
        assert isinstance(data["conversations"], list)

    def test_create_conversation_endpoint(self, client):
        """Test POST /api/conversations creates a new conversation."""
        response = client.post(
            "/api/conversations",
            json={"title": "Test Chat"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Test Chat"
        assert "id" in data

    def test_create_conversation_without_title(self, client):
        """Test POST /api/conversations without title uses default."""
        response = client.post(
            "/api/conversations",
            json={}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "New Conversation"

    def test_get_conversation_endpoint(self, client):
        """Test GET /api/conversations/{id} returns conversation."""
        # Create a conversation first
        create_resp = client.post(
            "/api/conversations",
            json={"title": "Get Test"}
        )
        conv_id = create_resp.json()["id"]

        response = client.get(f"/api/conversations/{conv_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == conv_id
        assert data["title"] == "Get Test"

    def test_get_nonexistent_conversation(self, client):
        """Test GET /api/conversations/{id} returns 404 for missing."""
        response = client.get("/api/conversations/conv_doesnotexist")
        assert response.status_code == 404

    def test_rename_conversation_endpoint(self, client):
        """Test PUT /api/conversations/{id} renames conversation."""
        # Create
        create_resp = client.post(
            "/api/conversations",
            json={"title": "Old Name"}
        )
        conv_id = create_resp.json()["id"]

        # Rename
        response = client.put(
            f"/api/conversations/{conv_id}",
            json={"title": "New Name"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "New Name"

    def test_rename_with_empty_title(self, client):
        """Test PUT with empty title returns 400."""
        create_resp = client.post(
            "/api/conversations",
            json={"title": "Chat"}
        )
        conv_id = create_resp.json()["id"]

        response = client.put(
            f"/api/conversations/{conv_id}",
            json={"title": ""}
        )
        assert response.status_code == 400

    def test_delete_conversation_endpoint(self, client):
        """Test DELETE /api/conversations/{id} deletes conversation."""
        # Create
        create_resp = client.post(
            "/api/conversations",
            json={"title": "Delete Me"}
        )
        conv_id = create_resp.json()["id"]

        # Delete
        response = client.delete(f"/api/conversations/{conv_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify deletion
        get_resp = client.get(f"/api/conversations/{conv_id}")
        assert get_resp.status_code == 404

    def test_cannot_delete_default_conversation(self, client):
        """Test DELETE /api/conversations/main returns 400."""
        response = client.delete("/api/conversations/main")
        assert response.status_code == 400
        assert "Cannot delete the default" in response.json()["detail"]

    def test_delete_nonexistent_conversation(self, client):
        """Test DELETE for non-existent conversation returns 404."""
        response = client.delete("/api/conversations/conv_doesnotexist")
        assert response.status_code == 404

    def test_backward_compatible_conversation_endpoint(self, client):
        """Test GET /api/conversation still works (backward compat)."""
        response = client.get("/api/conversation")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "main"

    def test_conversations_include_preview(self, client):
        """Test that conversation list includes preview snippets."""
        # Create a conversation with messages
        create_resp = client.post(
            "/api/conversations",
            json={"title": "Preview Test"}
        )
        conv_id = create_resp.json()["id"]

        # We can't easily send chat messages without API keys,
        # but we can verify the structure is there
        response = client.get("/api/conversations")
        data = response.json()
        assert "conversations" in data
        for conv in data["conversations"]:
            assert "preview" in conv
            assert "message_count" in conv


class TestBackwardCompatibility:
    """Tests to ensure backward compatibility is maintained."""

    @pytest.mark.asyncio
    async def test_default_conversation_id_unchanged(self, memory_service):
        """Test DEFAULT_CONVERSATION_ID is still 'main'."""
        assert DEFAULT_CONVERSATION_ID == "main"

    @pytest.mark.asyncio
    async def test_add_to_conversation_still_works(self, memory_service):
        """Test the simplified single-conversation API still works."""
        msg_id = await memory_service.add_to_conversation("user", "Test")
        assert msg_id.startswith("msg_")

        msgs = await memory_service.get_messages()
        assert len(msgs) == 2  # system + 1

    @pytest.mark.asyncio
    async def test_get_context_for_api_still_works(self, memory_service):
        """Test context summarization still works for default conversation."""
        for i in range(5):
            await memory_service.add_to_conversation("user", f"Message {i}")

        messages, meta = await memory_service.get_context_for_api()
        assert meta["total_messages"] == 5
        assert len(messages) > 0

    @pytest.mark.asyncio
    async def test_export_import_still_works(self, memory_service):
        """Test export/import functionality still works."""
        await memory_service.add_to_conversation("user", "Export test")

        export_data = await memory_service.export_conversation()
        assert export_data["message_count"] == 1

    @pytest.mark.asyncio
    async def test_main_conversation_preserved_in_list(self, memory_service):
        """Test that 'main' conversation appears in list."""
        await memory_service.add_to_conversation("user", "Main message")

        # Create another conversation
        await memory_service.create_conversation(title="Other Chat")

        convs = await memory_service.list_conversations()
        ids = [c["id"] for c in convs]
        assert "main" in ids


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
