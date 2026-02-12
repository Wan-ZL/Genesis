"""Tests for long-term memory extraction and recall service."""
import pytest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
import json

from server.services.memory_extractor import (
    MemoryExtractorService,
    Fact,
    get_memory_extractor
)


@pytest.fixture
async def service(tmp_path):
    """Create a memory extractor service with temporary database."""
    db_path = tmp_path / "test_facts.db"
    service = MemoryExtractorService(db_path)
    yield service
    # Cleanup
    await service._pool.close()


@pytest.fixture
def sample_facts():
    """Sample facts for testing."""
    return [
        Fact(
            id="fact_1",
            fact_type="preference",
            key="response_style",
            value="concise answers",
            source_conversation_id="conv_1",
            source_message_id="msg_1",
            confidence=0.95,
            created_at="2026-02-11T10:00:00",
            updated_at="2026-02-11T10:00:00"
        ),
        Fact(
            id="fact_2",
            fact_type="work_context",
            key="company",
            value="Genesis (startup)",
            source_conversation_id="conv_1",
            source_message_id="msg_1",
            confidence=0.9,
            created_at="2026-02-11T10:00:00",
            updated_at="2026-02-11T10:00:00"
        ),
        Fact(
            id="fact_3",
            fact_type="personal_info",
            key="name",
            value="Alice",
            source_conversation_id="conv_1",
            source_message_id="msg_2",
            confidence=0.98,
            created_at="2026-02-11T10:05:00",
            updated_at="2026-02-11T10:05:00"
        )
    ]


class TestFactExtraction:
    """Tests for fact extraction from conversations."""

    @pytest.mark.asyncio
    async def test_extract_facts_with_mock_llm(self, service):
        """Test fact extraction with mocked LLM response."""
        # Mock LLM response
        mock_extraction = {
            "facts": [
                {
                    "fact_type": "preference",
                    "key": "response_style",
                    "value": "concise answers",
                    "confidence": 0.95
                },
                {
                    "fact_type": "work_context",
                    "key": "company",
                    "value": "Genesis",
                    "confidence": 0.9
                }
            ]
        }

        with patch.object(service, '_call_extraction_llm', return_value=mock_extraction):
            facts = await service.extract_facts_from_turn(
                user_message="I work at Genesis. Please keep answers concise.",
                assistant_message="Understood! I'll keep my responses short.",
                conversation_id="conv_1",
                message_id="msg_1"
            )

            assert len(facts) == 2
            assert facts[0].fact_type == "preference"
            assert facts[0].key == "response_style"
            assert facts[0].confidence == 0.95
            assert facts[1].fact_type == "work_context"
            assert facts[1].key == "company"

    @pytest.mark.asyncio
    async def test_extract_facts_filters_low_confidence(self, service):
        """Test that low-confidence facts are filtered out."""
        mock_extraction = {
            "facts": [
                {
                    "fact_type": "preference",
                    "key": "test",
                    "value": "high confidence",
                    "confidence": 0.9
                },
                {
                    "fact_type": "preference",
                    "key": "test2",
                    "value": "low confidence",
                    "confidence": 0.3  # Below 0.5 threshold
                }
            ]
        }

        with patch.object(service, '_call_extraction_llm', return_value=mock_extraction):
            facts = await service.extract_facts_from_turn(
                user_message="test", assistant_message="test",
                conversation_id="conv_1", message_id="msg_1"
            )

            assert len(facts) == 1
            assert facts[0].value == "high confidence"

    @pytest.mark.asyncio
    async def test_extract_facts_handles_llm_errors(self, service):
        """Test that extraction handles LLM errors gracefully."""
        with patch.object(service, '_call_extraction_llm', side_effect=Exception("API error")):
            facts = await service.extract_facts_from_turn(
                user_message="test", assistant_message="test",
                conversation_id="conv_1", message_id="msg_1"
            )

            assert len(facts) == 0  # Should return empty list on error

    @pytest.mark.asyncio
    async def test_extract_facts_handles_invalid_json(self, service):
        """Test that extraction handles incomplete fact data."""
        mock_extraction = {
            "facts": [
                {
                    "fact_type": "preference",
                    "key": "test",
                    # Missing "value" and "confidence"
                }
            ]
        }

        with patch.object(service, '_call_extraction_llm', return_value=mock_extraction):
            facts = await service.extract_facts_from_turn(
                user_message="test", assistant_message="test",
                conversation_id="conv_1", message_id="msg_1"
            )

            assert len(facts) == 0  # Should skip incomplete facts


