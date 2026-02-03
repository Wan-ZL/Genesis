"""Tests for the tool suggestion service."""
import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass
from enum import Enum


# Mock CapabilityType for testing
class MockCapabilityType(str, Enum):
    CLI_TOOL = "cli_tool"
    SERVICE = "service"
    SYSTEM = "system"


@dataclass
class MockCapability:
    """Mock capability for testing."""
    name: str
    type: MockCapabilityType
    available: bool
    description: str = ""


class TestToolSuggestionService:
    """Tests for ToolSuggestionService."""

    @pytest.fixture
    def mock_capabilities(self):
        """Create mock capabilities for testing."""
        return {
            "git": MockCapability("git", MockCapabilityType.CLI_TOOL, True, "Version control"),
            "docker": MockCapability("docker", MockCapabilityType.CLI_TOOL, True, "Container runtime"),
            "python3": MockCapability("python3", MockCapabilityType.CLI_TOOL, True, "Python interpreter"),
            "node": MockCapability("node", MockCapabilityType.CLI_TOOL, True, "Node.js runtime"),
            "npm": MockCapability("npm", MockCapabilityType.CLI_TOOL, True, "Node package manager"),
            "curl": MockCapability("curl", MockCapabilityType.CLI_TOOL, True, "HTTP client"),
            "jq": MockCapability("jq", MockCapabilityType.CLI_TOOL, True, "JSON processor"),
            "sqlite3": MockCapability("sqlite3", MockCapabilityType.CLI_TOOL, True, "SQLite database"),
            "aws": MockCapability("aws", MockCapabilityType.CLI_TOOL, False, "AWS CLI (not installed)"),
            "gh": MockCapability("gh", MockCapabilityType.CLI_TOOL, True, "GitHub CLI"),
            "brew": MockCapability("brew", MockCapabilityType.CLI_TOOL, True, "Homebrew"),
            "ffmpeg": MockCapability("ffmpeg", MockCapabilityType.CLI_TOOL, True, "Media processor"),
            "kubectl": MockCapability("kubectl", MockCapabilityType.CLI_TOOL, False, "Kubernetes CLI (not installed)"),
            "run_shell_command": MockCapability("run_shell_command", MockCapabilityType.CLI_TOOL, True, "Shell execution"),
        }

    @pytest.fixture
    def service(self, mock_capabilities):
        """Create service with mock capabilities."""
        from server.services.tool_suggestions import ToolSuggestionService
        return ToolSuggestionService(mock_capabilities)

    def test_init_with_capabilities(self, service, mock_capabilities):
        """Test initialization with capabilities."""
        assert service._capabilities == mock_capabilities
        assert "git" in service._available_tools
        assert "docker" in service._available_tools
        assert "aws" not in service._available_tools  # Not available

    def test_init_without_capabilities(self):
        """Test initialization without capabilities."""
        from server.services.tool_suggestions import ToolSuggestionService
        service = ToolSuggestionService()
        assert service._capabilities is None
        assert len(service._available_tools) == 0

    def test_analyze_message_git_keywords(self, service):
        """Test analyzing message with git keywords."""
        suggestions = service.analyze_message("I need to commit my changes")
        tool_names = [s.name for s in suggestions]
        assert "git" in tool_names

    def test_analyze_message_docker_keywords(self, service):
        """Test analyzing message with docker keywords."""
        suggestions = service.analyze_message("I want to build a Docker container")
        tool_names = [s.name for s in suggestions]
        assert "docker" in tool_names

    def test_analyze_message_python_keywords(self, service):
        """Test analyzing message with Python keywords."""
        suggestions = service.analyze_message("Run this Python script")
        tool_names = [s.name for s in suggestions]
        assert "python3" in tool_names

    def test_analyze_message_node_keywords(self, service):
        """Test analyzing message with Node.js keywords."""
        suggestions = service.analyze_message("I need to install npm packages")
        tool_names = [s.name for s in suggestions]
        assert "node" in tool_names
        assert "npm" in tool_names

    def test_analyze_message_database_keywords(self, service):
        """Test analyzing message with database keywords."""
        suggestions = service.analyze_message("Query the sqlite database")
        tool_names = [s.name for s in suggestions]
        assert "sqlite3" in tool_names

    def test_analyze_message_http_keywords(self, service):
        """Test analyzing message with HTTP keywords."""
        suggestions = service.analyze_message("Make an API request to the endpoint")
        tool_names = [s.name for s in suggestions]
        assert "curl" in tool_names

    def test_analyze_message_json_keywords(self, service):
        """Test analyzing message with JSON keywords."""
        suggestions = service.analyze_message("Parse this JSON data")
        tool_names = [s.name for s in suggestions]
        assert "jq" in tool_names

    def test_analyze_message_github_keywords(self, service):
        """Test analyzing message with GitHub keywords."""
        suggestions = service.analyze_message("Check the GitHub repo status")
        tool_names = [s.name for s in suggestions]
        assert "gh" in tool_names

    def test_analyze_message_shell_keywords(self, service):
        """Test analyzing message with shell keywords."""
        suggestions = service.analyze_message("Execute a shell command")
        tool_names = [s.name for s in suggestions]
        assert "run_shell_command" in tool_names

    def test_analyze_message_media_keywords(self, service):
        """Test analyzing message with media keywords."""
        suggestions = service.analyze_message("Convert this video to mp4")
        tool_names = [s.name for s in suggestions]
        assert "ffmpeg" in tool_names

    def test_analyze_message_package_keywords(self, service):
        """Test analyzing message with package keywords."""
        suggestions = service.analyze_message("Install this package with homebrew")
        tool_names = [s.name for s in suggestions]
        assert "brew" in tool_names

    def test_analyze_message_no_matches(self, service):
        """Test analyzing message with no matching keywords."""
        suggestions = service.analyze_message("Hello, how are you?")
        assert len(suggestions) == 0

    def test_analyze_message_unavailable_tool(self, service):
        """Test that unavailable tools are not suggested."""
        # AWS is in capabilities but not available
        suggestions = service.analyze_message("Use AWS S3 to store files")
        tool_names = [s.name for s in suggestions]
        assert "aws" not in tool_names

    def test_analyze_message_multiple_keywords(self, service):
        """Test analyzing message with multiple matching keywords."""
        suggestions = service.analyze_message("Build a Docker container and push to git repo")
        tool_names = [s.name for s in suggestions]
        assert "docker" in tool_names
        assert "git" in tool_names

    def test_analyze_message_no_duplicates(self, service):
        """Test that suggestions don't have duplicates."""
        suggestions = service.analyze_message("Use git to commit and then git push")
        tool_names = [s.name for s in suggestions]
        assert tool_names.count("git") == 1

    def test_analyze_message_case_insensitive(self, service):
        """Test that keyword matching is case insensitive."""
        suggestions_lower = service.analyze_message("use docker")
        suggestions_upper = service.analyze_message("USE DOCKER")
        suggestions_mixed = service.analyze_message("Use Docker")

        assert len(suggestions_lower) > 0
        assert len(suggestions_upper) > 0
        assert len(suggestions_mixed) > 0

    def test_get_system_prompt_injection_with_suggestions(self, service):
        """Test generating system prompt with suggestions."""
        suggestions = service.analyze_message("Build a Docker container")
        prompt = service.get_system_prompt_injection(suggestions)

        assert "[AVAILABLE TOOLS]" in prompt
        assert "docker" in prompt.lower()

    def test_get_system_prompt_injection_empty(self, service):
        """Test generating system prompt with no suggestions."""
        prompt = service.get_system_prompt_injection([])
        assert prompt == ""

    def test_get_available_tools_summary(self, service):
        """Test getting summary of all available tools."""
        summary = service.get_available_tools_summary()

        assert "[SYSTEM CAPABILITIES]" in summary
        assert "git" in summary
        assert "docker" in summary
        assert "aws" not in summary  # Not available

    def test_update_capabilities(self, service):
        """Test updating capabilities."""
        new_capabilities = {
            "terraform": MockCapability("terraform", MockCapabilityType.CLI_TOOL, True, "Infrastructure as code"),
        }
        service.update_capabilities(new_capabilities)

        assert "terraform" in service._available_tools
        assert "git" not in service._available_tools  # Old ones replaced

    def test_suggestion_has_all_fields(self, service):
        """Test that suggestions have all required fields."""
        suggestions = service.analyze_message("I need to commit changes with git")

        assert len(suggestions) > 0
        s = suggestions[0]
        assert s.name is not None
        assert s.type is not None
        assert s.relevance_reason is not None
        assert s.usage_hint is not None


