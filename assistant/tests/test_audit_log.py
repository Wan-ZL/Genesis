"""Tests for the audit log service and API endpoints."""
import os
import sys
import pytest
import asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime

# Add assistant directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from server.services.audit_log import AuditLogService


class TestAuditLogService:
    """Tests for AuditLogService."""

    @pytest.fixture
    def temp_db(self, tmp_path):
        """Create a temporary database path."""
        return tmp_path / "test_audit.db"

    @pytest.fixture
    def audit_service(self, temp_db):
        """Create an AuditLogService instance."""
        return AuditLogService(temp_db)

    @pytest.mark.asyncio
    async def test_log_permission_change_basic(self, audit_service):
        """Test logging a basic permission change."""
        log_id = await audit_service.log_permission_change(
            old_level=1,
            old_level_name="LOCAL",
            new_level=2,
            new_level_name="SYSTEM",
            source="api"
        )
        assert log_id.startswith("audit_")
        assert len(log_id) == 18  # "audit_" + 12 hex chars

    @pytest.mark.asyncio
    async def test_log_permission_change_with_metadata(self, audit_service):
        """Test logging with full metadata."""
        log_id = await audit_service.log_permission_change(
            old_level=0,
            old_level_name="SANDBOX",
            new_level=3,
            new_level_name="FULL",
            source="cli",
            ip_address="192.168.1.100",
            user_agent="Mozilla/5.0 Test",
            reason="User requested full access for debugging"
        )
        assert log_id.startswith("audit_")

    @pytest.mark.asyncio
    async def test_get_audit_log_empty(self, audit_service):
        """Test getting audit log when empty."""
        entries = await audit_service.get_audit_log()
        assert entries == []

    @pytest.mark.asyncio
    async def test_get_audit_log_returns_entries(self, audit_service):
        """Test getting audit log with entries."""
        # Log a few changes
        await audit_service.log_permission_change(
            old_level=0, old_level_name="SANDBOX",
            new_level=1, new_level_name="LOCAL",
            source="api"
        )
        await audit_service.log_permission_change(
            old_level=1, old_level_name="LOCAL",
            new_level=2, new_level_name="SYSTEM",
            source="cli"
        )

        entries = await audit_service.get_audit_log()
        assert len(entries) == 2
        # Most recent first
        assert entries[0]["old_level_name"] == "LOCAL"
        assert entries[0]["new_level_name"] == "SYSTEM"
        assert entries[0]["source"] == "cli"

    @pytest.mark.asyncio
    async def test_get_audit_log_entry_format(self, audit_service):
        """Test that audit log entries have correct format."""
        await audit_service.log_permission_change(
            old_level=1, old_level_name="LOCAL",
            new_level=2, new_level_name="SYSTEM",
            source="api",
            ip_address="127.0.0.1",
            user_agent="Test/1.0",
            reason="Testing"
        )

        entries = await audit_service.get_audit_log()
        entry = entries[0]

        assert "id" in entry
        assert "timestamp" in entry
        assert entry["old_level"] == 1
        assert entry["old_level_name"] == "LOCAL"
        assert entry["new_level"] == 2
        assert entry["new_level_name"] == "SYSTEM"
        assert entry["source"] == "api"
        assert entry["ip_address"] == "127.0.0.1"
        assert entry["user_agent"] == "Test/1.0"
        assert entry["reason"] == "Testing"
        assert entry["change"] == "LOCAL (1) -> SYSTEM (2)"

    @pytest.mark.asyncio
    async def test_get_audit_log_pagination(self, audit_service):
        """Test pagination works correctly."""
        # Log 5 changes
        for i in range(5):
            await audit_service.log_permission_change(
                old_level=i, old_level_name=f"LEVEL_{i}",
                new_level=i+1, new_level_name=f"LEVEL_{i+1}",
                source="api"
            )

        # Get first 2
        entries = await audit_service.get_audit_log(limit=2, offset=0)
        assert len(entries) == 2
        # Most recent (level 4->5) should be first
        assert entries[0]["old_level"] == 4

        # Get next 2
        entries = await audit_service.get_audit_log(limit=2, offset=2)
        assert len(entries) == 2
        assert entries[0]["old_level"] == 2

    @pytest.mark.asyncio
    async def test_get_audit_log_source_filter(self, audit_service):
        """Test filtering by source."""
        await audit_service.log_permission_change(
            old_level=1, old_level_name="LOCAL",
            new_level=2, new_level_name="SYSTEM",
            source="api"
        )
        await audit_service.log_permission_change(
            old_level=2, old_level_name="SYSTEM",
            new_level=1, new_level_name="LOCAL",
            source="cli"
        )
        await audit_service.log_permission_change(
            old_level=1, old_level_name="LOCAL",
            new_level=0, new_level_name="SANDBOX",
            source="api"
        )

        api_entries = await audit_service.get_audit_log(source_filter="api")
        assert len(api_entries) == 2

        cli_entries = await audit_service.get_audit_log(source_filter="cli")
        assert len(cli_entries) == 1
        assert cli_entries[0]["source"] == "cli"

    @pytest.mark.asyncio
    async def test_get_audit_count(self, audit_service):
        """Test getting total count."""
        assert await audit_service.get_audit_count() == 0

        await audit_service.log_permission_change(
            old_level=1, old_level_name="LOCAL",
            new_level=2, new_level_name="SYSTEM",
            source="api"
        )
        await audit_service.log_permission_change(
            old_level=2, old_level_name="SYSTEM",
            new_level=1, new_level_name="LOCAL",
            source="cli"
        )

        assert await audit_service.get_audit_count() == 2
        assert await audit_service.get_audit_count(source_filter="api") == 1
        assert await audit_service.get_audit_count(source_filter="cli") == 1

    @pytest.mark.asyncio
    async def test_get_latest_change(self, audit_service):
        """Test getting the most recent change."""
        assert await audit_service.get_latest_change() is None

        await audit_service.log_permission_change(
            old_level=0, old_level_name="SANDBOX",
            new_level=1, new_level_name="LOCAL",
            source="api"
        )
        await audit_service.log_permission_change(
            old_level=1, old_level_name="LOCAL",
            new_level=2, new_level_name="SYSTEM",
            source="cli"
        )

        latest = await audit_service.get_latest_change()
        assert latest is not None
        assert latest["old_level_name"] == "LOCAL"
        assert latest["new_level_name"] == "SYSTEM"
        assert latest["source"] == "cli"

    @pytest.mark.asyncio
    async def test_clear_audit_log(self, audit_service):
        """Test clearing the audit log."""
        await audit_service.log_permission_change(
            old_level=1, old_level_name="LOCAL",
            new_level=2, new_level_name="SYSTEM",
            source="api"
        )
        assert await audit_service.get_audit_count() == 1

        await audit_service.clear_audit_log()
        assert await audit_service.get_audit_count() == 0

    @pytest.mark.asyncio
    async def test_timestamp_format(self, audit_service):
        """Test that timestamps are ISO format."""
        await audit_service.log_permission_change(
            old_level=1, old_level_name="LOCAL",
            new_level=2, new_level_name="SYSTEM",
            source="api"
        )

        entries = await audit_service.get_audit_log()
        timestamp = entries[0]["timestamp"]

        # Should be parseable as ISO format
        parsed = datetime.fromisoformat(timestamp)
        assert parsed is not None