class TestFactStorage:
    """Tests for fact storage and retrieval."""

    @pytest.mark.asyncio
    async def test_store_and_retrieve_facts(self, service, sample_facts):
        """Test storing and retrieving facts."""
        await service.store_facts(sample_facts, deduplicate=False)

        # Retrieve all facts
        retrieved = await service.get_all_facts(limit=100)

        assert len(retrieved) == 3
        # Verify all IDs are present (order may vary)
        retrieved_ids = {f.id for f in retrieved}
        expected_ids = {f.id for f in sample_facts}
        assert retrieved_ids == expected_ids

    @pytest.mark.asyncio
    async def test_store_facts_with_deduplication(self, service):
        """Test that duplicate facts are updated rather than duplicated."""
        fact1 = Fact(
            id="fact_1",
            fact_type="preference",
            key="response_style",
            value="detailed answers",
            source_conversation_id="conv_1",
            source_message_id="msg_1",
            confidence=0.8,
            created_at="2026-02-11T10:00:00",
            updated_at="2026-02-11T10:00:00"
        )

        # Store initial fact
        await service.store_facts([fact1], deduplicate=True)

        # Store updated fact with same type+key but higher confidence
        fact2 = Fact(
            id="fact_2",
            fact_type="preference",
            key="response_style",  # Same key
            value="concise answers",  # Different value
            source_conversation_id="conv_1",
            source_message_id="msg_2",
            confidence=0.95,  # Higher confidence
            created_at="2026-02-11T10:05:00",
            updated_at="2026-02-11T10:05:00"
        )

        await service.store_facts([fact2], deduplicate=True)

        # Should only have one fact (updated)
        all_facts = await service.get_all_facts(limit=100)
        assert len(all_facts) == 1
        assert all_facts[0].value == "concise answers"
        assert all_facts[0].confidence == 0.95

    @pytest.mark.asyncio
    async def test_store_facts_skips_lower_confidence_updates(self, service):
        """Test that lower confidence facts don't overwrite higher confidence ones."""
        high_conf_fact = Fact(
            id="fact_1",
            fact_type="preference",
            key="response_style",
            value="concise answers",
            source_conversation_id="conv_1",
            source_message_id="msg_1",
            confidence=0.95,
            created_at="2026-02-11T10:00:00",
            updated_at="2026-02-11T10:00:00"
        )

        await service.store_facts([high_conf_fact], deduplicate=True)

        # Try to store lower confidence fact
        low_conf_fact = Fact(
            id="fact_2",
            fact_type="preference",
            key="response_style",
            value="detailed answers",
            source_conversation_id="conv_1",
            source_message_id="msg_2",
            confidence=0.6,  # Lower confidence
            created_at="2026-02-11T10:05:00",
            updated_at="2026-02-11T10:05:00"
        )

        await service.store_facts([low_conf_fact], deduplicate=True)

        # Original fact should remain
        all_facts = await service.get_all_facts(limit=100)
        assert len(all_facts) == 1
        assert all_facts[0].value == "concise answers"
        assert all_facts[0].confidence == 0.95

    @pytest.mark.asyncio
    async def test_get_fact_by_id(self, service, sample_facts):
        """Test retrieving a specific fact by ID."""
        await service.store_facts(sample_facts, deduplicate=False)

        fact = await service.get_fact("fact_1")

        assert fact is not None
        assert fact.id == "fact_1"
        assert fact.key == "response_style"

    @pytest.mark.asyncio
    async def test_get_fact_by_id_not_found(self, service):
        """Test retrieving a non-existent fact."""
        fact = await service.get_fact("nonexistent")
        assert fact is None

    @pytest.mark.asyncio
    async def test_get_facts_with_type_filter(self, service, sample_facts):
        """Test filtering facts by type."""
        await service.store_facts(sample_facts, deduplicate=False)

        prefs = await service.get_all_facts(limit=100, fact_type="preference")
        work = await service.get_all_facts(limit=100, fact_type="work_context")

        assert len(prefs) == 1
        assert prefs[0].fact_type == "preference"
        assert len(work) == 1
        assert work[0].fact_type == "work_context"

    @pytest.mark.asyncio
    async def test_get_facts_with_pagination(self, service, sample_facts):
        """Test pagination of facts."""
        await service.store_facts(sample_facts, deduplicate=False)

        # Get first page
        page1 = await service.get_all_facts(limit=2, offset=0)
        assert len(page1) == 2

        # Get second page
        page2 = await service.get_all_facts(limit=2, offset=2)
        assert len(page2) == 1

        # Ensure no overlap
        assert page1[0].id != page2[0].id


