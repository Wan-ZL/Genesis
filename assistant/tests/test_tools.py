"""Tests for the Tool Registry System."""

import os
import pytest
from datetime import datetime
from server.services.tools import (
    ToolRegistry,
    ToolSpec,
    ToolParameter,
    PermissionLevel,
    registry,
    get_current_datetime,
    calculate,
    web_fetch,
    run_shell_command,
)
from unittest.mock import patch, MagicMock


class TestToolRegistry:
    """Tests for ToolRegistry class."""

    def test_register_decorator(self):
        """Test registering a tool via decorator."""
        reg = ToolRegistry()

        @reg.register
        def test_tool(param1: str) -> str:
            """A test tool."""
            return f"Got: {param1}"

        assert "test_tool" in reg.list_tools()
        spec = reg.get_tool("test_tool")
        assert spec is not None
        assert spec.name == "test_tool"
        assert spec.description == "A test tool."

    def test_register_tool_explicit(self):
        """Test registering a tool with explicit spec."""
        reg = ToolRegistry()

        def my_handler(x: int) -> int:
            return x * 2

        spec = ToolSpec(
            name="doubler",
            description="Doubles a number",
            parameters=[ToolParameter("x", "integer", "Number to double")],
            handler=my_handler,
        )
        reg.register_tool(spec)

        assert "doubler" in reg.list_tools()
        assert reg.get_tool("doubler").description == "Doubles a number"

    def test_register_tool_without_handler_fails(self):
        """Test that registering without handler raises error."""
        reg = ToolRegistry()
        spec = ToolSpec(name="bad", description="No handler")

        with pytest.raises(ValueError, match="must have a handler"):
            reg.register_tool(spec)

    def test_execute_success(self):
        """Test successful tool execution."""
        reg = ToolRegistry()

        @reg.register
        def add(a: int, b: int) -> int:
            """Add two numbers."""
            return a + b

        result = reg.execute("add", a=5, b=3)
        assert result["success"] is True
        assert result["result"] == 8

    def test_execute_not_found(self):
        """Test executing non-existent tool."""
        reg = ToolRegistry()
        result = reg.execute("nonexistent", foo="bar")

        assert result["success"] is False
        assert "not found" in result["error"]

    def test_execute_with_error(self):
        """Test tool that raises an exception."""
        reg = ToolRegistry()

        @reg.register
        def failing_tool() -> None:
            """A tool that fails."""
            raise RuntimeError("Something broke")

        result = reg.execute("failing_tool")
        assert result["success"] is False
        assert "Something broke" in result["error"]

    def test_list_tools(self):
        """Test listing all tools."""
        reg = ToolRegistry()

        @reg.register
        def tool_a():
            """Tool A."""
            pass

        @reg.register
        def tool_b():
            """Tool B."""
            pass

        tools = reg.list_tools()
        assert "tool_a" in tools
        assert "tool_b" in tools
        assert len(tools) == 2

    def test_get_all_specs(self):
        """Test getting all tool specifications."""
        reg = ToolRegistry()

        @reg.register
        def my_tool(x: str) -> str:
            """My tool."""
            return x

        specs = reg.get_all_specs()
        assert len(specs) == 1
        assert specs[0].name == "my_tool"


class TestOpenAIFormat:
    """Tests for OpenAI tool format conversion."""

    def test_to_openai_tools_format(self):
        """Test conversion to OpenAI function format."""
        reg = ToolRegistry()

        @reg.register
        def search(query: str, limit: int = 10) -> str:
            """Search for something."""
            return f"Found: {query}"

        tools = reg.to_openai_tools()
        assert len(tools) == 1

        tool = tools[0]
        assert tool["type"] == "function"
        assert tool["function"]["name"] == "search"
        assert tool["function"]["description"] == "Search for something."
        assert "query" in tool["function"]["parameters"]["properties"]
        assert "query" in tool["function"]["parameters"]["required"]


