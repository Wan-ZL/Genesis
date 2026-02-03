"""Tool suggestion service for proactive capability recommendations.

Analyzes user messages and suggests relevant tools from discovered capabilities.
This enables the AI to proactively inform users about available tools.
"""
import re
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ToolSuggestion:
    """A suggested tool with context for why it's relevant."""
    name: str
    type: str
    description: str
    relevance_reason: str
    usage_hint: Optional[str] = None


# Keyword mappings for common tasks -> relevant tools
# Each entry: keyword_pattern -> [(tool_name, reason, hint)]
TASK_TOOL_MAPPINGS = {
    # Version control
    r"\b(commit|push|pull|branch|merge|git|version control|repo)\b": [
        ("git", "Version control detected", "I can help you with git operations"),
        ("gh", "GitHub operations detected", "I can interact with GitHub via the gh CLI"),
    ],
    # Containers and deployment
    r"\b(docker|container|deploy|image|dockerfile|kubernetes|k8s)\b": [
        ("docker", "Container operations detected", "I can help build and manage Docker containers"),
        ("docker-compose", "Multi-container setup detected", "I can help with docker-compose configurations"),
        ("kubectl", "Kubernetes operations detected", "I can interact with your Kubernetes cluster"),
    ],
    # Python development
    r"\b(python|pip|virtualenv|venv|pytest|django|flask|fastapi)\b": [
        ("python3", "Python development detected", "I can run Python scripts and help with Python tasks"),
    ],
    # JavaScript/Node development
    r"\b(javascript|node|npm|yarn|react|vue|angular|typescript|js)\b": [
        ("node", "Node.js development detected", "I can run Node.js and help with JavaScript tasks"),
        ("npm", "Package management detected", "I can help manage npm packages"),
    ],
    # Database operations
    r"\b(database|sql|query|postgres|mysql|sqlite|redis|db)\b": [
        ("sqlite3", "SQLite operations detected", "I can help with SQLite database queries"),
        ("psql", "PostgreSQL operations detected", "I can connect to PostgreSQL databases"),
        ("mysql", "MySQL operations detected", "I can help with MySQL databases"),
        ("redis-cli", "Redis operations detected", "I can interact with Redis"),
    ],
    # Cloud operations
    r"\b(aws|amazon|s3|ec2|lambda|cloud)\b": [
        ("aws", "AWS operations detected", "I can help with AWS CLI commands"),
    ],
    r"\b(gcloud|google cloud|gcp|bigquery)\b": [
        ("gcloud", "Google Cloud operations detected", "I can help with gcloud commands"),
    ],
    r"\b(azure|az)\b": [
        ("az", "Azure operations detected", "I can help with Azure CLI commands"),
    ],
    # Infrastructure
    r"\b(terraform|infrastructure|iac)\b": [
        ("terraform", "Infrastructure as code detected", "I can help with Terraform configurations"),
    ],
    # Media processing
    r"\b(video|audio|convert|ffmpeg|media|encode|transcode)\b": [
        ("ffmpeg", "Media processing detected", "I can help with audio/video processing"),
    ],
    # HTTP/API operations
    r"\b(api|http|request|curl|fetch|endpoint|rest)\b": [
        ("curl", "HTTP operations detected", "I can make HTTP requests"),
    ],
    # JSON processing
    r"\b(json|parse|jq|format)\b": [
        ("jq", "JSON processing detected", "I can help process and transform JSON data"),
    ],
    # File downloads
    r"\b(download|wget|fetch file)\b": [
        ("wget", "File download detected", "I can help download files"),
        ("curl", "HTTP download detected", "I can download files via HTTP"),
    ],
    # VS Code / editor
    r"\b(vscode|visual studio|editor|code)\b": [
        ("code", "VS Code operations detected", "I can open files in VS Code"),
    ],
    # Package management (macOS)
    r"\b(brew|homebrew|install|package)\b": [
        ("brew", "Package management detected", "I can help install software via Homebrew"),
    ],
    # Shell/terminal operations
    r"\b(shell|terminal|command|run|execute|bash)\b": [
        ("run_shell_command", "Shell execution detected", "I can run shell commands (requires SYSTEM permission)"),
    ],
}