class TestFactRecall:
    """Tests for fact recall and search."""

    @pytest.mark.asyncio
    async def test_recall_facts_with_query(self, service, sample_facts):
        """Test FTS5 search for facts."""
        await service.store_facts(sample_facts, deduplicate=False)

        # Search for "Genesis"
        results = await service.recall_facts(query="Genesis", limit=10)

        assert len(results) >= 1
        assert any("Genesis" in f.value for f in results)

    @pytest.mark.asyncio
    async def test_recall_facts_without_query(self, service, sample_facts):
        """Test getting top facts without search query."""
        await service.store_facts(sample_facts, deduplicate=False)

        results = await service.recall_facts(limit=2)

        assert len(results) == 2
        # Should be ordered by confidence
        assert results[0].confidence >= results[1].confidence

    @pytest.mark.asyncio
    async def test_recall_facts_with_type_filter(self, service, sample_facts):
        """Test searching with fact type filter."""
        await service.store_facts(sample_facts, deduplicate=False)

        results = await service.recall_facts(
            query="answers",
            fact_types=["preference"],
            limit=10
        )

        assert len(results) >= 1
        assert all(f.fact_type == "preference" for f in results)

    @pytest.mark.asyncio
    async def test_format_facts_for_system_prompt(self, service, sample_facts):
        """Test formatting facts for injection into system prompt."""
        formatted = service.format_facts_for_system_prompt(sample_facts)

        assert "## What I know about you:" in formatted
        assert "Preferences:" in formatted
        assert "concise answers" in formatted
        assert "Work Context:" in formatted
        assert "Genesis (startup)" in formatted
        assert "Personal Info:" in formatted
        assert "Alice" in formatted

    @pytest.mark.asyncio
    async def test_format_facts_empty_list(self, service):
        """Test formatting empty fact list."""
        formatted = service.format_facts_for_system_prompt([])
        assert formatted == ""


class TestFactDeletion:
    """Tests for fact deletion."""

    @pytest.mark.asyncio
    async def test_delete_fact_by_id(self, service, sample_facts):
        """Test deleting a specific fact."""
        await service.store_facts(sample_facts, deduplicate=False)

        success = await service.delete_fact("fact_1")
        assert success is True

        # Verify deletion
        remaining = await service.get_all_facts(limit=100)
        assert len(remaining) == 2
        assert not any(f.id == "fact_1" for f in remaining)

    @pytest.mark.asyncio
    async def test_delete_fact_not_found(self, service):
        """Test deleting a non-existent fact."""
        success = await service.delete_fact("nonexistent")
        assert success is False

    @pytest.mark.asyncio
    async def test_delete_all_facts(self, service, sample_facts):
        """Test deleting all facts."""
        await service.store_facts(sample_facts, deduplicate=False)

        count = await service.delete_all_facts()
        assert count == 3

        # Verify all deleted
        remaining = await service.get_all_facts(limit=100)
        assert len(remaining) == 0


class TestDatabaseIntegrity:
    """Tests for database structure and triggers."""

    @pytest.mark.asyncio
    async def test_fts5_index_auto_updates(self, service, sample_facts):
        """Test that FTS5 index updates automatically via triggers."""
        await service.store_facts(sample_facts[:1], deduplicate=False)

        # Search should find the fact
        results = await service.recall_facts(query="concise", limit=10)
        assert len(results) == 1

        # Delete the fact
        await service.delete_fact(sample_facts[0].id)

        # Search should no longer find it
        results = await service.recall_facts(query="concise", limit=10)
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_fts5_index_updates_on_fact_update(self, service):
        """Test that FTS5 index updates when fact value changes."""
        fact1 = Fact(
            id="fact_1",
            fact_type="preference",
            key="style",
            value="original value",
            source_conversation_id="conv_1",
            source_message_id="msg_1",
            confidence=0.8,
            created_at="2026-02-11T10:00:00",
            updated_at="2026-02-11T10:00:00"
        )

        await service.store_facts([fact1], deduplicate=True)

        # Search for original value
        results = await service.recall_facts(query="original", limit=10)
        assert len(results) == 1

        # Update the fact
        fact2 = Fact(
            id="fact_2",
            fact_type="preference",
            key="style",
            value="updated value",
            source_conversation_id="conv_1",
            source_message_id="msg_2",
            confidence=0.9,
            created_at="2026-02-11T10:05:00",
            updated_at="2026-02-11T10:05:00"
        )

        await service.store_facts([fact2], deduplicate=True)

        # Search for new value
        results = await service.recall_facts(query="updated", limit=10)
        assert len(results) == 1

        # Note: FTS5 trigger fires on UPDATE, so the fact should now contain "updated value"
        # and searching for "original" should find the updated fact (since it still has the same ID)
        # The FTS5 index should reflect the current value in the facts table


class TestServiceSingleton:
    """Tests for global service instance."""

    def test_get_memory_extractor_singleton(self, tmp_path):
        """Test that get_memory_extractor returns a singleton."""
        # First call creates instance
        service1 = get_memory_extractor()
        assert service1 is not None

        # Second call returns same instance
        service2 = get_memory_extractor()
        assert service1 is service2