class TestClaudeFormat:
    """Tests for Claude tool format conversion."""

    def test_to_claude_tools_format(self):
        """Test conversion to Claude tool format."""
        reg = ToolRegistry()

        @reg.register
        def analyze(text: str) -> str:
            """Analyze text content."""
            return f"Analysis of: {text}"

        tools = reg.to_claude_tools()
        assert len(tools) == 1

        tool = tools[0]
        assert tool["name"] == "analyze"
        assert tool["description"] == "Analyze text content."
        assert "input_schema" in tool
        assert tool["input_schema"]["type"] == "object"
        assert "text" in tool["input_schema"]["properties"]


class TestBuiltinTools:
    """Tests for built-in tools."""

    def test_get_current_datetime_default(self):
        """Test datetime tool with default format."""
        result = get_current_datetime()
        # Should be in format YYYY-MM-DD HH:MM:SS
        assert len(result) == 19
        # Verify it's a valid datetime
        datetime.strptime(result, "%Y-%m-%d %H:%M:%S")

    def test_get_current_datetime_custom_format(self):
        """Test datetime tool with custom format."""
        result = get_current_datetime("%Y-%m-%d")
        assert len(result) == 10
        datetime.strptime(result, "%Y-%m-%d")

    def test_calculate_basic(self):
        """Test calculate tool with basic expressions."""
        assert calculate("2 + 3") == "5"
        assert calculate("10 - 4") == "6"
        assert calculate("3 * 4") == "12"
        assert calculate("15 / 3") == "5.0"

    def test_calculate_complex(self):
        """Test calculate tool with complex expressions."""
        assert calculate("2 + 3 * 4") == "14"
        assert calculate("(2 + 3) * 4") == "20"
        assert calculate("2 ** 3") == "8"

    def test_calculate_negative(self):
        """Test calculate tool with negative numbers."""
        assert calculate("-5 + 3") == "-2"
        assert calculate("5 * -2") == "-10"

    def test_calculate_invalid(self):
        """Test calculate tool with invalid expression."""
        result = calculate("invalid")
        assert "Error" in result


class TestGlobalRegistry:
    """Tests for the global registry instance."""

    def test_global_registry_has_builtin_tools(self):
        """Test that global registry has built-in tools."""
        tools = registry.list_tools()
        assert "get_current_datetime" in tools
        assert "calculate" in tools

    def test_global_registry_execute_datetime(self):
        """Test executing datetime via global registry."""
        result = registry.execute("get_current_datetime")
        assert result["success"] is True
        assert len(result["result"]) == 19

    def test_global_registry_execute_calculate(self):
        """Test executing calculate via global registry."""
        result = registry.execute("calculate", expression="2 + 2")
        assert result["success"] is True
        assert result["result"] == "4"

    def test_global_registry_has_web_fetch(self):
        """Test that global registry has web_fetch tool."""
        tools = registry.list_tools()
        assert "web_fetch" in tools


class TestWebFetchTool:
    """Tests for the web_fetch tool."""

    def test_web_fetch_invalid_scheme(self):
        """Test web_fetch rejects invalid URL schemes."""
        result = web_fetch("ftp://example.com")
        assert "Error" in result
        assert "Invalid URL scheme" in result

    def test_web_fetch_invalid_url(self):
        """Test web_fetch rejects invalid URLs."""
        result = web_fetch("not-a-url")
        assert "Error" in result

    def test_web_fetch_success(self):
        """Test web_fetch with mocked successful response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html>Hello World</html>"
        mock_response.reason_phrase = "OK"
        mock_response.headers = {"content-type": "text/html"}

        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_response
            result = web_fetch("https://example.com")

        assert "URL: https://example.com" in result
        assert "Status: 200" in result
        assert "Hello World" in result

    def test_web_fetch_truncation(self):
        """Test web_fetch truncates long content."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "A" * 10000
        mock_response.reason_phrase = "OK"
        mock_response.headers = {"content-type": "text/html"}

        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_response
            result = web_fetch("https://example.com", max_length=100)

        assert "[Content truncated at 100 characters" in result

    def test_web_fetch_http_error(self):
        """Test web_fetch handles HTTP errors."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.reason_phrase = "Not Found"
        mock_response.headers = {}

        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_response
            result = web_fetch("https://example.com/notfound")

        assert "Error" in result
        assert "404" in result

    def test_web_fetch_timeout(self):
        """Test web_fetch handles timeouts (with no cached fallback)."""
        import httpx

        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.side_effect = httpx.TimeoutException("timeout")
            # Use unique URL and disable cache to test pure timeout behavior
            result = web_fetch("https://example.com/unique-timeout-test-no-cache", use_cache=False)

        assert "Error" in result
        assert "timed out" in result

    def test_web_fetch_via_registry(self):
        """Test executing web_fetch via global registry."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "Test content"
        mock_response.reason_phrase = "OK"
        mock_response.headers = {"content-type": "text/plain"}

        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_response
            result = registry.execute("web_fetch", url="https://example.com")

        assert result["success"] is True
        assert "Test content" in result["result"]


