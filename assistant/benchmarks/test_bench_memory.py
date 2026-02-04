"""
Benchmarks for Memory Service

Critical paths tested:
- add_message: Adding a message to conversation
- get_messages: Retrieving conversation messages
- search_messages: Full-text search across messages
"""

import pytest
import tempfile
import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from server.services.memory import MemoryService, DEFAULT_CONVERSATION_ID


@pytest.fixture
def memory_service(tmp_path):
    """Create a memory service with a temporary database."""
    db_path = tmp_path / "bench_memory.db"
    service = MemoryService(db_path)
    return service


@pytest.fixture
def event_loop():
    """Create event loop for async benchmarks."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


class TestMemoryServiceBenchmarks:
    """Benchmarks for MemoryService operations."""

    def test_bench_add_message(self, benchmark, memory_service, event_loop):
        """Benchmark adding a single message."""

        async def setup():
            await memory_service._ensure_initialized()
            await memory_service._ensure_default_conversation()

        async def add_message():
            await memory_service.add_to_conversation("user", "Hello, this is a test message!")

        event_loop.run_until_complete(setup())

        # Run benchmark
        benchmark(lambda: event_loop.run_until_complete(add_message()))

    def test_bench_add_message_bulk(self, benchmark, memory_service, event_loop):
        """Benchmark adding 10 messages in sequence."""

        async def setup():
            await memory_service._ensure_initialized()
            await memory_service._ensure_default_conversation()

        async def add_messages():
            for i in range(10):
                await memory_service.add_to_conversation("user", f"Message {i}")

        event_loop.run_until_complete(setup())

        benchmark(lambda: event_loop.run_until_complete(add_messages()))

    def test_bench_get_messages_small(self, benchmark, memory_service, event_loop):
        """Benchmark getting messages from a small conversation (20 messages)."""

        async def setup():
            await memory_service._ensure_initialized()
            await memory_service._ensure_default_conversation()
            for i in range(20):
                await memory_service.add_to_conversation("user", f"Test message {i}")

        async def get_messages():
            return await memory_service.get_messages()

        event_loop.run_until_complete(setup())

        benchmark(lambda: event_loop.run_until_complete(get_messages()))

    def test_bench_get_messages_large(self, benchmark, memory_service, event_loop):
        """Benchmark getting messages from a large conversation (200 messages)."""

        async def setup():
            await memory_service._ensure_initialized()
            await memory_service._ensure_default_conversation()
            for i in range(200):
                await memory_service.add_to_conversation("user", f"Test message {i}")

        async def get_messages():
            return await memory_service.get_messages()

        event_loop.run_until_complete(setup())

        benchmark(lambda: event_loop.run_until_complete(get_messages()))

    def test_bench_get_messages_with_limit(self, benchmark, memory_service, event_loop):
        """Benchmark getting limited messages from large conversation."""

        async def setup():
            await memory_service._ensure_initialized()
            await memory_service._ensure_default_conversation()
            for i in range(200):
                await memory_service.add_to_conversation("user", f"Test message {i}")

        async def get_messages():
            return await memory_service.get_messages(limit=20)

        event_loop.run_until_complete(setup())

        benchmark(lambda: event_loop.run_until_complete(get_messages()))

    def test_bench_search_messages_small(self, benchmark, memory_service, event_loop):
        """Benchmark searching in a small dataset (50 messages)."""

        async def setup():
            await memory_service._ensure_initialized()
            await memory_service._ensure_default_conversation()
            for i in range(50):
                await memory_service.add_to_conversation("user", f"Test message about Python {i}")

        async def search():
            return await memory_service.search_messages("Python")

        event_loop.run_until_complete(setup())

        benchmark(lambda: event_loop.run_until_complete(search()))

    def test_bench_search_messages_large(self, benchmark, memory_service, event_loop):
        """Benchmark searching in a large dataset (500 messages)."""

        async def setup():
            await memory_service._ensure_initialized()
            await memory_service._ensure_default_conversation()
            for i in range(500):
                topic = ["Python", "JavaScript", "Rust", "Go"][i % 4]
                await memory_service.add_to_conversation("user", f"Test message about {topic} {i}")

        async def search():
            return await memory_service.search_messages("Python", limit=20)

        event_loop.run_until_complete(setup())

        benchmark(lambda: event_loop.run_until_complete(search()))

    def test_bench_search_no_results(self, benchmark, memory_service, event_loop):
        """Benchmark search with no results."""

        async def setup():
            await memory_service._ensure_initialized()
            await memory_service._ensure_default_conversation()
            for i in range(100):
                await memory_service.add_to_conversation("user", f"Test message {i}")

        async def search():
            return await memory_service.search_messages("xyznonexistent")

        event_loop.run_until_complete(setup())

        benchmark(lambda: event_loop.run_until_complete(search()))

    def test_bench_get_message_count(self, benchmark, memory_service, event_loop):
        """Benchmark getting total message count."""

        async def setup():
            await memory_service._ensure_initialized()
            await memory_service._ensure_default_conversation()
            for i in range(200):
                await memory_service.add_to_conversation("user", f"Test message {i}")

        async def count():
            return await memory_service.get_message_count()

        event_loop.run_until_complete(setup())

        benchmark(lambda: event_loop.run_until_complete(count()))


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--benchmark-only"])
