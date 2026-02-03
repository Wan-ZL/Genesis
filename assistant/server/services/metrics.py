"""Metrics service for tracking API usage and performance."""
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import statistics


@dataclass
class MetricsSnapshot:
    """Point-in-time metrics data."""
    timestamp: str
    uptime_seconds: float
    requests: dict
    latency: dict
    tool_usage: dict
    errors: dict


class MetricsService:
    """Service for collecting and reporting metrics."""

    def __init__(self):
        self._start_time = time.time()
        self._request_counts: dict[str, int] = defaultdict(int)
        self._error_counts: dict[str, int] = defaultdict(int)
        self._latencies: dict[str, list[float]] = defaultdict(list)
        self._tool_calls: dict[str, int] = defaultdict(int)
        self._max_latency_samples = 1000  # Keep last N samples per endpoint

    def record_request(self, endpoint: str, latency_ms: float, success: bool = True):
        """Record a request with its latency."""
        self._request_counts[endpoint] += 1

        # Track latency
        latencies = self._latencies[endpoint]
        latencies.append(latency_ms)
        if len(latencies) > self._max_latency_samples:
            latencies.pop(0)

        if not success:
            self._error_counts[endpoint] += 1

    def record_tool_call(self, tool_name: str):
        """Record a tool invocation."""
        self._tool_calls[tool_name] += 1

    def record_error(self, endpoint: str, error_type: str = "unknown"):
        """Record an error for an endpoint."""
        self._error_counts[f"{endpoint}:{error_type}"] += 1

    def _calculate_latency_stats(self, latencies: list[float]) -> dict:
        """Calculate latency statistics for a list of values."""
        if not latencies:
            return {"avg": 0, "min": 0, "max": 0, "p50": 0, "p95": 0, "p99": 0}

        sorted_latencies = sorted(latencies)
        n = len(sorted_latencies)

        def percentile(p: float) -> float:
            idx = int(n * p / 100)
            return sorted_latencies[min(idx, n - 1)]

        return {
            "avg": round(statistics.mean(latencies), 2),
            "min": round(min(latencies), 2),
            "max": round(max(latencies), 2),
            "p50": round(percentile(50), 2),
            "p95": round(percentile(95), 2),
            "p99": round(percentile(99), 2),
        }

    def get_snapshot(self) -> MetricsSnapshot:
        """Get current metrics snapshot."""
        now = datetime.now()
        uptime = time.time() - self._start_time

        # Calculate latency stats per endpoint
        latency_stats = {}
        for endpoint, latencies in self._latencies.items():
            latency_stats[endpoint] = self._calculate_latency_stats(latencies)

        return MetricsSnapshot(
            timestamp=now.isoformat(),
            uptime_seconds=round(uptime, 2),
            requests=dict(self._request_counts),
            latency=latency_stats,
            tool_usage=dict(self._tool_calls),
            errors=dict(self._error_counts),
        )

    def to_dict(self) -> dict:
        """Convert metrics to dictionary for JSON response."""
        snapshot = self.get_snapshot()

        # Calculate totals
        total_requests = sum(snapshot.requests.values())
        total_errors = sum(snapshot.errors.values())

        # Calculate overall latency stats
        all_latencies = []
        for latencies in self._latencies.values():
            all_latencies.extend(latencies)
        overall_latency = self._calculate_latency_stats(all_latencies)

        return {
            "timestamp": snapshot.timestamp,
            "uptime": {
                "seconds": snapshot.uptime_seconds,
                "formatted": self._format_uptime(snapshot.uptime_seconds),
            },
            "requests": {
                "total": total_requests,
                "by_endpoint": snapshot.requests,
            },
            "errors": {
                "total": total_errors,
                "by_endpoint": snapshot.errors,
                "rate": round(total_errors / max(total_requests, 1) * 100, 2),
            },
            "latency": {
                "overall": overall_latency,
                "by_endpoint": snapshot.latency,
            },
            "tools": {
                "total_calls": sum(snapshot.tool_usage.values()),
                "by_tool": snapshot.tool_usage,
            },
        }

    def _format_uptime(self, seconds: float) -> str:
        """Format uptime as human-readable string."""
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        parts.append(f"{secs}s")

        return " ".join(parts)

    def reset(self):
        """Reset all metrics (useful for testing)."""
        self._start_time = time.time()
        self._request_counts.clear()
        self._error_counts.clear()
        self._latencies.clear()
        self._tool_calls.clear()


# Global metrics instance
metrics = MetricsService()
