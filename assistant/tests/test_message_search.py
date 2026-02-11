"""Tests for cross-conversation message search functionality."""
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from server.services.memory import MemoryService


@pytest.fixture
def memory_service(tmp_path):
    """Create a memory service with a temporary database."""
    db_path = tmp_path / "test_memory.db"
    service = MemoryService(db_path)
    return service


class TestMessageSearch:
    """Tests for message search across conversations."""

    @pytest.mark.asyncio
    async def test_search_single_conversation(self, memory_service):
        """Test searching within a specific conversation."""
        conv_id = await memory_service.create_conversation(title="Test Conversation")
        await memory_service.add_message(conv_id, "user", "What is Python?")
        await memory_service.add_message(conv_id, "assistant", "Python is a programming language.")
        await memory_service.add_message(conv_id, "user", "Tell me about JavaScript")

        # Search for "Python"
        results = await memory_service.search_messages(
            query="Python",
            conversation_id=conv_id,
            limit=50
        )

        assert len(results) == 2  # Found in user message and assistant response
        assert all("python" in r["content"].lower() for r in results)

    @pytest.mark.asyncio
    async def test_search_all_conversations(self, memory_service):
        """Test searching across all conversations."""
        # Create multiple conversations with distinct content
        conv1 = await memory_service.create_conversation(title="Python Chat")
        await memory_service.add_message(conv1, "user", "How do I use Python decorators?")
        await memory_service.add_message(conv1, "assistant", "Python decorators are functions...")

        conv2 = await memory_service.create_conversation(title="JavaScript Chat")
        await memory_service.add_message(conv2, "user", "Explain JavaScript promises")
        await memory_service.add_message(conv2, "assistant", "JavaScript promises are...")

        conv3 = await memory_service.create_conversation(title="Mixed Chat")
        await memory_service.add_message(conv3, "user", "Compare Python and JavaScript")
        await memory_service.add_message(conv3, "assistant", "Both Python and JavaScript are popular...")

        # Search for "Python" across all conversations
        results = await memory_service.search_messages(
            query="Python",
            conversation_id=None,  # Search all conversations
            limit=50
        )

        # Should find Python in conv1 (2 messages) and conv3 (2 messages) = 4 total
        assert len(results) >= 4
        assert all("python" in r["content"].lower() for r in results)

        # Verify results include conversation titles
        conv_titles = set(r["conversation_title"] for r in results)
        assert "Python Chat" in conv_titles
        assert "Mixed Chat" in conv_titles

    @pytest.mark.asyncio
    async def test_search_snippet_extraction(self, memory_service):
        """Test that search results include context snippets."""
        conv_id = await memory_service.create_conversation()
        long_message = "This is a very long message. " * 20 + "Important keyword here. " + "More text. " * 20
        await memory_service.add_message(conv_id, "user", long_message)

        results = await memory_service.search_messages(
            query="keyword",
            conversation_id=None,
            limit=50
        )

        assert len(results) == 1
        snippet = results[0]["snippet"]

        # Snippet should be shorter than the original message
        assert len(snippet) < len(long_message)

        # Snippet should contain the keyword
        assert "keyword" in snippet.lower()

        # Snippet should have ellipsis if truncated
        if len(long_message) > 150:  # Based on context_chars in _extract_snippet
            assert snippet.startswith("...") or snippet.endswith("...")

    @pytest.mark.asyncio
    async def test_search_case_insensitive(self, memory_service):
        """Test that search is case-insensitive."""
        conv_id = await memory_service.create_conversation()
        await memory_service.add_message(conv_id, "user", "Testing UPPERCASE and lowercase")

        # Search with different cases
        results_lower = await memory_service.search_messages("uppercase", conversation_id=None, limit=50)
        results_upper = await memory_service.search_messages("UPPERCASE", conversation_id=None, limit=50)
        results_mixed = await memory_service.search_messages("UpPeRcAsE", conversation_id=None, limit=50)

        assert len(results_lower) == 1
        assert len(results_upper) == 1
        assert len(results_mixed) == 1

    @pytest.mark.asyncio
    async def test_search_with_pagination(self, memory_service):
        """Test search result pagination."""
        conv_id = await memory_service.create_conversation()

        # Add many messages with the keyword
        for i in range(20):
            await memory_service.add_message(conv_id, "user", f"Message {i} contains keyword")

        # First page
        page1 = await memory_service.search_messages(
            query="keyword",
            conversation_id=None,
            limit=10,
            offset=0
        )

        # Second page
        page2 = await memory_service.search_messages(
            query="keyword",
            conversation_id=None,
            limit=10,
            offset=10
        )

        assert len(page1) == 10
        assert len(page2) == 10

        # Results should be different (no duplicates)
        page1_ids = set(r["id"] for r in page1)
        page2_ids = set(r["id"] for r in page2)
        assert page1_ids.isdisjoint(page2_ids)

    @pytest.mark.asyncio
    async def test_search_no_results(self, memory_service):
        """Test search with no matching results."""
        conv_id = await memory_service.create_conversation()
        await memory_service.add_message(conv_id, "user", "Hello world")
        await memory_service.add_message(conv_id, "assistant", "Hi there")

        results = await memory_service.search_messages(
            query="nonexistent",
            conversation_id=None,
            limit=50
        )

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_search_includes_metadata(self, memory_service):
        """Test that search results include necessary metadata."""
        conv_id = await memory_service.create_conversation(title="My Conversation")
        await memory_service.add_message(conv_id, "user", "Search test message")

        results = await memory_service.search_messages(
            query="Search",
            conversation_id=None,
            limit=50
        )

        assert len(results) == 1
        result = results[0]

        # Check all required fields
        assert "id" in result
        assert "conversation_id" in result
        assert "conversation_title" in result
        assert "role" in result
        assert "content" in result
        assert "created_at" in result
        assert "snippet" in result

        assert result["conversation_title"] == "My Conversation"
        assert result["role"] == "user"
        assert "Search" in result["content"]

    @pytest.mark.asyncio
    async def test_search_empty_query(self, memory_service):
        """Test that empty queries don't crash (handled at API level)."""
        conv_id = await memory_service.create_conversation()
        await memory_service.add_message(conv_id, "user", "Test message")

        # Empty query should return no results or all results (implementation dependent)
        # The API layer should validate this, but service should handle gracefully
        results = await memory_service.search_messages(
            query="",
            conversation_id=None,
            limit=50
        )

        # Empty query returns everything that matches "" (likely everything)
        # This is acceptable at service level; API validates minimum length
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_search_respects_limit(self, memory_service):
        """Test that search respects the limit parameter."""
        conv_id = await memory_service.create_conversation()

        # Add many messages
        for i in range(50):
            await memory_service.add_message(conv_id, "user", f"Message with keyword {i}")

        # Search with small limit
        results = await memory_service.search_messages(
            query="keyword",
            conversation_id=None,
            limit=5
        )

        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_search_multiple_keywords(self, memory_service):
        """Test searching for phrases with multiple words."""
        conv_id = await memory_service.create_conversation()
        await memory_service.add_message(conv_id, "user", "I love Python programming")
        await memory_service.add_message(conv_id, "user", "Python is great")
        await memory_service.add_message(conv_id, "user", "I love JavaScript")

        # Search for multi-word phrase
        results = await memory_service.search_messages(
            query="love Python",
            conversation_id=None,
            limit=50
        )

        # Should find messages containing "love Python"
        # Note: Current implementation uses LIKE which treats it as a phrase
        assert len(results) >= 1
        assert any("love" in r["content"].lower() and "python" in r["content"].lower() for r in results)
