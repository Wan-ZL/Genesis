"""Tests for the metrics service."""
import pytest
import time
from server.services.metrics import MetricsService


class TestMetricsService:
    """Tests for MetricsService."""

    def setup_method(self):
        """Reset metrics before each test."""
        self.metrics = MetricsService()

    def test_record_request(self):
        """Test recording a request."""
        self.metrics.record_request("/api/chat", 100.0)
        self.metrics.record_request("/api/chat", 200.0)
        self.metrics.record_request("/api/status", 50.0)

        snapshot = self.metrics.get_snapshot()
        assert snapshot.requests["/api/chat"] == 2
        assert snapshot.requests["/api/status"] == 1

    def test_record_request_with_error(self):
        """Test recording failed requests."""
        self.metrics.record_request("/api/chat", 100.0, success=True)
        self.metrics.record_request("/api/chat", 200.0, success=False)

        snapshot = self.metrics.get_snapshot()
        assert snapshot.requests["/api/chat"] == 2
        assert snapshot.errors["/api/chat"] == 1

    def test_record_tool_call(self):
        """Test recording tool calls."""
        self.metrics.record_tool_call("get_current_datetime")
        self.metrics.record_tool_call("get_current_datetime")
        self.metrics.record_tool_call("calculate")

        snapshot = self.metrics.get_snapshot()
        assert snapshot.tool_usage["get_current_datetime"] == 2
        assert snapshot.tool_usage["calculate"] == 1

    def test_latency_stats(self):
        """Test latency statistics calculation."""
        for latency in [100, 200, 300, 400, 500]:
            self.metrics.record_request("/api/chat", float(latency))

        snapshot = self.metrics.get_snapshot()
        stats = snapshot.latency["/api/chat"]

        assert stats["avg"] == 300.0
        assert stats["min"] == 100.0
        assert stats["max"] == 500.0
        assert stats["p50"] == 300.0

    def test_latency_percentiles(self):
        """Test latency percentile calculations."""
        # Record 100 requests with latencies 1-100ms
        for i in range(1, 101):
            self.metrics.record_request("/api/chat", float(i))

        snapshot = self.metrics.get_snapshot()
        stats = snapshot.latency["/api/chat"]

        # p95 should be around 95
        assert 93 <= stats["p95"] <= 96
        # p99 should be around 99
        assert 97 <= stats["p99"] <= 100

    def test_max_latency_samples(self):
        """Test that latency samples are limited."""
        # Record more than max samples
        for i in range(1500):
            self.metrics.record_request("/api/chat", 100.0)

        # Should only keep last 1000 samples
        assert len(self.metrics._latencies["/api/chat"]) == 1000

    def test_uptime(self):
        """Test uptime tracking."""
        time.sleep(0.1)  # Wait a bit
        snapshot = self.metrics.get_snapshot()
        assert snapshot.uptime_seconds >= 0.1

    def test_format_uptime(self):
        """Test uptime formatting."""
        # Test various durations
        assert self.metrics._format_uptime(30) == "30s"
        assert self.metrics._format_uptime(90) == "1m 30s"
        assert self.metrics._format_uptime(3661) == "1h 1m 1s"
        assert self.metrics._format_uptime(90061) == "1d 1h 1m 1s"

    def test_to_dict(self):
        """Test conversion to dictionary."""
        self.metrics.record_request("/api/chat", 100.0)
        self.metrics.record_tool_call("calculate")

        data = self.metrics.to_dict()

        assert "timestamp" in data
        assert "uptime" in data
        assert "requests" in data
        assert "errors" in data
        assert "latency" in data
        assert "tools" in data

        assert data["requests"]["total"] == 1
        assert data["tools"]["total_calls"] == 1

    def test_error_rate_calculation(self):
        """Test error rate calculation."""
        self.metrics.record_request("/api/chat", 100.0, success=True)
        self.metrics.record_request("/api/chat", 200.0, success=True)
        self.metrics.record_request("/api/chat", 300.0, success=False)
        self.metrics.record_request("/api/chat", 400.0, success=False)

        data = self.metrics.to_dict()
        # 2 errors out of 4 requests = 50%
        assert data["errors"]["rate"] == 50.0

    def test_reset(self):
        """Test metrics reset."""
        self.metrics.record_request("/api/chat", 100.0)
        self.metrics.record_tool_call("calculate")
        self.metrics.record_error("/api/chat", "ValueError")

        self.metrics.reset()

        data = self.metrics.to_dict()
        assert data["requests"]["total"] == 0
        assert data["tools"]["total_calls"] == 0
        assert data["errors"]["total"] == 0

    def test_empty_latency_stats(self):
        """Test latency stats with no data."""
        stats = self.metrics._calculate_latency_stats([])
        assert stats["avg"] == 0
        assert stats["min"] == 0
        assert stats["max"] == 0

    def test_record_error_with_type(self):
        """Test recording errors with type."""
        self.metrics.record_error("/api/chat", "ValueError")
        self.metrics.record_error("/api/chat", "TimeoutError")
        self.metrics.record_error("/api/chat", "ValueError")

        snapshot = self.metrics.get_snapshot()
        assert snapshot.errors["/api/chat:ValueError"] == 2
        assert snapshot.errors["/api/chat:TimeoutError"] == 1
