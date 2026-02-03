"""Tests for capabilities and permissions API."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import os

from server.main import app
from core.permissions import PermissionLevel, get_permission_level, set_permission_level
from core.capability_scanner import Capability, CapabilityType


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_permission_level():
    """Reset permission level before and after each test."""
    original_level = get_permission_level()
    yield
    set_permission_level(original_level)


class TestCapabilitiesAPI:
    """Tests for /api/capabilities endpoints."""

    def test_list_capabilities(self, client):
        """Test listing all capabilities."""
        response = client.get("/api/capabilities")
        assert response.status_code == 200
        data = response.json()

        assert "capabilities" in data
        assert "total" in data
        assert "available" in data
        assert "summary" in data
        assert isinstance(data["capabilities"], list)
        assert data["total"] >= 0
        assert data["available"] >= 0

    def test_list_capabilities_available_only(self, client):
        """Test listing only available capabilities."""
        response = client.get("/api/capabilities?available_only=true")
        assert response.status_code == 200
        data = response.json()

        # All returned capabilities should be available
        for cap in data["capabilities"]:
            assert cap["available"] is True

    def test_list_capabilities_type_filter(self, client):
        """Test filtering capabilities by type."""
        response = client.get("/api/capabilities?type_filter=cli_tool")
        assert response.status_code == 200
        data = response.json()

        # All returned capabilities should be CLI tools
        for cap in data["capabilities"]:
            assert cap["type"] == "cli_tool"

    def test_list_capabilities_invalid_type_filter(self, client):
        """Test invalid type filter returns error."""
        response = client.get("/api/capabilities?type_filter=invalid")
        assert response.status_code == 400
        assert "Invalid type_filter" in response.json()["detail"]

    def test_refresh_capabilities(self, client):
        """Test refreshing capability scan."""
        response = client.post("/api/capabilities/refresh")
        assert response.status_code == 200
        data = response.json()

        assert "capabilities" in data
        assert "total" in data
        assert "available" in data

    def test_capability_response_structure(self, client):
        """Test capability response has correct structure."""
        response = client.get("/api/capabilities")
        assert response.status_code == 200
        data = response.json()

        if data["capabilities"]:
            cap = data["capabilities"][0]
            assert "name" in cap
            assert "type" in cap
            assert "available" in cap
            # Optional fields
            assert "path" in cap
            assert "version" in cap
            assert "description" in cap


class TestPermissionsAPI:
    """Tests for /api/permissions endpoints."""

    def test_get_permissions(self, client):
        """Test getting current permission level."""
        response = client.get("/api/permissions")
        assert response.status_code == 200
        data = response.json()

        assert "level" in data
        assert "name" in data
        assert "description" in data
        assert data["level"] in [0, 1, 2, 3]
        assert data["name"] in ["SANDBOX", "LOCAL", "SYSTEM", "FULL"]

    def test_list_permission_levels(self, client):
        """Test listing all permission levels."""
        response = client.get("/api/permissions/levels")
        assert response.status_code == 200
        data = response.json()

        assert "levels" in data
        assert len(data["levels"]) == 4

        # Check all levels are present
        levels = {l["name"] for l in data["levels"]}
        assert levels == {"SANDBOX", "LOCAL", "SYSTEM", "FULL"}

    def test_update_permission_to_sandbox(self, client):
        """Test setting permission to SANDBOX."""
        response = client.post(
            "/api/permissions",
            json={"level": 0}
        )
        assert response.status_code == 200
        data = response.json()

        assert data["level"] == 0
        assert data["name"] == "SANDBOX"
        assert get_permission_level() == PermissionLevel.SANDBOX

    def test_update_permission_to_local(self, client):
        """Test setting permission to LOCAL."""
        response = client.post(
            "/api/permissions",
            json={"level": 1}
        )
        assert response.status_code == 200
        data = response.json()

        assert data["level"] == 1
        assert data["name"] == "LOCAL"
        assert get_permission_level() == PermissionLevel.LOCAL

    def test_update_permission_to_system(self, client):
        """Test setting permission to SYSTEM."""
        response = client.post(
            "/api/permissions",
            json={"level": 2}
        )
        assert response.status_code == 200
        data = response.json()

        assert data["level"] == 2
        assert data["name"] == "SYSTEM"
        assert get_permission_level() == PermissionLevel.SYSTEM

    def test_update_permission_to_full(self, client):
        """Test setting permission to FULL."""
        response = client.post(
            "/api/permissions",
            json={"level": 3}
        )
        assert response.status_code == 200
        data = response.json()

        assert data["level"] == 3
        assert data["name"] == "FULL"
        assert get_permission_level() == PermissionLevel.FULL

    def test_update_permission_invalid_level(self, client):
        """Test invalid permission level returns error."""
        response = client.post(
            "/api/permissions",
            json={"level": 5}
        )
        assert response.status_code == 400
        assert "Invalid permission level" in response.json()["detail"]

    def test_update_permission_negative_level(self, client):
        """Test negative permission level returns error."""
        response = client.post(
            "/api/permissions",
            json={"level": -1}
        )
        assert response.status_code == 400


class TestCapabilityScanner:
    """Additional tests for capability scanner integration."""

    def test_scanner_caches_results(self, client):
        """Test that scanner results are cached between requests."""
        # First request
        response1 = client.get("/api/capabilities")
        assert response1.status_code == 200
        data1 = response1.json()

        # Second request should return same data
        response2 = client.get("/api/capabilities")
        assert response2.status_code == 200
        data2 = response2.json()

        assert data1["total"] == data2["total"]
        assert data1["available"] == data2["available"]

    def test_combined_filters(self, client):
        """Test combining available_only and type_filter."""
        response = client.get("/api/capabilities?available_only=true&type_filter=cli_tool")
        assert response.status_code == 200
        data = response.json()

        for cap in data["capabilities"]:
            assert cap["available"] is True
            assert cap["type"] == "cli_tool"

    def test_service_type_filter(self, client):
        """Test filtering by service type."""
        response = client.get("/api/capabilities?type_filter=service")
        assert response.status_code == 200
        data = response.json()

        for cap in data["capabilities"]:
            assert cap["type"] == "service"

    def test_system_type_filter(self, client):
        """Test filtering by system type."""
        response = client.get("/api/capabilities?type_filter=system")
        assert response.status_code == 200
        data = response.json()

        for cap in data["capabilities"]:
            assert cap["type"] == "system"
