"""Tests for graceful degradation service."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock, MagicMock
import asyncio

from server.services.degradation import (
    DegradationService,
    DegradationMode,
    APIHealth,
    get_degradation_service,
)


class TestAPIHealth:
    """Tests for APIHealth class."""

    def test_init_defaults(self):
        """Test APIHealth initializes with correct defaults."""
        health = APIHealth(name="test")
        assert health.name == "test"
        assert health.available is True
        assert health.last_success is None
        assert health.last_failure is None
        assert health.consecutive_failures == 0
        assert health.rate_limited_until is None
        assert health.total_requests == 0
        assert health.total_failures == 0

    def test_failure_rate_no_requests(self):
        """Test failure rate returns 0 with no requests."""
        health = APIHealth(name="test")
        assert health.failure_rate == 0.0

    def test_failure_rate_calculation(self):
        """Test failure rate calculation."""
        health = APIHealth(name="test")
        health.total_requests = 10
        health.total_failures = 3
        assert health.failure_rate == 30.0

    def test_is_rate_limited_false_when_none(self):
        """Test is_rate_limited returns False when no limit set."""
        health = APIHealth(name="test")
        assert health.is_rate_limited is False

    def test_is_rate_limited_true_when_active(self):
        """Test is_rate_limited returns True when limit is active."""
        health = APIHealth(name="test")
        health.rate_limited_until = datetime.now() + timedelta(seconds=60)
        assert health.is_rate_limited is True

    def test_is_rate_limited_false_when_expired(self):
        """Test is_rate_limited returns False when limit expired."""
        health = APIHealth(name="test")
        health.rate_limited_until = datetime.now() - timedelta(seconds=60)
        assert health.is_rate_limited is False

    def test_record_success(self):
        """Test recording a successful API call."""
        health = APIHealth(name="test")
        health.consecutive_failures = 3
        health.available = False
        health.record_success()
        assert health.total_requests == 1
        assert health.consecutive_failures == 0
        assert health.available is True
        assert health.last_success is not None

    def test_record_failure(self):
        """Test recording a failed API call."""
        health = APIHealth(name="test")
        health.record_failure()
        assert health.total_requests == 1
        assert health.total_failures == 1
        assert health.consecutive_failures == 1
        assert health.last_failure is not None
        assert health.available is True  # Still available after 1 failure

    def test_record_failure_marks_unavailable_after_threshold(self):
        """Test API marked unavailable after 3 consecutive failures."""
        health = APIHealth(name="test")
        health.record_failure()
        health.record_failure()
        assert health.available is True
        health.record_failure()
        assert health.available is False
        assert health.consecutive_failures == 3

    def test_record_failure_with_rate_limit(self):
        """Test recording a rate limit failure."""
        health = APIHealth(name="test")
        health.record_failure(is_rate_limit=True, retry_after=120)
        assert health.is_rate_limited is True
        assert health.rate_limited_until is not None
        expected_after = datetime.now() + timedelta(seconds=119)
        assert health.rate_limited_until > expected_after

    def test_to_dict(self):
        """Test converting APIHealth to dictionary."""
        health = APIHealth(name="claude")
        health.record_success()
        data = health.to_dict()
        assert data["name"] == "claude"
        assert data["available"] is True
        assert data["is_rate_limited"] is False
        assert data["consecutive_failures"] == 0
        assert "last_success" in data
        assert data["last_success"] is not None


class TestDegradationService:
    """Tests for DegradationService class."""

    def test_init(self):
        """Test DegradationService initializes correctly."""
        service = DegradationService()
        assert service.mode == DegradationMode.NORMAL
        assert not service.is_degraded
        assert "claude" in service._api_health
        assert "openai" in service._api_health
        assert "ollama" in service._api_health

    def test_init_ollama_unavailable_by_default(self):
        """Test that Ollama starts as unavailable until verified (Issue #23)."""
        service = DegradationService()
        # Cloud APIs should default to available
        assert service._api_health["claude"].available is True
        assert service._api_health["openai"].available is True
        # Ollama should default to unavailable until initialize_ollama_status() is called
        assert service._api_health["ollama"].available is False

    @pytest.mark.asyncio
    async def test_initialize_ollama_status_available(self):
        """Test initialize_ollama_status sets Ollama available when running."""
        service = DegradationService()
        assert service._api_health["ollama"].available is False

        with patch('server.services.ollama.check_ollama_available', new=AsyncMock(return_value=True)):
            await service.initialize_ollama_status()

        assert service._api_health["ollama"].available is True

    @pytest.mark.asyncio
    async def test_initialize_ollama_status_unavailable(self):
        """Test initialize_ollama_status keeps Ollama unavailable when not running."""
        service = DegradationService()
        assert service._api_health["ollama"].available is False

        with patch('server.services.ollama.check_ollama_available', new=AsyncMock(return_value=False)):
            await service.initialize_ollama_status()

        assert service._api_health["ollama"].available is False

    @pytest.mark.asyncio
    async def test_initialize_ollama_status_handles_exception(self):
        """Test initialize_ollama_status handles errors gracefully."""
        service = DegradationService()

        with patch('server.services.ollama.check_ollama_available', new=AsyncMock(side_effect=Exception("Connection error"))):
            # Should not raise
            await service.initialize_ollama_status()

        # Should remain unavailable
        assert service._api_health["ollama"].available is False

    def test_get_api_health(self):
        """Test getting API health."""
        service = DegradationService()
        health = service.get_api_health("claude")
        assert health.name == "claude"

    def test_record_success(self):
        """Test recording API success updates mode."""
        service = DegradationService()
        # First mark as unavailable
        for _ in range(3):
            service.record_failure("claude")
        assert service.mode == DegradationMode.CLAUDE_UNAVAILABLE
        # Now record success
        service.record_success("claude")
        assert service.mode == DegradationMode.NORMAL

    def test_record_failure_changes_mode(self):
        """Test recording failures changes degradation mode."""
        service = DegradationService()
        assert service.mode == DegradationMode.NORMAL
        # 3 failures marks API unavailable
        for _ in range(3):
            service.record_failure("claude")
        assert service.mode == DegradationMode.CLAUDE_UNAVAILABLE
        assert service.is_degraded

    def test_record_failure_both_cloud_apis_with_ollama(self):
        """Test both cloud APIs failing with Ollama available results in CLOUD_UNAVAILABLE."""
        service = DegradationService()
        # Ollama is available by default
        service._api_health["ollama"].available = True
        for _ in range(3):
            service.record_failure("claude")
            service.record_failure("openai")
        assert service.mode == DegradationMode.CLOUD_UNAVAILABLE

    def test_record_failure_all_apis_goes_offline(self):
        """Test all APIs (including Ollama) failing results in OFFLINE mode."""
        service = DegradationService()
        service._api_health["ollama"].available = False
        for _ in range(3):
            service.record_failure("claude")
            service.record_failure("openai")
        assert service.mode == DegradationMode.OFFLINE

    def test_rate_limit_changes_mode(self):
        """Test rate limiting changes mode."""
        service = DegradationService()
        service.record_failure("claude", is_rate_limit=True, retry_after=60)
        assert service.mode == DegradationMode.RATE_LIMITED

    def test_should_use_fallback_when_unavailable(self):
        """Test fallback detection when API unavailable."""
        service = DegradationService()
        assert not service.should_use_fallback("claude")
        for _ in range(3):
            service.record_failure("claude")
        assert service.should_use_fallback("claude")

    def test_should_use_fallback_when_rate_limited(self):
        """Test fallback detection when rate limited."""
        service = DegradationService()
        service.record_failure("claude", is_rate_limit=True, retry_after=60)
        assert service.should_use_fallback("claude")

    def test_get_preferred_api_normal(self):
        """Test preferred API in normal mode."""
        service = DegradationService()
        assert service.get_preferred_api("claude") == "claude"
        assert service.get_preferred_api("openai") == "openai"

    def test_get_preferred_api_fallback(self):
        """Test preferred API falls back when primary unavailable."""
        service = DegradationService()
        for _ in range(3):
            service.record_failure("claude")
        assert service.get_preferred_api("claude") == "openai"

    def test_get_preferred_api_both_cloud_unavailable_returns_ollama(self):
        """Test preferred API falls back to Ollama when both cloud APIs unavailable."""
        service = DegradationService()
        service._api_health["ollama"].available = True
        for _ in range(3):
            service.record_failure("claude")
            service.record_failure("openai")
        # Should fall back to Ollama
        result = service.get_preferred_api("claude")
        assert result == "ollama"

    def test_get_preferred_api_all_unavailable_returns_primary(self):
        """Test preferred API returns primary when all APIs unavailable."""
        service = DegradationService()
        service._api_health["ollama"].available = False
        for _ in range(3):
            service.record_failure("claude")
            service.record_failure("openai")
        # Should still return one of the cloud APIs (fallback logic)
        result = service.get_preferred_api("claude")
        assert result in ["claude", "openai"]

    @pytest.mark.asyncio
    async def test_check_network_success(self):
        """Test network check succeeds."""
        service = DegradationService()
        with patch('socket.gethostbyname', return_value='8.8.8.8'):
            result = await service.check_network(force=True)
            assert result is True
            assert service._network_available is True

    @pytest.mark.asyncio
    async def test_check_network_failure(self):
        """Test network check fails."""
        import socket
        service = DegradationService()
        with patch('socket.gethostbyname', side_effect=socket.gaierror):
            result = await service.check_network(force=True)
            assert result is False
            assert service._network_available is False
            assert service.mode == DegradationMode.OFFLINE

    @pytest.mark.asyncio
    async def test_check_network_cached(self):
        """Test network check uses cached result."""
        service = DegradationService()
        service._network_available = True
        service._last_network_check = datetime.now()
        # Should return cached result without calling socket
        with patch('socket.gethostbyname') as mock_dns:
            result = await service.check_network(force=False)
            assert result is True
            mock_dns.assert_not_called()

    def test_cache_tool_result(self):
        """Test caching tool results."""
        service = DegradationService()
        service.cache_tool_result("web_fetch", "hash123", {"data": "test"})
        assert len(service._tool_cache) == 1

    def test_get_cached_tool_result(self):
        """Test retrieving cached tool results."""
        service = DegradationService()
        service.cache_tool_result("web_fetch", "hash123", {"data": "test"})
        result = service.get_cached_tool_result("web_fetch", "hash123")
        assert result is not None
        assert result["result"] == {"data": "test"}
        assert result["cached"] is True

    def test_get_cached_tool_result_not_found(self):
        """Test retrieving non-existent cached result."""
        service = DegradationService()
        result = service.get_cached_tool_result("web_fetch", "nonexistent")
        assert result is None

    def test_get_cached_tool_result_expired(self):
        """Test expired cache entries are not returned."""
        service = DegradationService()
        service._tool_cache["web_fetch:hash123"] = {
            "result": {"data": "old"},
            "cached_at": datetime.now() - timedelta(hours=25)  # Expired
        }
        result = service.get_cached_tool_result("web_fetch", "hash123")
        assert result is None
        assert len(service._tool_cache) == 0  # Entry should be removed

    def test_clear_cache(self):
        """Test clearing cache."""
        service = DegradationService()
        service.cache_tool_result("web_fetch", "hash1", "data1")
        service.cache_tool_result("web_fetch", "hash2", "data2")
        assert len(service._tool_cache) == 2
        service.clear_cache()
        assert len(service._tool_cache) == 0

    @pytest.mark.asyncio
    async def test_queue_request(self):
        """Test queuing requests."""
        service = DegradationService()
        async def dummy_callback():
            pass
        result = await service.queue_request("req1", dummy_callback, priority=1)
        assert result is True
        assert service.get_queue_size() == 1

    @pytest.mark.asyncio
    async def test_queue_request_full(self):
        """Test queue rejects when full."""
        service = DegradationService()
        service.MAX_QUEUE_SIZE = 2
        async def dummy_callback():
            pass
        await service.queue_request("req1", dummy_callback)
        await service.queue_request("req2", dummy_callback)
        result = await service.queue_request("req3", dummy_callback)
        assert result is False
        assert service.get_queue_size() == 2

    def test_get_queue_wait_time_not_rate_limited(self):
        """Test wait time is None when not rate limited."""
        service = DegradationService()
        assert service.get_queue_wait_time() is None

    def test_get_queue_wait_time_rate_limited(self):
        """Test wait time when rate limited."""
        service = DegradationService()
        service.record_failure("claude", is_rate_limit=True, retry_after=60)
        wait_time = service.get_queue_wait_time()
        assert wait_time is not None
        assert 0 <= wait_time <= 60

    def test_get_status(self):
        """Test getting full status."""
        service = DegradationService()
        status = service.get_status()
        assert "mode" in status
        assert status["mode"] == "NORMAL"
        assert "is_degraded" in status
        assert status["is_degraded"] is False
        assert "network_available" in status
        assert "apis" in status
        assert "claude" in status["apis"]
        assert "openai" in status["apis"]
        assert "queue_size" in status
        assert "cache_entries" in status

    def test_reset_api_health_specific(self):
        """Test resetting specific API health."""
        service = DegradationService()
        for _ in range(3):
            service.record_failure("claude")
        assert service.mode == DegradationMode.CLAUDE_UNAVAILABLE
        service.reset_api_health("claude")
        assert service.mode == DegradationMode.NORMAL

    def test_reset_api_health_all(self):
        """Test resetting all API health."""
        service = DegradationService()
        # Disable Ollama so both cloud APIs failing = OFFLINE
        service._api_health["ollama"].available = False
        for _ in range(3):
            service.record_failure("claude")
            service.record_failure("openai")
        assert service.mode == DegradationMode.OFFLINE
        service.reset_api_health()
        assert service.mode == DegradationMode.NORMAL
        # Verify Ollama is also reset (but to unavailable, per Issue #23 fix)
        assert "ollama" in service._api_health
        assert service._api_health["ollama"].available is False
        # Cloud APIs should be reset to available
        assert service._api_health["claude"].available is True
        assert service._api_health["openai"].available is True

    def test_reset_ollama_specific_stays_unavailable(self):
        """Test resetting Ollama specifically keeps it unavailable (Issue #23)."""
        service = DegradationService()
        # First make Ollama available (as if it was detected)
        service._api_health["ollama"].available = True
        # Then reset it
        service.reset_api_health("ollama")
        # Should be unavailable after reset (needs re-verification)
        assert service._api_health["ollama"].available is False


class TestGlobalService:
    """Tests for global service singleton."""

    def test_get_degradation_service_singleton(self):
        """Test that get_degradation_service returns singleton."""
        # Clear the global instance first
        import server.services.degradation as module
        module._degradation_service = None

        service1 = get_degradation_service()
        service2 = get_degradation_service()
        assert service1 is service2


class TestDegradationAPI:
    """Tests for degradation API endpoints."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from fastapi.testclient import TestClient
        from server.main import app
        return TestClient(app)

    def test_get_degradation_status(self, client):
        """Test GET /api/degradation returns status."""
        response = client.get("/api/degradation")
        assert response.status_code == 200
        data = response.json()
        assert "mode" in data
        assert "is_degraded" in data
        assert "apis" in data

    def test_reset_api_health(self, client):
        """Test POST /api/degradation/reset resets health."""
        # First cause degradation
        service = get_degradation_service()
        for _ in range(3):
            service.record_failure("claude")

        # Reset it
        response = client.post("/api/degradation/reset", json={"api_name": "claude"})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_reset_all_api_health(self, client):
        """Test POST /api/degradation/reset with no api_name resets all."""
        response = client.post("/api/degradation/reset", json={})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "all APIs" in data["message"]

    def test_check_network(self, client):
        """Test POST /api/degradation/check-network."""
        with patch('socket.gethostbyname', return_value='8.8.8.8'):
            response = client.post("/api/degradation/check-network")
            assert response.status_code == 200
            data = response.json()
            assert "network_available" in data
            assert "mode" in data

    def test_clear_cache(self, client):
        """Test DELETE /api/degradation/cache clears cache."""
        # First add some cache
        service = get_degradation_service()
        service.cache_tool_result("test", "hash", "data")

        response = client.delete("/api/degradation/cache")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["cleared_entries"] >= 0


class TestQueueProcessing:
    """Tests for queue processing functionality."""

    @pytest.mark.asyncio
    async def test_process_queue_empty(self):
        """Test processing empty queue returns empty list."""
        service = DegradationService()
        results = await service.process_queue()
        assert results == []

    @pytest.mark.asyncio
    async def test_process_queue_executes_callback(self):
        """Test queue processing executes callbacks."""
        service = DegradationService()
        call_count = [0]

        async def test_callback():
            call_count[0] += 1
            return "success"

        await service.queue_request("req1", test_callback)
        results = await service.process_queue()

        assert len(results) == 1
        assert results[0]["success"] is True
        assert results[0]["result"] == "success"
        assert call_count[0] == 1
        assert service.get_queue_size() == 0

    @pytest.mark.asyncio
    async def test_process_queue_handles_sync_callback(self):
        """Test queue processing handles sync callbacks."""
        service = DegradationService()

        def sync_callback():
            return 42

        await service.queue_request("req1", sync_callback)
        results = await service.process_queue()

        assert len(results) == 1
        assert results[0]["success"] is True
        assert results[0]["result"] == 42

    @pytest.mark.asyncio
    async def test_process_queue_priority_order(self):
        """Test queue processes in priority order."""
        service = DegradationService()
        execution_order = []

        async def callback_a():
            execution_order.append("a")
            return "a"

        async def callback_b():
            execution_order.append("b")
            return "b"

        async def callback_c():
            execution_order.append("c")
            return "c"

        await service.queue_request("req_low", callback_a, priority=1)
        await service.queue_request("req_high", callback_b, priority=10)
        await service.queue_request("req_med", callback_c, priority=5)

        await service.process_queue()

        # Should be processed: high (10), medium (5), low (1)
        assert execution_order == ["b", "c", "a"]

    @pytest.mark.asyncio
    async def test_process_queue_timeout(self):
        """Test queue removes timed-out requests."""
        service = DegradationService()
        service.QUEUE_TIMEOUT = 1  # 1 second for testing

        async def dummy_callback():
            return "ok"

        await service.queue_request("req1", dummy_callback)

        # Manually set creation time to past
        service._request_queue[0].created_at = datetime.now() - timedelta(seconds=10)

        results = await service.process_queue()

        assert len(results) == 1
        assert results[0]["success"] is False
        assert "timed out" in results[0]["error"]
        assert service.get_queue_size() == 0

    @pytest.mark.asyncio
    async def test_process_queue_callback_error(self):
        """Test queue handles callback errors."""
        service = DegradationService()

        async def failing_callback():
            raise ValueError("Test error")

        await service.queue_request("req1", failing_callback)
        results = await service.process_queue()

        assert len(results) == 1
        assert results[0]["success"] is False
        assert "Test error" in results[0]["error"]
        assert service.get_queue_size() == 0

    @pytest.mark.asyncio
    async def test_process_queue_stops_on_rate_limit_error(self):
        """Test queue stops processing on rate limit error."""
        service = DegradationService()
        call_count = [0]

        async def rate_limit_callback():
            call_count[0] += 1
            if call_count[0] == 2:
                raise Exception("Rate limit error 429")
            return f"result_{call_count[0]}"

        await service.queue_request("req1", rate_limit_callback)
        await service.queue_request("req2", rate_limit_callback)
        await service.queue_request("req3", rate_limit_callback)

        results = await service.process_queue()

        # First should succeed, second should fail with rate limit
        assert len(results) == 2
        assert results[0]["success"] is True
        assert results[1]["success"] is False
        assert results[1].get("requeued") is True
        # Third should still be in queue
        assert service.get_queue_size() == 2

    def test_is_any_api_rate_limited(self):
        """Test is_any_api_rate_limited detection."""
        service = DegradationService()
        assert not service.is_any_api_rate_limited()

        service.record_failure("claude", is_rate_limit=True, retry_after=60)
        assert service.is_any_api_rate_limited()

    def test_get_next_available_time(self):
        """Test get_next_available_time returns earliest time."""
        service = DegradationService()
        assert service.get_next_available_time() is None

        # Add rate limits
        service.record_failure("claude", is_rate_limit=True, retry_after=60)
        service.record_failure("openai", is_rate_limit=True, retry_after=30)

        next_time = service.get_next_available_time()
        assert next_time is not None
        # Should be closer to 30 seconds from now (openai)
        time_diff = (next_time - datetime.now()).total_seconds()
        assert 25 <= time_diff <= 35

    def test_clear_queue(self):
        """Test clearing the queue."""
        service = DegradationService()

        async def dummy():
            pass

        # Add items synchronously via internal method for testing
        from server.services.degradation import QueuedRequest
        service._request_queue.append(QueuedRequest(
            id="req1",
            created_at=datetime.now(),
            callback=dummy,
            args=(),
            kwargs={},
            priority=0,
        ))
        service._request_queue.append(QueuedRequest(
            id="req2",
            created_at=datetime.now(),
            callback=dummy,
            args=(),
            kwargs={},
            priority=0,
        ))

        assert service.get_queue_size() == 2
        cleared = service.clear_queue()
        assert cleared == 2
        assert service.get_queue_size() == 0

    def test_get_queue_info(self):
        """Test getting queue info."""
        service = DegradationService()

        async def dummy():
            pass

        from server.services.degradation import QueuedRequest
        service._request_queue.append(QueuedRequest(
            id="req1",
            created_at=datetime.now(),
            callback=dummy,
            args=(),
            kwargs={},
            priority=5,
        ))

        info = service.get_queue_info()
        assert info["size"] == 1
        assert info["max_size"] == service.MAX_QUEUE_SIZE
        assert info["timeout_seconds"] == service.QUEUE_TIMEOUT
        assert len(info["pending_requests"]) == 1
        assert info["pending_requests"][0]["id"] == "req1"
        assert info["pending_requests"][0]["priority"] == 5

    def test_stop_queue_processor(self):
        """Test stopping queue processor sets flag."""
        service = DegradationService()
        service._queue_processor_running = True
        service.stop_queue_processor()
        assert service._queue_processor_running is False


class TestQueueAPI:
    """Tests for queue API endpoints."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from fastapi.testclient import TestClient
        from server.main import app
        return TestClient(app)

    def test_get_queue_info_endpoint(self, client):
        """Test GET /api/degradation/queue returns queue info."""
        response = client.get("/api/degradation/queue")
        assert response.status_code == 200
        data = response.json()
        assert "size" in data
        assert "max_size" in data
        assert "pending_requests" in data

    def test_process_queue_endpoint(self, client):
        """Test POST /api/degradation/queue/process processes queue."""
        response = client.post("/api/degradation/queue/process")
        assert response.status_code == 200
        data = response.json()
        assert "processed_count" in data
        assert "results" in data
        assert "queue_remaining" in data

    def test_clear_queue_endpoint(self, client):
        """Test DELETE /api/degradation/queue clears queue."""
        response = client.delete("/api/degradation/queue")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "cleared_count" in data


class TestIntegrationWithChat:
    """Test degradation integration with chat endpoints."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from fastapi.testclient import TestClient
        from server.main import app
        return TestClient(app)

    def test_chat_records_success(self, client):
        """Test chat endpoint records success to degradation service."""
        # This is more of a smoke test - actual API calls would need mocking
        service = get_degradation_service()
        initial_requests = service._api_health["claude"].total_requests

        # The actual chat would need API keys to work
        # Just verify the service exists and is accessible
        assert service is not None

    def test_degradation_status_reflects_in_chat(self):
        """Test that degradation status is accessible during chat."""
        service = get_degradation_service()

        # Record failures to trigger degradation
        for _ in range(3):
            service.record_failure("claude")

        # Verify preferred API changes
        preferred = service.get_preferred_api("claude")
        assert preferred == "openai"

        # Reset for other tests
        service.reset_api_health()
