"""
Benchmarks for Settings Service

Critical paths tested:
- Settings load (get individual setting)
- Settings save (set individual setting)
- Settings get_all (load all settings)
"""

import pytest
import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from server.services.settings import SettingsService


@pytest.fixture
def settings_service(tmp_path):
    """Create a settings service with a temporary database."""
    db_path = tmp_path / "bench_settings.db"
    service = SettingsService(db_path)
    return service


@pytest.fixture
def event_loop():
    """Create event loop for async benchmarks."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


class TestSettingsServiceBenchmarks:
    """Benchmarks for SettingsService operations."""

    def test_bench_get_setting_default(self, benchmark, settings_service, event_loop):
        """Benchmark getting a setting (returns default - no DB hit after init)."""

        async def setup():
            await settings_service._ensure_initialized()

        async def get_setting():
            return await settings_service.get("model")

        event_loop.run_until_complete(setup())

        benchmark(lambda: event_loop.run_until_complete(get_setting()))

    def test_bench_get_setting_stored(self, benchmark, settings_service, event_loop):
        """Benchmark getting a stored setting."""

        async def setup():
            await settings_service._ensure_initialized()
            await settings_service.set("custom_setting", "custom_value")

        async def get_setting():
            return await settings_service.get("custom_setting")

        event_loop.run_until_complete(setup())

        benchmark(lambda: event_loop.run_until_complete(get_setting()))

    def test_bench_set_setting(self, benchmark, settings_service, event_loop):
        """Benchmark setting a value."""

        async def setup():
            await settings_service._ensure_initialized()

        i = [0]

        async def set_setting():
            await settings_service.set(f"key_{i[0]}", f"value_{i[0]}")
            i[0] += 1

        event_loop.run_until_complete(setup())

        benchmark(lambda: event_loop.run_until_complete(set_setting()))

    def test_bench_update_setting(self, benchmark, settings_service, event_loop):
        """Benchmark updating an existing setting (upsert)."""

        async def setup():
            await settings_service._ensure_initialized()
            await settings_service.set("update_key", "initial_value")

        i = [0]

        async def update_setting():
            await settings_service.set("update_key", f"updated_{i[0]}")
            i[0] += 1

        event_loop.run_until_complete(setup())

        benchmark(lambda: event_loop.run_until_complete(update_setting()))

    def test_bench_get_all_small(self, benchmark, settings_service, event_loop):
        """Benchmark getting all settings (5 settings)."""

        async def setup():
            await settings_service._ensure_initialized()
            for i in range(5):
                await settings_service.set(f"setting_{i}", f"value_{i}")

        async def get_all():
            return await settings_service.get_all()

        event_loop.run_until_complete(setup())

        benchmark(lambda: event_loop.run_until_complete(get_all()))

    def test_bench_get_all_large(self, benchmark, settings_service, event_loop):
        """Benchmark getting all settings (50 settings)."""

        async def setup():
            await settings_service._ensure_initialized()
            for i in range(50):
                await settings_service.set(f"setting_{i}", f"value_{i}")

        async def get_all():
            return await settings_service.get_all()

        event_loop.run_until_complete(setup())

        benchmark(lambda: event_loop.run_until_complete(get_all()))


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--benchmark-only"])