class TestPermissionEscalation:
    """Tests for permission-aware tool execution."""

    def test_tool_spec_has_required_permission(self):
        """Test that ToolSpec supports required_permission field."""
        spec = ToolSpec(
            name="test",
            description="Test tool",
            handler=lambda: "test",
            required_permission=PermissionLevel.SYSTEM,
        )
        assert spec.required_permission == PermissionLevel.SYSTEM

    def test_tool_spec_default_permission_is_sandbox(self):
        """Test that default permission level is SANDBOX."""
        spec = ToolSpec(
            name="test",
            description="Test tool",
            handler=lambda: "test",
        )
        assert spec.required_permission == PermissionLevel.SANDBOX

    def test_execute_returns_escalation_when_permission_insufficient(self):
        """Test that execute returns escalation request when permission is insufficient."""
        reg = ToolRegistry()
        reg.register_tool(ToolSpec(
            name="admin_tool",
            description="Admin operation",
            handler=lambda: "done",
            required_permission=PermissionLevel.SYSTEM,
        ))

        # Set permission to LOCAL (below SYSTEM)
        with patch.dict(os.environ, {"ASSISTANT_PERMISSION_LEVEL": "1"}):
            result = reg.execute("admin_tool")

        assert result["success"] is False
        assert "permission_escalation" in result
        escalation = result["permission_escalation"]
        assert escalation["tool_name"] == "admin_tool"
        assert escalation["current_level"] == 1
        assert escalation["current_level_name"] == "LOCAL"
        assert escalation["required_level"] == 2
        assert escalation["required_level_name"] == "SYSTEM"

    def test_execute_succeeds_with_sufficient_permission(self):
        """Test that execute succeeds when permission is sufficient."""
        reg = ToolRegistry()
        reg.register_tool(ToolSpec(
            name="admin_tool",
            description="Admin operation",
            handler=lambda: "done",
            required_permission=PermissionLevel.SYSTEM,
        ))

        # Set permission to SYSTEM (equal to required)
        with patch.dict(os.environ, {"ASSISTANT_PERMISSION_LEVEL": "2"}):
            result = reg.execute("admin_tool")

        assert result["success"] is True
        assert result["result"] == "done"

    def test_execute_succeeds_with_higher_permission(self):
        """Test that execute succeeds when permission exceeds requirement."""
        reg = ToolRegistry()
        reg.register_tool(ToolSpec(
            name="local_tool",
            description="Local operation",
            handler=lambda: "done",
            required_permission=PermissionLevel.LOCAL,
        ))

        # Set permission to FULL (above LOCAL)
        with patch.dict(os.environ, {"ASSISTANT_PERMISSION_LEVEL": "3"}):
            result = reg.execute("local_tool")

        assert result["success"] is True
        assert result["result"] == "done"

    def test_escalation_includes_pending_args(self):
        """Test that escalation request includes the pending arguments."""
        reg = ToolRegistry()
        reg.register_tool(ToolSpec(
            name="parameterized_tool",
            description="Tool with params",
            parameters=[
                ToolParameter("cmd", "string", "Command to run"),
            ],
            handler=lambda cmd: f"ran {cmd}",
            required_permission=PermissionLevel.SYSTEM,
        ))

        with patch.dict(os.environ, {"ASSISTANT_PERMISSION_LEVEL": "0"}):
            result = reg.execute("parameterized_tool", cmd="ls -la")

        assert "permission_escalation" in result
        assert result["permission_escalation"]["pending_args"] == {"cmd": "ls -la"}