class ToolSuggestionService:
    """Service for suggesting relevant tools based on user context."""

    def __init__(self, capabilities: dict = None):
        """Initialize with discovered capabilities.

        Args:
            capabilities: Dict of capability_name -> Capability object
                         If None, will be loaded on first use
        """
        self._capabilities = capabilities
        self._available_tools: set = set()
        self._refresh_available_tools()

    def _refresh_available_tools(self):
        """Refresh the set of available tool names."""
        if self._capabilities:
            self._available_tools = {
                name for name, cap in self._capabilities.items()
                if cap.available
            }
        else:
            self._available_tools = set()

    def update_capabilities(self, capabilities: dict):
        """Update the capabilities dictionary.

        Args:
            capabilities: New capabilities dictionary
        """
        self._capabilities = capabilities
        self._refresh_available_tools()

    def analyze_message(self, message: str) -> list[ToolSuggestion]:
        """Analyze a user message and suggest relevant tools.

        Args:
            message: The user's message text

        Returns:
            List of ToolSuggestion objects for relevant available tools
        """
        suggestions = []
        seen_tools = set()  # Avoid duplicate suggestions
        message_lower = message.lower()

        for pattern, tool_infos in TASK_TOOL_MAPPINGS.items():
            if re.search(pattern, message_lower, re.IGNORECASE):
                for tool_name, reason, hint in tool_infos:
                    # Only suggest if tool is available and not already suggested
                    if tool_name in self._available_tools and tool_name not in seen_tools:
                        seen_tools.add(tool_name)

                        # Get description from capability if available
                        description = ""
                        if self._capabilities and tool_name in self._capabilities:
                            description = self._capabilities[tool_name].description or ""

                        suggestions.append(ToolSuggestion(
                            name=tool_name,
                            type="cli_tool",
                            description=description,
                            relevance_reason=reason,
                            usage_hint=hint,
                        ))

        logger.debug(f"Found {len(suggestions)} tool suggestions for message")
        return suggestions

    def get_system_prompt_injection(self, suggestions: list[ToolSuggestion]) -> str:
        """Generate system prompt text with tool suggestions.

        Args:
            suggestions: List of ToolSuggestion objects

        Returns:
            Text to inject into system prompt about available tools
        """
        if not suggestions:
            return ""

        lines = [
            "\n[AVAILABLE TOOLS]",
            "The following tools are available on this system and relevant to the user's request:",
        ]

        for s in suggestions:
            lines.append(f"- **{s.name}**: {s.usage_hint}")

        lines.append(
            "\nProactively suggest using these tools when appropriate. "
            "If a task would benefit from a tool, mention it to the user."
        )

        return "\n".join(lines)

    def get_available_tools_summary(self) -> str:
        """Get a summary of all available tools for the system prompt.

        Returns:
            Text summarizing all available tools
        """
        if not self._capabilities:
            return ""

        available = [
            (name, cap.description or "")
            for name, cap in self._capabilities.items()
            if cap.available and cap.type.value == "cli_tool"
        ]

        if not available:
            return ""

        lines = [
            "\n[SYSTEM CAPABILITIES]",
            "The following CLI tools are available on this system:",
        ]

        # Group by first letter for readability
        available.sort(key=lambda x: x[0])
        tool_names = [name for name, _ in available]
        lines.append(", ".join(tool_names))

        lines.append(
            "\nYou can suggest using any of these tools to help the user with their tasks. "
            "Be proactive about offering tool-based solutions."
        )

        return "\n".join(lines)


# Singleton instance (lazy-loaded with capabilities)
_suggestion_service: Optional[ToolSuggestionService] = None


def get_suggestion_service(capabilities: dict = None) -> ToolSuggestionService:
    """Get or create the singleton suggestion service.

    Args:
        capabilities: Capabilities dict to initialize with (optional)

    Returns:
        ToolSuggestionService instance
    """
    global _suggestion_service
    if _suggestion_service is None:
        _suggestion_service = ToolSuggestionService(capabilities)
    elif capabilities:
        _suggestion_service.update_capabilities(capabilities)
    return _suggestion_service
