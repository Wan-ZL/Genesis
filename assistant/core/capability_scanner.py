"""Capability scanner for discovering available tools and system capabilities.

Scans for:
- CLI tools (brew, git, python, node, etc.)
- System capabilities (file access, network, clipboard)
- Running services (Docker, databases, etc.)
"""
import os
import shutil
import subprocess
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class CapabilityType(str, Enum):
    """Types of capabilities that can be discovered."""
    CLI_TOOL = "cli_tool"
    SERVICE = "service"
    SYSTEM = "system"
    MCP_SERVER = "mcp_server"


@dataclass
class Capability:
    """Represents a discovered capability."""
    name: str
    type: CapabilityType
    available: bool
    path: Optional[str] = None
    version: Optional[str] = None
    description: Optional[str] = None
    discovered_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        d = asdict(self)
        d['type'] = self.type.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> 'Capability':
        """Create from dictionary."""
        data = data.copy()
        data['type'] = CapabilityType(data['type'])
        return cls(**data)


# Common CLI tools to scan for
CLI_TOOLS = [
    ("git", "Version control"),
    ("python3", "Python interpreter"),
    ("python", "Python interpreter (alt)"),
    ("node", "Node.js runtime"),
    ("npm", "Node package manager"),
    ("brew", "Homebrew package manager"),
    ("docker", "Container runtime"),
    ("docker-compose", "Docker Compose"),
    ("curl", "HTTP client"),
    ("wget", "File downloader"),
    ("jq", "JSON processor"),
    ("sqlite3", "SQLite database"),
    ("psql", "PostgreSQL client"),
    ("mysql", "MySQL client"),
    ("redis-cli", "Redis client"),
    ("aws", "AWS CLI"),
    ("gcloud", "Google Cloud CLI"),
    ("az", "Azure CLI"),
    ("kubectl", "Kubernetes CLI"),
    ("terraform", "Infrastructure as code"),
    ("ffmpeg", "Media processor"),
    ("gh", "GitHub CLI"),
    ("code", "VS Code"),
]

# Services to check
SERVICES = [
    ("docker", "Docker daemon"),
    ("postgresql", "PostgreSQL database"),
    ("mysql", "MySQL database"),
    ("redis", "Redis server"),
    ("nginx", "Web server"),
    ("supervisord", "Process manager"),
]


