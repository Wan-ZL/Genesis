"""
Tool Registry System

This module provides a registry for tools that the AI Assistant can use.
Tools allow the assistant to perform actions beyond just generating text.

Tool Requirements (per .claude/rules/04-tools-network.md):
1. Interface spec - defined via ToolSpec dataclass
2. Tests - in tests/test_tools.py
3. Documentation - in docstrings and registry
4. Registry entry - via @register_tool decorator
"""

from dataclasses import dataclass, field
from typing import Callable, Any, Optional
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class ToolParameter:
    """Specification for a tool parameter."""
    name: str
    type: str  # "string", "integer", "boolean", "array", "object"
    description: str
    required: bool = True
    default: Any = None


@dataclass
class ToolSpec:
    """Specification for a tool that can be registered."""
    name: str
    description: str
    parameters: list[ToolParameter] = field(default_factory=list)
    # The actual function to execute
    handler: Optional[Callable[..., Any]] = None


class ToolRegistry:
    """
    Central registry for all available tools.

    Usage:
        registry = ToolRegistry()

        @registry.register
        def my_tool(param1: str) -> str:
            '''Tool description.'''
            return f"Result: {param1}"

        # Or register with explicit spec:
        registry.register_tool(ToolSpec(
            name="my_tool",
            description="Does something",
            parameters=[ToolParameter("param1", "string", "Input value")],
            handler=my_handler_fn
        ))
    """

    def __init__(self):
        self._tools: dict[str, ToolSpec] = {}

    def register(self, func: Callable) -> Callable:
        """
        Decorator to register a function as a tool.
        Uses function name and docstring for spec.
        """
        name = func.__name__
        description = func.__doc__ or f"Tool: {name}"

        # Extract parameter info from type hints
        import inspect
        sig = inspect.signature(func)
        parameters = []
        for param_name, param in sig.parameters.items():
            param_type = "string"  # default
            if param.annotation != inspect.Parameter.empty:
                type_map = {
                    str: "string",
                    int: "integer",
                    float: "number",
                    bool: "boolean",
                    list: "array",
                    dict: "object",
                }
                param_type = type_map.get(param.annotation, "string")

            required = param.default == inspect.Parameter.empty
            default = None if required else param.default

            parameters.append(ToolParameter(
                name=param_name,
                type=param_type,
                description=f"Parameter: {param_name}",
                required=required,
                default=default,
            ))

        spec = ToolSpec(
            name=name,
            description=description.strip(),
            parameters=parameters,
            handler=func,
        )
        self._tools[name] = spec
        logger.info(f"Registered tool: {name}")
        return func

    def register_tool(self, spec: ToolSpec) -> None:
        """Register a tool with explicit specification."""
        if not spec.handler:
            raise ValueError(f"Tool {spec.name} must have a handler")
        self._tools[spec.name] = spec
        logger.info(f"Registered tool: {spec.name}")

    def get_tool(self, name: str) -> Optional[ToolSpec]:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    def get_all_specs(self) -> list[ToolSpec]:
        """Get all tool specifications."""
        return list(self._tools.values())

    def execute(self, name: str, **kwargs) -> dict[str, Any]:
        """
        Execute a tool by name with given arguments.

        Returns:
            dict with 'success' bool and 'result' or 'error'
        """
        tool = self._tools.get(name)
        if not tool:
            return {"success": False, "error": f"Tool not found: {name}"}

        try:
            result = tool.handler(**kwargs)
            logger.info(f"Tool {name} executed successfully")
            return {"success": True, "result": result}
        except Exception as e:
            logger.error(f"Tool {name} failed: {e}")
            return {"success": False, "error": str(e)}

    def to_openai_tools(self) -> list[dict]:
        """
        Convert registered tools to OpenAI function calling format.

        Returns:
            List of tool definitions for OpenAI API
        """
        tools = []
        for spec in self._tools.values():
            properties = {}
            required = []
            for param in spec.parameters:
                properties[param.name] = {
                    "type": param.type,
                    "description": param.description,
                }
                if param.required:
                    required.append(param.name)

            tools.append({
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                    },
                },
            })
        return tools

    def to_claude_tools(self) -> list[dict]:
        """
        Convert registered tools to Claude/Anthropic tool format.

        Returns:
            List of tool definitions for Claude API
        """
        tools = []
        for spec in self._tools.values():
            properties = {}
            required = []
            for param in spec.parameters:
                properties[param.name] = {
                    "type": param.type,
                    "description": param.description,
                }
                if param.required:
                    required.append(param.name)

            tools.append({
                "name": spec.name,
                "description": spec.description,
                "input_schema": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            })
        return tools


# Global registry instance
registry = ToolRegistry()


# ============================================================
# Built-in Tools
# ============================================================

def _get_current_datetime_impl(format: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Implementation for get_current_datetime."""
    return datetime.now().strftime(format)


# Register with explicit spec for better LLM understanding
registry.register_tool(ToolSpec(
    name="get_current_datetime",
    description="Get the current date and time. Returns the current local date and time in the specified format. Useful for answering 'what time is it?' or 'what day is today?'",
    parameters=[
        ToolParameter(
            name="format",
            type="string",
            description="Python strftime format string. Common formats: '%Y-%m-%d %H:%M:%S' (full datetime), '%H:%M' (time only), '%Y-%m-%d' (date only), '%A' (day name), '%B %d, %Y' (readable date). Default: '%Y-%m-%d %H:%M:%S'",
            required=False,
            default="%Y-%m-%d %H:%M:%S",
        )
    ],
    handler=_get_current_datetime_impl,
))

# Expose implementation for direct calls and testing
get_current_datetime = _get_current_datetime_impl


@registry.register
def calculate(expression: str) -> str:
    """
    Evaluate a simple mathematical expression.
    Supports +, -, *, /, **, (), and basic math functions.
    Example: "2 + 3 * 4" returns "14"
    """
    # Safe evaluation of math expressions
    import ast
    import operator

    # Supported operators
    operators = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    def eval_expr(node):
        if isinstance(node, ast.Constant):  # Python 3.8+
            return node.value
        elif isinstance(node, ast.BinOp):
            left = eval_expr(node.left)
            right = eval_expr(node.right)
            return operators[type(node.op)](left, right)
        elif isinstance(node, ast.UnaryOp):
            operand = eval_expr(node.operand)
            return operators[type(node.op)](operand)
        else:
            raise ValueError(f"Unsupported expression: {ast.dump(node)}")

    try:
        tree = ast.parse(expression, mode='eval')
        result = eval_expr(tree.body)
        return str(result)
    except Exception as e:
        return f"Error: {e}"