class TestRunShellCommand:
    """Tests for the run_shell_command tool."""

    def test_global_registry_has_run_shell_command(self):
        """Test that global registry has run_shell_command tool."""
        assert "run_shell_command" in registry.list_tools()

    def test_run_shell_command_tool_requires_system_permission(self):
        """Test that run_shell_command requires SYSTEM permission."""
        tool = registry.get_tool("run_shell_command")
        assert tool.required_permission == PermissionLevel.SYSTEM

    def test_run_shell_command_returns_escalation_at_local_permission(self):
        """Test that run_shell_command returns escalation at LOCAL permission."""
        with patch.dict(os.environ, {"ASSISTANT_PERMISSION_LEVEL": "1"}):
            result = registry.execute("run_shell_command", command="echo hello")

        assert result["success"] is False
        assert "permission_escalation" in result
        assert result["permission_escalation"]["required_level_name"] == "SYSTEM"

    def test_run_shell_command_executes_at_system_permission(self):
        """Test that run_shell_command works at SYSTEM permission."""
        with patch.dict(os.environ, {"ASSISTANT_PERMISSION_LEVEL": "2"}):
            result = registry.execute("run_shell_command", command="echo hello")

        assert result["success"] is True
        assert "hello" in result["result"]

    def test_run_shell_command_direct_call(self):
        """Test direct call to run_shell_command function."""
        result = run_shell_command("echo test123")
        assert "test123" in result
        assert "Exit code: 0" in result

    def test_run_shell_command_captures_stderr(self):
        """Test that stderr is captured."""
        result = run_shell_command("ls /nonexistent/path/xyz")
        assert "STDERR" in result or "Exit code:" in result

    def test_run_shell_command_blocks_dangerous_commands(self):
        """Test that dangerous commands are blocked."""
        result = run_shell_command("rm -rf /")
        assert "Error" in result
        assert "blocked for safety" in result

    def test_run_shell_command_timeout(self):
        """Test command timeout."""
        result = run_shell_command("sleep 10", timeout=1)
        assert "Error" in result
        assert "timed out" in result