class TestToolSuggestionSingleton:
    """Tests for the singleton pattern."""

    def test_get_suggestion_service_singleton(self):
        """Test that get_suggestion_service returns same instance."""
        from server.services import tool_suggestions
        # Reset singleton
        tool_suggestions._suggestion_service = None

        service1 = tool_suggestions.get_suggestion_service()
        service2 = tool_suggestions.get_suggestion_service()

        assert service1 is service2

    def test_get_suggestion_service_with_capabilities(self):
        """Test initializing singleton with capabilities."""
        from server.services import tool_suggestions
        # Reset singleton
        tool_suggestions._suggestion_service = None

        caps = {
            "git": MockCapability("git", MockCapabilityType.CLI_TOOL, True, "Version control"),
        }

        service = tool_suggestions.get_suggestion_service(caps)
        assert "git" in service._available_tools


class TestChatAPIIntegration:
    """Tests for chat API integration with tool suggestions."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from fastapi.testclient import TestClient
        from server.main import app
        return TestClient(app)

    @pytest.fixture
    def mock_openai_response(self):
        """Mock OpenAI response."""
        mock = MagicMock()
        mock.choices = [MagicMock()]
        mock.choices[0].message.content = "Here's how to use git for version control..."
        mock.choices[0].message.tool_calls = None
        return mock

    def test_chat_response_includes_suggested_tools(self, client, mock_openai_response):
        """Test that chat response includes suggested tools."""
        with patch("server.routes.chat.get_openai_client") as mock_client:
            mock_instance = MagicMock()
            mock_instance.chat.completions.create.return_value = mock_openai_response
            mock_client.return_value = mock_instance

            # Also mock the suggestion service to ensure it has tools
            from server.services import tool_suggestions
            tool_suggestions._suggestion_service = None
            caps = {
                "git": MockCapability("git", MockCapabilityType.CLI_TOOL, True, "Version control"),
                "gh": MockCapability("gh", MockCapabilityType.CLI_TOOL, True, "GitHub CLI"),
            }
            tool_suggestions.get_suggestion_service(caps)

            response = client.post(
                "/api/chat",
                json={"message": "How do I commit with git?"}
            )

            assert response.status_code == 200
            data = response.json()

            # Should have suggested_tools field (may be null if no tools matched)
            assert "suggested_tools" in data

    def test_suggested_tool_format(self, client, mock_openai_response):
        """Test format of suggested tools in response."""
        with patch("server.routes.chat.get_openai_client") as mock_client:
            mock_instance = MagicMock()
            mock_instance.chat.completions.create.return_value = mock_openai_response
            mock_client.return_value = mock_instance

            # Setup suggestion service with tools
            from server.services import tool_suggestions
            tool_suggestions._suggestion_service = None
            caps = {
                "git": MockCapability("git", MockCapabilityType.CLI_TOOL, True, "Version control"),
            }
            tool_suggestions.get_suggestion_service(caps)

            response = client.post(
                "/api/chat",
                json={"message": "Commit my changes with git"}
            )

            assert response.status_code == 200
            data = response.json()

            if data.get("suggested_tools"):
                tool = data["suggested_tools"][0]
                assert "name" in tool
                assert "description" in tool
                assert "relevance_reason" in tool
                assert "usage_hint" in tool


class TestToolMappings:
    """Tests for the keyword-to-tool mappings."""

    @pytest.fixture
    def all_tools_available(self):
        """Create capabilities with all tools available."""
        tools = [
            "git", "gh", "docker", "docker-compose", "kubectl",
            "python3", "node", "npm", "sqlite3", "psql", "mysql",
            "redis-cli", "aws", "gcloud", "az", "terraform",
            "ffmpeg", "curl", "jq", "wget", "code", "brew",
            "run_shell_command"
        ]
        return {
            name: MockCapability(name, MockCapabilityType.CLI_TOOL, True, f"{name} tool")
            for name in tools
        }

    def test_version_control_mappings(self, all_tools_available):
        """Test version control keyword mappings."""
        from server.services.tool_suggestions import ToolSuggestionService
        service = ToolSuggestionService(all_tools_available)

        keywords = ["commit", "push", "pull", "branch", "merge", "git", "version control", "repo"]
        for keyword in keywords:
            suggestions = service.analyze_message(f"I want to {keyword}")
            tool_names = [s.name for s in suggestions]
            assert "git" in tool_names or "gh" in tool_names, f"Failed for keyword: {keyword}"

    def test_container_mappings(self, all_tools_available):
        """Test container keyword mappings."""
        from server.services.tool_suggestions import ToolSuggestionService
        service = ToolSuggestionService(all_tools_available)

        keywords = ["docker", "container", "deploy", "image", "dockerfile", "kubernetes", "k8s"]
        for keyword in keywords:
            suggestions = service.analyze_message(f"Help with {keyword}")
            tool_names = [s.name for s in suggestions]
            assert any(t in tool_names for t in ["docker", "docker-compose", "kubectl"]), f"Failed for keyword: {keyword}"

    def test_cloud_mappings(self, all_tools_available):
        """Test cloud provider keyword mappings."""
        from server.services.tool_suggestions import ToolSuggestionService
        service = ToolSuggestionService(all_tools_available)

        assert len(service.analyze_message("Upload to AWS S3")) > 0
        assert len(service.analyze_message("Use Google Cloud BigQuery")) > 0
        assert len(service.analyze_message("Deploy to Azure")) > 0
