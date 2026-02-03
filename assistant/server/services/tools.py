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
import re
from urllib.parse import urlparse

# Import permission system
import sys
from pathlib import Path
# Add parent path for core module
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from core.permissions import PermissionLevel, get_permission_level, can_access

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
    # Permission level required to execute this tool (default: SANDBOX)
    required_permission: PermissionLevel = PermissionLevel.SANDBOX


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
            dict with:
            - 'success' bool and 'result' for successful execution
            - 'success' False and 'error' for errors
            - 'success' False and 'permission_escalation' for permission requests
        """
        tool = self._tools.get(name)
        if not tool:
            return {"success": False, "error": f"Tool not found: {name}"}

        # Check permission before execution
        current_level = get_permission_level()
        required_level = tool.required_permission

        if not can_access(required_level):
            logger.info(
                f"Tool {name} requires {required_level.name} permission "
                f"(current: {current_level.name}). Returning escalation request."
            )
            return {
                "success": False,
                "permission_escalation": {
                    "tool_name": name,
                    "tool_description": tool.description,
                    "current_level": current_level.value,
                    "current_level_name": current_level.name,
                    "required_level": required_level.value,
                    "required_level_name": required_level.name,
                    "pending_args": kwargs,
                }
            }

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


def _web_fetch_impl(url: str, max_length: int = 4000) -> str:
    """Implementation for web_fetch tool."""
    import httpx

    # Validate URL
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return f"Error: Invalid URL scheme. Only http and https are supported."
    if not parsed.netloc:
        return f"Error: Invalid URL. Missing domain."

    # Log external call (per network rules in 04-tools-network.md)
    logger.info(f"web_fetch: Fetching URL={url}, purpose=user_request")

    try:
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            response = client.get(url, headers={
                "User-Agent": "GenesisAssistant/1.0 (AI Assistant web_fetch tool)"
            })

        # Log result summary
        logger.info(f"web_fetch: status={response.status_code}, content_type={response.headers.get('content-type', 'unknown')}, length={len(response.text)}")

        if response.status_code != 200:
            return f"Error: HTTP {response.status_code} - {response.reason_phrase}"

        content = response.text
        content_type = response.headers.get("content-type", "")

        # Truncate if too long
        if len(content) > max_length:
            content = content[:max_length] + f"\n\n[Content truncated at {max_length} characters. Total length: {len(response.text)}]"

        # Add metadata
        result = f"URL: {url}\nStatus: {response.status_code}\nContent-Type: {content_type}\n\n{content}"
        return result

    except httpx.TimeoutException:
        logger.warning(f"web_fetch: Timeout fetching {url}")
        return f"Error: Request timed out after 10 seconds"
    except httpx.RequestError as e:
        logger.error(f"web_fetch: Request error for {url}: {e}")
        return f"Error: Failed to fetch URL - {str(e)}"
    except Exception as e:
        logger.error(f"web_fetch: Unexpected error for {url}: {e}")
        return f"Error: {str(e)}"


# Register web_fetch with explicit spec
registry.register_tool(ToolSpec(
    name="web_fetch",
    description="Fetch content from a URL. Returns the text content of the webpage. Useful for reading articles, documentation, or any web page. Note: Only fetches text content, does not execute JavaScript.",
    parameters=[
        ToolParameter(
            name="url",
            type="string",
            description="The URL to fetch. Must be a valid http or https URL.",
            required=True,
        ),
        ToolParameter(
            name="max_length",
            type="integer",
            description="Maximum characters to return. Default: 4000. Increase for longer content, decrease for summaries.",
            required=False,
            default=4000,
        ),
    ],
    handler=_web_fetch_impl,
))

# Expose for direct calls
web_fetch = _web_fetch_impl


def _run_shell_command_impl(command: str, timeout: int = 30) -> str:
    """Implementation for run_shell_command tool.

    Requires SYSTEM permission level.
    """
    import subprocess

    # Safety check: block extremely dangerous commands
    dangerous_patterns = [
        "rm -rf /",
        "rm -rf ~",
        ":(){:|:&};:",  # fork bomb
        "mkfs.",
        "dd if=/dev/zero",
        "> /dev/sda",
    ]

    cmd_lower = command.lower()
    for pattern in dangerous_patterns:
        if pattern in cmd_lower:
            return f"Error: Command blocked for safety reasons (matched pattern: {pattern})"

    logger.info(f"run_shell_command: Executing command='{command}', timeout={timeout}")

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(Path(__file__).parent.parent.parent.parent)  # Genesis root
        )

        output_parts = []
        if result.stdout:
            output_parts.append(f"STDOUT:\n{result.stdout}")
        if result.stderr:
            output_parts.append(f"STDERR:\n{result.stderr}")
        if not output_parts:
            output_parts.append("(no output)")

        output_parts.append(f"\nExit code: {result.returncode}")

        output = "\n".join(output_parts)

        # Truncate if too long
        if len(output) > 4000:
            output = output[:4000] + f"\n\n[Output truncated at 4000 characters]"

        logger.info(f"run_shell_command: exit_code={result.returncode}, output_length={len(output)}")
        return output

    except subprocess.TimeoutExpired:
        logger.warning(f"run_shell_command: Command timed out after {timeout}s")
        return f"Error: Command timed out after {timeout} seconds"
    except Exception as e:
        logger.error(f"run_shell_command: Error executing command: {e}")
        return f"Error: {str(e)}"


# Register run_shell_command with SYSTEM permission requirement
registry.register_tool(ToolSpec(
    name="run_shell_command",
    description="Execute a shell command on the system. Returns stdout, stderr, and exit code. Use for file operations, git commands, running scripts, etc. Note: This tool requires SYSTEM permission level.",
    parameters=[
        ToolParameter(
            name="command",
            type="string",
            description="The shell command to execute. Example: 'ls -la' or 'git status'",
            required=True,
        ),
        ToolParameter(
            name="timeout",
            type="integer",
            description="Maximum seconds to wait for command completion. Default: 30",
            required=False,
            default=30,
        ),
    ],
    handler=_run_shell_command_impl,
    required_permission=PermissionLevel.SYSTEM,  # Requires elevated permission
))

# Expose for direct calls (bypasses permission check)
run_shell_command = _run_shell_command_impl