class TestAuditLogAPI:
    """Tests for the audit log API endpoints."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        from fastapi.testclient import TestClient
        from server.main import app
        return TestClient(app)

    @pytest.fixture(autouse=True)
    def reset_audit_log(self, tmp_path, monkeypatch):
        """Reset audit log singleton before each test."""
        import server.routes.capabilities as cap_module
        # Clear the singleton so each test gets fresh instance
        cap_module._audit_log = None
        yield
        cap_module._audit_log = None

    def test_get_audit_log_endpoint_exists(self, client):
        """Test that audit log endpoint exists."""
        response = client.get("/api/permissions/audit")
        assert response.status_code == 200
        data = response.json()

        assert "entries" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data

    def test_permission_change_creates_audit_entry(self, client):
        """Test that changing permission creates an audit log entry."""
        from core.permissions import get_permission_level

        # Remember old level
        old_level = get_permission_level()

        # First change permission
        response = client.post(
            "/api/permissions",
            json={"level": 2, "reason": "Testing audit log"}
        )
        assert response.status_code == 200

        # Check audit log
        response = client.get("/api/permissions/audit")
        assert response.status_code == 200
        data = response.json()

        assert data["total"] >= 1
        assert len(data["entries"]) >= 1

        # Find our entry (most recent)
        entry = data["entries"][0]
        assert entry["new_level"] == 2
        assert entry["new_level_name"] == "SYSTEM"
        assert entry["source"] == "api"
        assert entry["reason"] == "Testing audit log"
        assert "change" in entry

    def test_get_audit_log_pagination_params(self, client):
        """Test pagination parameters."""
        response = client.get("/api/permissions/audit?limit=10&offset=5")
        assert response.status_code == 200
        data = response.json()

        assert data["limit"] == 10
        assert data["offset"] == 5

    def test_get_audit_log_source_filter(self, client):
        """Test source filter parameter."""
        response = client.get("/api/permissions/audit?source=cli")
        assert response.status_code == 200
        # Just verify it doesn't error - filtering works at service level

    def test_audit_captures_client_info(self, client):
        """Test that audit log captures client IP and user agent."""
        # Make request with custom user agent
        response = client.post(
            "/api/permissions",
            json={"level": 1},
            headers={"User-Agent": "TestClient/1.0"}
        )
        assert response.status_code == 200

        # Check audit log
        response = client.get("/api/permissions/audit")
        data = response.json()

        if data["total"] > 0:
            entry = data["entries"][0]
            assert entry["user_agent"] == "TestClient/1.0"
            # IP will be testclient
            assert entry["ip_address"] is not None