class TestWebFetchCaching:
    """Tests for web_fetch caching functionality."""

    def test_web_fetch_caches_successful_result(self):
        """Test that successful web_fetch results are cached."""
        from server.services.degradation import get_degradation_service

        # Clear any existing cache
        degradation = get_degradation_service()
        degradation.clear_cache()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "Cached content here"
        mock_response.reason_phrase = "OK"
        mock_response.headers = {"content-type": "text/html"}

        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_response
            result = web_fetch("https://example.com/cacheable", use_cache=True)

        assert "Cached content here" in result
        # Verify content is cached
        assert degradation._tool_cache  # Should have at least one entry

    def test_web_fetch_returns_cached_when_offline(self):
        """Test that web_fetch returns cached content when in OFFLINE mode."""
        from server.services.degradation import get_degradation_service, DegradationMode

        degradation = get_degradation_service()
        degradation.clear_cache()

        # First, cache some content
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "Original cached content"
        mock_response.reason_phrase = "OK"
        mock_response.headers = {"content-type": "text/html"}

        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_response
            web_fetch("https://example.com/offline-test", use_cache=True)

        # Now simulate offline mode
        degradation._network_available = False
        degradation._update_mode()
        assert degradation.mode == DegradationMode.OFFLINE

        # Fetch should return cached content
        result = web_fetch("https://example.com/offline-test", use_cache=True)
        assert "[CACHED" in result
        assert "Original cached content" in result

        # Cleanup
        degradation._network_available = True
        degradation._update_mode()

    def test_web_fetch_returns_cached_on_http_error(self):
        """Test that web_fetch returns cached content on HTTP errors."""
        from server.services.degradation import get_degradation_service

        degradation = get_degradation_service()
        degradation.clear_cache()

        # First, cache some content
        mock_response_ok = MagicMock()
        mock_response_ok.status_code = 200
        mock_response_ok.text = "Good content before error"
        mock_response_ok.reason_phrase = "OK"
        mock_response_ok.headers = {"content-type": "text/html"}

        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_response_ok
            web_fetch("https://example.com/error-fallback", use_cache=True)

        # Now simulate HTTP error
        mock_response_error = MagicMock()
        mock_response_error.status_code = 500
        mock_response_error.reason_phrase = "Internal Server Error"
        mock_response_error.headers = {}

        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_response_error
            result = web_fetch("https://example.com/error-fallback", use_cache=True)

        assert "[CACHED FALLBACK" in result
        assert "Good content before error" in result

    def test_web_fetch_returns_cached_on_timeout(self):
        """Test that web_fetch returns cached content on timeout."""
        import httpx
        from server.services.degradation import get_degradation_service

        degradation = get_degradation_service()
        degradation.clear_cache()

        # First, cache some content
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "Content before timeout"
        mock_response.reason_phrase = "OK"
        mock_response.headers = {"content-type": "text/html"}

        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_response
            web_fetch("https://example.com/timeout-test", use_cache=True)

        # Now simulate timeout
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.side_effect = httpx.TimeoutException("timeout")
            result = web_fetch("https://example.com/timeout-test", use_cache=True)

        assert "[CACHED FALLBACK - Timeout]" in result
        assert "Content before timeout" in result

    def test_web_fetch_returns_cached_on_network_error(self):
        """Test that web_fetch returns cached content on network errors."""
        import httpx
        from server.services.degradation import get_degradation_service

        degradation = get_degradation_service()
        degradation.clear_cache()

        # First, cache some content
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "Content before network error"
        mock_response.reason_phrase = "OK"
        mock_response.headers = {"content-type": "text/html"}

        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_response
            web_fetch("https://example.com/network-error", use_cache=True)

        # Now simulate network error
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.side_effect = httpx.RequestError("Connection refused")
            result = web_fetch("https://example.com/network-error", use_cache=True)

        assert "[CACHED FALLBACK - Network Error]" in result
        assert "Content before network error" in result

    def test_web_fetch_with_cache_disabled(self):
        """Test that web_fetch doesn't cache when use_cache=False."""
        from server.services.degradation import get_degradation_service

        degradation = get_degradation_service()
        initial_cache_count = len(degradation._tool_cache)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "No cache content"
        mock_response.reason_phrase = "OK"
        mock_response.headers = {"content-type": "text/html"}

        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_response
            result = web_fetch("https://example.com/nocache", use_cache=False)

        assert "No cache content" in result
        # Cache should not have grown
        assert len(degradation._tool_cache) == initial_cache_count

    def test_web_fetch_cache_key_includes_max_length(self):
        """Test that different max_length values use different cache keys."""
        from server.services.degradation import get_degradation_service
        from server.services.tools import _compute_cache_key

        # Verify cache keys differ for same URL with different max_length
        key1 = _compute_cache_key("https://example.com/test", 4000)
        key2 = _compute_cache_key("https://example.com/test", 8000)
        assert key1 != key2

    def test_web_fetch_no_cached_returns_error_on_failure(self):
        """Test that web_fetch returns error when no cached content exists."""
        import httpx
        from server.services.degradation import get_degradation_service

        degradation = get_degradation_service()
        degradation.clear_cache()

        # Simulate network error without prior cache
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.side_effect = httpx.RequestError("Connection refused")
            result = web_fetch("https://example.com/never-cached", use_cache=True)

        assert "Error" in result
        assert "Failed to fetch URL" in result
        assert "[CACHED" not in result
