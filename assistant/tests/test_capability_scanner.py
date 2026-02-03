"""Tests for the capability scanner."""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from core.capability_scanner import (
    CapabilityScanner,
    Capability,
    CapabilityType,
    CLI_TOOLS,
)


class TestCapability:
    """Tests for the Capability dataclass."""

    def test_create_capability(self):
        """Should create a capability with required fields."""
        cap = Capability(
            name="git",
            type=CapabilityType.CLI_TOOL,
            available=True,
        )
        assert cap.name == "git"
        assert cap.type == CapabilityType.CLI_TOOL
        assert cap.available is True

    def test_capability_with_all_fields(self):
        """Should create capability with all optional fields."""
        cap = Capability(
            name="python3",
            type=CapabilityType.CLI_TOOL,
            available=True,
            path="/usr/bin/python3",
            version="Python 3.11.0",
            description="Python interpreter",
            metadata={"extra": "data"},
        )
        assert cap.path == "/usr/bin/python3"
        assert cap.version == "Python 3.11.0"
        assert cap.description == "Python interpreter"
        assert cap.metadata == {"extra": "data"}

    def test_to_dict(self):
        """Should convert to dictionary correctly."""
        cap = Capability(
            name="git",
            type=CapabilityType.CLI_TOOL,
            available=True,
            path="/usr/bin/git",
        )
        d = cap.to_dict()
        assert d["name"] == "git"
        assert d["type"] == "cli_tool"  # String value
        assert d["available"] is True
        assert d["path"] == "/usr/bin/git"

    def test_from_dict(self):
        """Should create from dictionary correctly."""
        d = {
            "name": "node",
            "type": "cli_tool",
            "available": True,
            "path": "/usr/local/bin/node",
            "version": "v18.0.0",
            "description": "Node.js",
            "discovered_at": "2026-02-03T10:00:00",
            "metadata": {},
        }
        cap = Capability.from_dict(d)
        assert cap.name == "node"
        assert cap.type == CapabilityType.CLI_TOOL
        assert cap.available is True

    def test_to_dict_from_dict_roundtrip(self):
        """Should survive to_dict/from_dict roundtrip."""
        original = Capability(
            name="docker",
            type=CapabilityType.SERVICE,
            available=False,
            description="Container runtime",
        )
        d = original.to_dict()
        restored = Capability.from_dict(d)
        assert restored.name == original.name
        assert restored.type == original.type
        assert restored.available == original.available


class TestCapabilityType:
    """Tests for CapabilityType enum."""

    def test_all_types_exist(self):
        """All expected capability types should exist."""
        assert CapabilityType.CLI_TOOL
        assert CapabilityType.SERVICE
        assert CapabilityType.SYSTEM
        assert CapabilityType.MCP_SERVER

    def test_types_are_strings(self):
        """Capability types should be string enums for JSON."""
        assert CapabilityType.CLI_TOOL.value == "cli_tool"
        assert CapabilityType.SERVICE.value == "service"