class CapabilityScanner:
    """Scans for and tracks available system capabilities."""

    def __init__(self, cache_path: Optional[Path] = None):
        """Initialize the scanner.

        Args:
            cache_path: Path to cache capabilities. If None, uses memory/capabilities.json
        """
        if cache_path is None:
            from config import BASE_DIR
            cache_path = BASE_DIR / "memory" / "capabilities.json"
        self.cache_path = Path(cache_path)
        self.capabilities: dict[str, Capability] = {}
        self._load_cache()

    def _load_cache(self) -> None:
        """Load capabilities from cache file."""
        if self.cache_path.exists():
            try:
                data = json.loads(self.cache_path.read_text())
                self.capabilities = {
                    k: Capability.from_dict(v) for k, v in data.items()
                }
                logger.info(f"Loaded {len(self.capabilities)} capabilities from cache")
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to load capability cache: {e}")
                self.capabilities = {}

    def _save_cache(self) -> None:
        """Save capabilities to cache file."""
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        data = {k: v.to_dict() for k, v in self.capabilities.items()}
        self.cache_path.write_text(json.dumps(data, indent=2))
        logger.info(f"Saved {len(self.capabilities)} capabilities to cache")

    def scan_cli_tool(self, name: str, description: str = "") -> Capability:
        """Check if a CLI tool is available.

        Args:
            name: Command name to check
            description: Human-readable description

        Returns:
            Capability object with availability status
        """
        path = shutil.which(name)
        available = path is not None
        version = None

        if available:
            # Try to get version
            version = self._get_tool_version(name)

        cap = Capability(
            name=name,
            type=CapabilityType.CLI_TOOL,
            available=available,
            path=path,
            version=version,
            description=description,
        )
        self.capabilities[name] = cap
        return cap

    def _get_tool_version(self, name: str) -> Optional[str]:
        """Try to get version of a tool."""
        version_flags = ["--version", "-v", "version"]

        for flag in version_flags:
            try:
                result = subprocess.run(
                    [name, flag],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0 and result.stdout:
                    # Take first line, truncate if too long
                    version = result.stdout.strip().split('\n')[0][:100]
                    return version
            except (subprocess.TimeoutExpired, FileNotFoundError, PermissionError):
                continue
        return None

    def scan_service(self, name: str, description: str = "") -> Capability:
        """Check if a service is running.

        Args:
            name: Service name to check
            description: Human-readable description

        Returns:
            Capability object with availability status
        """
        available = False
        metadata = {}

        # Try different methods to check service status
        if name == "docker":
            available = self._check_docker_running()
        elif name in ("postgresql", "mysql", "redis"):
            available = self._check_port_listening(name)
        else:
            # Try launchctl on macOS
            available = self._check_launchctl(name)

        cap = Capability(
            name=name,
            type=CapabilityType.SERVICE,
            available=available,
            description=description,
            metadata=metadata,
        )
        self.capabilities[f"service:{name}"] = cap
        return cap

    def _check_docker_running(self) -> bool:
        """Check if Docker daemon is running."""
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _check_port_listening(self, service: str) -> bool:
        """Check if common ports for a service are listening."""
        ports = {
            "postgresql": 5432,
            "mysql": 3306,
            "redis": 6379,
        }
        port = ports.get(service)
        if not port:
            return False

        try:
            result = subprocess.run(
                ["lsof", "-i", f":{port}"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0 and bool(result.stdout)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _check_launchctl(self, name: str) -> bool:
        """Check if a launchd service is running (macOS)."""
        try:
            result = subprocess.run(
                ["launchctl", "list"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return name in result.stdout
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def scan_system_capabilities(self) -> list[Capability]:
        """Scan basic system capabilities."""
        caps = []

        # File system access
        caps.append(Capability(
            name="file_read",
            type=CapabilityType.SYSTEM,
            available=True,  # Always available at SANDBOX
            description="Read files from allowed paths",
        ))

        caps.append(Capability(
            name="file_write",
            type=CapabilityType.SYSTEM,
            available=True,  # Always available at SANDBOX
            description="Write files to allowed paths",
        ))

        # Network access
        caps.append(Capability(
            name="network_http",
            type=CapabilityType.SYSTEM,
            available=True,
            description="Make HTTP/HTTPS requests",
        ))

        # Clipboard (check pbcopy/pbpaste on macOS)
        clipboard_available = shutil.which("pbcopy") is not None
        caps.append(Capability(
            name="clipboard",
            type=CapabilityType.SYSTEM,
            available=clipboard_available,
            description="Access system clipboard",
        ))

        for cap in caps:
            self.capabilities[cap.name] = cap

        return caps

    def scan_all(self) -> dict[str, Capability]:
        """Perform a full scan of all capabilities.

        Returns:
            Dictionary of all discovered capabilities
        """
        logger.info("Starting full capability scan...")

        # Scan CLI tools
        for name, description in CLI_TOOLS:
            self.scan_cli_tool(name, description)

        # Scan services
        for name, description in SERVICES:
            self.scan_service(name, description)

        # Scan system capabilities
        self.scan_system_capabilities()

        # Save to cache
        self._save_cache()

        available_count = sum(1 for c in self.capabilities.values() if c.available)
        logger.info(
            f"Capability scan complete: {available_count}/{len(self.capabilities)} available"
        )

        return self.capabilities

    def get_available(self) -> dict[str, Capability]:
        """Get only available capabilities."""
        return {k: v for k, v in self.capabilities.items() if v.available}

    def get_by_type(self, cap_type: CapabilityType) -> dict[str, Capability]:
        """Get capabilities of a specific type."""
        return {k: v for k, v in self.capabilities.items() if v.type == cap_type}

    def get_summary(self) -> str:
        """Get a human-readable summary of capabilities."""
        available = self.get_available()
        by_type = {}
        for cap in available.values():
            by_type.setdefault(cap.type.value, []).append(cap.name)

        lines = ["Available capabilities:"]
        for cap_type, names in sorted(by_type.items()):
            lines.append(f"  {cap_type}: {', '.join(sorted(names))}")

        return '\n'.join(lines)

    def refresh(self) -> dict[str, Capability]:
        """Force a full rescan of all capabilities."""
        self.capabilities = {}
        return self.scan_all()
