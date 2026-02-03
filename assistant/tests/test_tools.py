"""Tests for the Tool Registry System."""

import pytest
from datetime import datetime
from server.services.tools import (
    ToolRegistry,
    ToolSpec,
    ToolParameter,
    registry,
    get_current_datetime,
    calculate,
)


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
