"""Tests for memory facts API endpoints."""
import pytest
from fastapi.testclient import TestClient
from pathlib import Path
from unittest.mock import patch, AsyncMock

from server.main import app
from server.services.memory_extractor import Fact, MemoryExtractorService


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


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
        )
    ]


class TestListFactsEndpoint:
    """Tests for GET /api/memory/facts endpoint."""

    def test_list_facts_empty(self, client):
        """Test listing facts when none exist."""
        with patch('server.routes.memory_facts.get_memory_extractor') as mock_get:
            mock_service = AsyncMock()
            mock_service.get_all_facts = AsyncMock(return_value=[])
            mock_get.return_value = mock_service

            response = client.get("/api/memory/facts")

            assert response.status_code == 200
            data = response.json()
            assert data["count"] == 0
            assert data["facts"] == []
            assert data["limit"] == 100
            assert data["offset"] == 0

    def test_list_facts_with_data(self, client, sample_facts):
        """Test listing facts with data."""
        with patch('server.routes.memory_facts.get_memory_extractor') as mock_get:
            mock_service = AsyncMock()
            mock_service.get_all_facts = AsyncMock(return_value=sample_facts)
            mock_get.return_value = mock_service

            response = client.get("/api/memory/facts")

            assert response.status_code == 200
            data = response.json()
            assert data["count"] == 2
            assert len(data["facts"]) == 2
            assert data["facts"][0]["id"] == "fact_1"
            assert data["facts"][0]["fact_type"] == "preference"
            assert data["facts"][0]["confidence"] == 0.95

    def test_list_facts_with_pagination(self, client, sample_facts):
        """Test listing facts with pagination parameters."""
        with patch('server.routes.memory_facts.get_memory_extractor') as mock_get:
            mock_service = AsyncMock()
            mock_service.get_all_facts = AsyncMock(return_value=[sample_facts[0]])
            mock_get.return_value = mock_service

            response = client.get("/api/memory/facts?limit=1&offset=1")

            assert response.status_code == 200
            data = response.json()
            assert data["limit"] == 1
            assert data["offset"] == 1
            mock_service.get_all_facts.assert_called_once_with(
                limit=1, offset=1, fact_type=None
            )

    def test_list_facts_with_type_filter(self, client, sample_facts):
        """Test listing facts filtered by type."""
        with patch('server.routes.memory_facts.get_memory_extractor') as mock_get:
            mock_service = AsyncMock()
            mock_service.get_all_facts = AsyncMock(return_value=[sample_facts[0]])
            mock_get.return_value = mock_service

            response = client.get("/api/memory/facts?fact_type=preference")

            assert response.status_code == 200
            data = response.json()
            assert data["count"] == 1
            assert data["facts"][0]["fact_type"] == "preference"
            mock_service.get_all_facts.assert_called_once_with(
                limit=100, offset=0, fact_type="preference"
            )


class TestGetFactEndpoint:
    """Tests for GET /api/memory/facts/{fact_id} endpoint."""

    def test_get_fact_success(self, client, sample_facts):
        """Test getting a specific fact by ID."""
        with patch('server.routes.memory_facts.get_memory_extractor') as mock_get:
            mock_service = AsyncMock()
            mock_service.get_fact = AsyncMock(return_value=sample_facts[0])
            mock_get.return_value = mock_service

            response = client.get("/api/memory/facts/fact_1")

            assert response.status_code == 200
            data = response.json()
            assert data["id"] == "fact_1"
            assert data["key"] == "response_style"
            assert data["value"] == "concise answers"

    def test_get_fact_not_found(self, client):
        """Test getting a non-existent fact."""
        with patch('server.routes.memory_facts.get_memory_extractor') as mock_get:
            mock_service = AsyncMock()
            mock_service.get_fact = AsyncMock(return_value=None)
            mock_get.return_value = mock_service

            response = client.get("/api/memory/facts/nonexistent")

            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()


class TestDeleteFactEndpoint:
    """Tests for DELETE /api/memory/facts/{fact_id} endpoint."""

    def test_delete_fact_success(self, client):
        """Test deleting a fact."""
        with patch('server.routes.memory_facts.get_memory_extractor') as mock_get:
            mock_service = AsyncMock()
            mock_service.delete_fact = AsyncMock(return_value=True)
            mock_get.return_value = mock_service

            response = client.delete("/api/memory/facts/fact_1")

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["deleted"] == "fact_1"
            mock_service.delete_fact.assert_called_once_with("fact_1")

    def test_delete_fact_not_found(self, client):
        """Test deleting a non-existent fact."""
        with patch('server.routes.memory_facts.get_memory_extractor') as mock_get:
            mock_service = AsyncMock()
            mock_service.delete_fact = AsyncMock(return_value=False)
            mock_get.return_value = mock_service

            response = client.delete("/api/memory/facts/nonexistent")

            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()


class TestDeleteAllFactsEndpoint:
    """Tests for DELETE /api/memory/facts endpoint."""

    def test_delete_all_facts(self, client):
        """Test deleting all facts."""
        with patch('server.routes.memory_facts.get_memory_extractor') as mock_get:
            mock_service = AsyncMock()
            mock_service.delete_all_facts = AsyncMock(return_value=5)
            mock_get.return_value = mock_service

            response = client.delete("/api/memory/facts")

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["deleted_count"] == 5
            mock_service.delete_all_facts.assert_called_once()


class TestSearchFactsEndpoint:
    """Tests for GET /api/memory/search endpoint."""

    def test_search_facts_success(self, client, sample_facts):
        """Test searching facts."""
        with patch('server.routes.memory_facts.get_memory_extractor') as mock_get:
            mock_service = AsyncMock()
            mock_service.recall_facts = AsyncMock(return_value=[sample_facts[1]])
            mock_get.return_value = mock_service

            response = client.get("/api/memory/search?q=Genesis")

            assert response.status_code == 200
            data = response.json()
            assert data["query"] == "Genesis"
            assert data["count"] == 1
            assert data["facts"][0]["value"] == "Genesis (startup)"
            mock_service.recall_facts.assert_called_once_with(
                query="Genesis", fact_types=None, limit=50
            )

    def test_search_facts_with_type_filter(self, client, sample_facts):
        """Test searching facts with type filter."""
        with patch('server.routes.memory_facts.get_memory_extractor') as mock_get:
            mock_service = AsyncMock()
            mock_service.recall_facts = AsyncMock(return_value=[sample_facts[0]])
            mock_get.return_value = mock_service

            response = client.get("/api/memory/search?q=concise&fact_type=preference")

            assert response.status_code == 200
            data = response.json()
            assert data["count"] == 1
            mock_service.recall_facts.assert_called_once_with(
                query="concise", fact_types=["preference"], limit=50
            )

    def test_search_facts_query_too_short(self, client):
        """Test search with query that's too short."""
        response = client.get("/api/memory/search?q=a")

        assert response.status_code == 422  # FastAPI validation error
        assert "at least 2 characters" in str(response.json()["detail"]).lower()

    def test_search_facts_missing_query(self, client):
        """Test search without query parameter."""
        response = client.get("/api/memory/search")

        assert response.status_code == 422  # Validation error
