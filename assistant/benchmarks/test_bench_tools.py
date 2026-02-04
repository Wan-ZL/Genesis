"""
Benchmarks for Tool Registry System

Critical paths tested:
- Tool lookup by name
- Tool execution time (built-in tools)
- Tool format conversion (to OpenAI/Claude format)
"""

import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from server.services.tools import (
    ToolRegistry,
    ToolSpec,
    ToolParameter,
    registry as tool_registry,
)


@pytest.fixture
def registry():
    """Create a fresh tool registry."""
    return ToolRegistry()


@pytest.fixture
def populated_registry():
    """Create a registry with many tools."""
    reg = ToolRegistry()

    # Register 20 dummy tools to simulate a realistic registry
    for i in range(20):
        spec = ToolSpec(
            name=f"dummy_tool_{i}",
            description=f"Dummy tool number {i} for benchmarking",
            parameters=[
                ToolParameter(
                    name="param1",
                    type="string",
                    description="First parameter"
                ),
                ToolParameter(
                    name="param2",
                    type="integer",
                    description="Second parameter",
                    required=False,
                    default=0
                )
            ],
            handler=lambda x, y=0: f"Result: {x}, {y}"
        )
        reg.register_tool(spec)

    return reg


class TestToolRegistryBenchmarks:
    """Benchmarks for ToolRegistry operations."""

    def test_bench_tool_registration(self, benchmark, registry):
        """Benchmark registering a new tool."""

        i = [0]

        def register_tool():
            spec = ToolSpec(
                name=f"bench_tool_{i[0]}",
                description="Benchmark tool",
                parameters=[
                    ToolParameter("input", "string", "Input value")
                ],
                handler=lambda x: x
            )
            registry.register_tool(spec)
            i[0] += 1

        benchmark(register_tool)

    def test_bench_tool_lookup(self, benchmark, populated_registry):
        """Benchmark looking up a tool by name."""

        def lookup():
            return populated_registry.get_tool("dummy_tool_10")

        benchmark(lookup)

    def test_bench_tool_lookup_miss(self, benchmark, populated_registry):
        """Benchmark looking up a non-existent tool."""

        def lookup():
            return populated_registry.get_tool("nonexistent_tool")

        benchmark(lookup)

    def test_bench_list_all_tools(self, benchmark, populated_registry):
        """Benchmark listing all registered tools."""

        def list_tools():
            return populated_registry.list_tools()

        benchmark(list_tools)

    def test_bench_to_openai_format(self, benchmark, populated_registry):
        """Benchmark converting all tools to OpenAI format."""

        def convert():
            return populated_registry.to_openai_tools()

        benchmark(convert)

    def test_bench_to_claude_format(self, benchmark, populated_registry):
        """Benchmark converting all tools to Claude format."""

        def convert():
            return populated_registry.to_claude_tools()

        benchmark(convert)


class TestBuiltinToolBenchmarks:
    """Benchmarks for built-in tool execution."""

    def test_bench_datetime_tool(self, benchmark):
        """Benchmark get_current_datetime tool execution."""
        datetime_tool = tool_registry.get_tool("get_current_datetime")
        assert datetime_tool is not None

        def execute():
            return datetime_tool.handler()

        benchmark(execute)

    def test_bench_calculate_tool(self, benchmark):
        """Benchmark calculate tool execution."""
        calc_tool = tool_registry.get_tool("calculate")
        assert calc_tool is not None

        def execute():
            return calc_tool.handler("2 + 2 * 3 - 1")

        benchmark(execute)

    def test_bench_calculate_complex(self, benchmark):
        """Benchmark calculate tool with complex expression."""
        calc_tool = tool_registry.get_tool("calculate")
        assert calc_tool is not None

        def execute():
            return calc_tool.handler("(123 + 456) * 789 / 10 - 5")

        benchmark(execute)


class TestToolExecutionPipeline:
    """Benchmarks for the full tool execution pipeline."""

    def test_bench_lookup_and_execute(self, benchmark, populated_registry):
        """Benchmark looking up and executing a tool."""

        # First register a working tool
        populated_registry.register_tool(ToolSpec(
            name="echo_tool",
            description="Echo input",
            parameters=[ToolParameter("input", "string", "Input to echo")],
            handler=lambda x: f"Echo: {x}"
        ))

        def lookup_and_execute():
            tool = populated_registry.get_tool("echo_tool")
            if tool and tool.handler:
                return tool.handler("test input")
            return None

        benchmark(lookup_and_execute)

    def test_bench_validate_and_execute(self, benchmark):
        """Benchmark validating parameters and executing."""

        calc_tool = tool_registry.get_tool("calculate")

        def validate_and_execute():
            # Simulate parameter validation
            expression = "1 + 2 + 3"
            if not isinstance(expression, str):
                raise ValueError("Expression must be string")
            if len(expression) > 1000:
                raise ValueError("Expression too long")

            return calc_tool.handler(expression)

        benchmark(validate_and_execute)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--benchmark-only"])