class TestCapabilityScanner:
    """Tests for CapabilityScanner class."""

    @pytest.fixture
    def temp_cache(self):
        """Create a temporary cache file."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            yield Path(f.name)
        # Cleanup
        Path(f.name).unlink(missing_ok=True)

    def test_init_creates_empty_capabilities(self, temp_cache):
        """Should initialize with empty capabilities if no cache."""
        scanner = CapabilityScanner(cache_path=temp_cache)
        assert scanner.capabilities == {}

    def test_init_loads_existing_cache(self, temp_cache):
        """Should load capabilities from existing cache."""
        # Write some cached data
        cache_data = {
            "git": {
                "name": "git",
                "type": "cli_tool",
                "available": True,
                "path": "/usr/bin/git",
                "version": "git version 2.39.0",
                "description": "Version control",
                "discovered_at": "2026-02-03T10:00:00",
                "metadata": {},
            }
        }
        temp_cache.write_text(json.dumps(cache_data))

        scanner = CapabilityScanner(cache_path=temp_cache)
        assert "git" in scanner.capabilities
        assert scanner.capabilities["git"].available is True

    def test_scan_cli_tool_available(self, temp_cache):
        """Should detect available CLI tool."""
        scanner = CapabilityScanner(cache_path=temp_cache)

        # 'python3' should be available in most test environments
        with patch("shutil.which") as mock_which:
            mock_which.return_value = "/usr/bin/python3"
            with patch.object(scanner, "_get_tool_version", return_value="3.11.0"):
                cap = scanner.scan_cli_tool("python3", "Python interpreter")

        assert cap.name == "python3"
        assert cap.available is True
        assert cap.path == "/usr/bin/python3"

    def test_scan_cli_tool_not_available(self, temp_cache):
        """Should handle unavailable CLI tool."""
        scanner = CapabilityScanner(cache_path=temp_cache)

        with patch("shutil.which") as mock_which:
            mock_which.return_value = None
            cap = scanner.scan_cli_tool("nonexistent_tool", "Does not exist")

        assert cap.name == "nonexistent_tool"
        assert cap.available is False
        assert cap.path is None

    def test_scan_system_capabilities(self, temp_cache):
        """Should scan basic system capabilities."""
        scanner = CapabilityScanner(cache_path=temp_cache)
        caps = scanner.scan_system_capabilities()

        names = [c.name for c in caps]
        assert "file_read" in names
        assert "file_write" in names
        assert "network_http" in names

    def test_get_available(self, temp_cache):
        """Should filter to only available capabilities."""
        scanner = CapabilityScanner(cache_path=temp_cache)
        scanner.capabilities = {
            "git": Capability("git", CapabilityType.CLI_TOOL, True),
            "docker": Capability("docker", CapabilityType.SERVICE, False),
            "node": Capability("node", CapabilityType.CLI_TOOL, True),
        }

        available = scanner.get_available()
        assert len(available) == 2
        assert "git" in available
        assert "node" in available
        assert "docker" not in available

    def test_get_by_type(self, temp_cache):
        """Should filter capabilities by type."""
        scanner = CapabilityScanner(cache_path=temp_cache)
        scanner.capabilities = {
            "git": Capability("git", CapabilityType.CLI_TOOL, True),
            "docker": Capability("docker", CapabilityType.SERVICE, True),
            "node": Capability("node", CapabilityType.CLI_TOOL, True),
        }

        cli_tools = scanner.get_by_type(CapabilityType.CLI_TOOL)
        assert len(cli_tools) == 2
        assert "git" in cli_tools
        assert "node" in cli_tools

    def test_save_and_load_cache(self, temp_cache):
        """Should save and reload capabilities correctly."""
        scanner = CapabilityScanner(cache_path=temp_cache)
        scanner.capabilities = {
            "git": Capability("git", CapabilityType.CLI_TOOL, True, "/usr/bin/git"),
        }
        scanner._save_cache()

        # Load in new scanner instance
        scanner2 = CapabilityScanner(cache_path=temp_cache)
        assert "git" in scanner2.capabilities
        assert scanner2.capabilities["git"].path == "/usr/bin/git"

    def test_get_summary(self, temp_cache):
        """Should generate readable summary."""
        scanner = CapabilityScanner(cache_path=temp_cache)
        scanner.capabilities = {
            "git": Capability("git", CapabilityType.CLI_TOOL, True),
            "node": Capability("node", CapabilityType.CLI_TOOL, True),
            "docker": Capability("docker", CapabilityType.SERVICE, False),
        }

        summary = scanner.get_summary()
        assert "cli_tool" in summary
        assert "git" in summary
        assert "node" in summary
        # docker is not available, should not appear
        assert "docker" not in summary

    def test_refresh_clears_and_rescans(self, temp_cache):
        """Refresh should clear existing and rescan."""
        scanner = CapabilityScanner(cache_path=temp_cache)
        scanner.capabilities = {"old": Capability("old", CapabilityType.CLI_TOOL, True)}

        with patch.object(scanner, "scan_cli_tool") as mock_cli:
            with patch.object(scanner, "scan_service"):
                with patch.object(scanner, "scan_system_capabilities"):
                    with patch.object(scanner, "_save_cache"):
                        scanner.refresh()

        # Old capability should be gone (cleared before rescan)
        # The mock prevents actual capabilities from being added
        assert "old" not in scanner.capabilities

    def test_scan_service_docker(self, temp_cache):
        """Should check Docker service status."""
        scanner = CapabilityScanner(cache_path=temp_cache)

        with patch.object(scanner, "_check_docker_running", return_value=True):
            cap = scanner.scan_service("docker", "Docker daemon")

        assert cap.name == "docker"
        assert cap.type == CapabilityType.SERVICE
        assert cap.available is True

    def test_cli_tools_list_has_common_tools(self):
        """CLI_TOOLS should include common development tools."""
        names = [t[0] for t in CLI_TOOLS]
        assert "git" in names
        assert "python3" in names
        assert "node" in names
        assert "docker" in names
        assert "curl" in names
