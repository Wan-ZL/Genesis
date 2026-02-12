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
import hashlib
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


def _compute_cache_key(url: str, max_length: int) -> str:
    """Compute a cache key hash for web_fetch arguments."""
    key_data = f"{url}:{max_length}"
    return hashlib.sha256(key_data.encode()).hexdigest()[:16]


def _web_fetch_impl(url: str, max_length: int = 4000, use_cache: bool = True) -> str:
    """Implementation for web_fetch tool.

    Supports caching for offline access via the degradation service.
    When offline or degraded, returns cached content if available.
    Successful fetches are cached for future offline use.

    Args:
        url: The URL to fetch
        max_length: Maximum characters to return (default 4000)
        use_cache: Whether to use caching (default True)
    """
    import httpx
    from .degradation import get_degradation_service, DegradationMode

    # Validate URL
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return f"Error: Invalid URL scheme. Only http and https are supported."
    if not parsed.netloc:
        return f"Error: Invalid URL. Missing domain."

    # Get degradation service for caching
    degradation_service = get_degradation_service()
    cache_key = _compute_cache_key(url, max_length)

    # Check if we should try cache first (offline or network issues)
    if use_cache and degradation_service.mode in (
        DegradationMode.OFFLINE,
        DegradationMode.DEGRADED,
        DegradationMode.RATE_LIMITED,
    ):
        cached = degradation_service.get_cached_tool_result("web_fetch", cache_key)
        if cached:
            logger.info(f"web_fetch: Returning cached content for {url} (mode: {degradation_service.mode.name})")
            cached_result = cached["result"]
            # Add cache indicator to result
            return f"[CACHED - {cached['cached_at']}]\n{cached_result}"

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
            # On error, try cache as fallback
            if use_cache:
                cached = degradation_service.get_cached_tool_result("web_fetch", cache_key)
                if cached:
                    logger.info(f"web_fetch: HTTP error, returning cached content for {url}")
                    return f"[CACHED FALLBACK - HTTP {response.status_code}]\n{cached['result']}"
            return f"Error: HTTP {response.status_code} - {response.reason_phrase}"

        content = response.text
        content_type = response.headers.get("content-type", "")

        # Truncate if too long
        if len(content) > max_length:
            content = content[:max_length] + f"\n\n[Content truncated at {max_length} characters. Total length: {len(response.text)}]"

        # Add metadata
        result = f"URL: {url}\nStatus: {response.status_code}\nContent-Type: {content_type}\n\n{content}"

        # Cache successful result for offline access
        if use_cache:
            degradation_service.cache_tool_result("web_fetch", cache_key, result)
            logger.debug(f"web_fetch: Cached result for {url}")

        return result

    except httpx.TimeoutException:
        logger.warning(f"web_fetch: Timeout fetching {url}")
        # Try cache on timeout
        if use_cache:
            cached = degradation_service.get_cached_tool_result("web_fetch", cache_key)
            if cached:
                logger.info(f"web_fetch: Timeout, returning cached content for {url}")
                return f"[CACHED FALLBACK - Timeout]\n{cached['result']}"
        return f"Error: Request timed out after 10 seconds"
    except httpx.RequestError as e:
        logger.error(f"web_fetch: Request error for {url}: {e}")
        # Try cache on network error
        if use_cache:
            cached = degradation_service.get_cached_tool_result("web_fetch", cache_key)
            if cached:
                logger.info(f"web_fetch: Network error, returning cached content for {url}")
                return f"[CACHED FALLBACK - Network Error]\n{cached['result']}"
        return f"Error: Failed to fetch URL - {str(e)}"
    except Exception as e:
        logger.error(f"web_fetch: Unexpected error for {url}: {e}")
        return f"Error: {str(e)}"


# Register web_fetch with explicit spec
registry.register_tool(ToolSpec(
    name="web_fetch",
    description="Fetch content from a URL. Returns the text content of the webpage. Useful for reading articles, documentation, or any web page. Supports offline caching - results are cached for later use when network is unavailable. Note: Only fetches text content, does not execute JavaScript.",
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
        ToolParameter(
            name="use_cache",
            type="boolean",
            description="Whether to use caching for offline access. Default: true. Set to false to always fetch fresh content.",
            required=False,
            default=True,
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


# ============================================================
# Calendar Tools
# ============================================================

def _list_events_impl(
    start_date: str = "",
    end_date: str = "",
    calendar_name: str = ""
) -> str:
    """Implementation for list_events tool."""
    import asyncio
    from .calendar import get_calendar_service, CALDAV_AVAILABLE

    if not CALDAV_AVAILABLE:
        return "Error: Calendar functionality not available. Install caldav: pip install caldav"

    service = get_calendar_service()
    if not service.is_configured:
        return "Error: Calendar not configured. Set calendar credentials in settings."

    try:
        # Parse dates
        start = None
        end = None
        if start_date:
            start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            if start.tzinfo:
                start = start.replace(tzinfo=None)
        if end_date:
            end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            if end.tzinfo:
                end = end.replace(tzinfo=None)

        # Run async function
        loop = asyncio.new_event_loop()
        try:
            events = loop.run_until_complete(
                service.list_events(
                    start=start,
                    end=end,
                    calendar_name=calendar_name or None
                )
            )
        finally:
            loop.close()

        if not events:
            return "No events found in the specified date range."

        # Format output
        lines = [f"Found {len(events)} event(s):\n"]
        for event in events:
            lines.append(f"- {event.title}")
            lines.append(f"  Start: {event.start.strftime('%Y-%m-%d %H:%M')}")
            lines.append(f"  End: {event.end.strftime('%Y-%m-%d %H:%M')}")
            if event.location:
                lines.append(f"  Location: {event.location}")
            if event.calendar_name:
                lines.append(f"  Calendar: {event.calendar_name}")
            lines.append(f"  ID: {event.event_id}")
            lines.append("")

        return "\n".join(lines)

    except Exception as e:
        logger.error(f"list_events error: {e}")
        return f"Error listing events: {str(e)}"


# Register list_events tool
registry.register_tool(ToolSpec(
    name="list_events",
    description="List calendar events in a date range. Returns upcoming events from the user's calendar. Useful for checking schedule, finding appointments, or reviewing upcoming meetings.",
    parameters=[
        ToolParameter(
            name="start_date",
            type="string",
            description="Start date in ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS). Default: now",
            required=False,
            default="",
        ),
        ToolParameter(
            name="end_date",
            type="string",
            description="End date in ISO format. Default: 7 days from start",
            required=False,
            default="",
        ),
        ToolParameter(
            name="calendar_name",
            type="string",
            description="Specific calendar name to search. Default: all calendars",
            required=False,
            default="",
        ),
    ],
    handler=_list_events_impl,
    required_permission=PermissionLevel.SYSTEM,  # Calendar access is sensitive
))


def _create_event_impl(
    title: str,
    start: str,
    end: str,
    location: str = "",
    notes: str = "",
    calendar_name: str = ""
) -> str:
    """Implementation for create_event tool."""
    import asyncio
    from .calendar import get_calendar_service, CALDAV_AVAILABLE

    if not CALDAV_AVAILABLE:
        return "Error: Calendar functionality not available. Install caldav: pip install caldav"

    service = get_calendar_service()
    if not service.is_configured:
        return "Error: Calendar not configured. Set calendar credentials in settings."

    try:
        # Parse dates
        start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))

        # Remove timezone info for consistency
        if start_dt.tzinfo:
            start_dt = start_dt.replace(tzinfo=None)
        if end_dt.tzinfo:
            end_dt = end_dt.replace(tzinfo=None)

        # Run async function
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                service.create_event(
                    title=title,
                    start=start_dt,
                    end=end_dt,
                    location=location or None,
                    notes=notes or None,
                    calendar_name=calendar_name or None
                )
            )
        finally:
            loop.close()

        if result["success"]:
            response = f"Event created successfully!\nTitle: {title}\nStart: {start_dt}\nEnd: {end_dt}\nID: {result['event_id']}"
            if result.get("conflicts"):
                response += f"\n\nWarning: Conflicts with {len(result['conflicts'])} existing event(s):"
                for conflict in result["conflicts"]:
                    response += f"\n- {conflict['title']} ({conflict['start']} - {conflict['end']})"
            return response
        else:
            return f"Error creating event: {result.get('error')}"

    except ValueError as e:
        return f"Error: Invalid date format. Use ISO format (YYYY-MM-DDTHH:MM:SS). {str(e)}"
    except Exception as e:
        logger.error(f"create_event error: {e}")
        return f"Error creating event: {str(e)}"


# Register create_event tool
registry.register_tool(ToolSpec(
    name="create_event",
    description="Create a new calendar event. Use this to schedule meetings, appointments, or reminders on the user's calendar.",
    parameters=[
        ToolParameter(
            name="title",
            type="string",
            description="Event title/summary",
            required=True,
        ),
        ToolParameter(
            name="start",
            type="string",
            description="Event start time in ISO format (e.g., 2026-02-05T14:00:00)",
            required=True,
        ),
        ToolParameter(
            name="end",
            type="string",
            description="Event end time in ISO format (e.g., 2026-02-05T15:00:00)",
            required=True,
        ),
        ToolParameter(
            name="location",
            type="string",
            description="Event location (optional)",
            required=False,
            default="",
        ),
        ToolParameter(
            name="notes",
            type="string",
            description="Event description/notes (optional)",
            required=False,
            default="",
        ),
        ToolParameter(
            name="calendar_name",
            type="string",
            description="Calendar to add event to (optional, uses default)",
            required=False,
            default="",
        ),
    ],
    handler=_create_event_impl,
    required_permission=PermissionLevel.SYSTEM,
))


def _update_event_impl(
    event_id: str,
    title: str = "",
    start: str = "",
    end: str = "",
    location: str = "",
    notes: str = "",
    calendar_name: str = ""
) -> str:
    """Implementation for update_event tool."""
    import asyncio
    from .calendar import get_calendar_service, CALDAV_AVAILABLE

    if not CALDAV_AVAILABLE:
        return "Error: Calendar functionality not available. Install caldav: pip install caldav"

    service = get_calendar_service()
    if not service.is_configured:
        return "Error: Calendar not configured. Set calendar credentials in settings."

    try:
        # Parse optional dates
        start_dt = None
        end_dt = None
        if start:
            start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
            if start_dt.tzinfo:
                start_dt = start_dt.replace(tzinfo=None)
        if end:
            end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))
            if end_dt.tzinfo:
                end_dt = end_dt.replace(tzinfo=None)

        # Run async function
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                service.update_event(
                    event_id=event_id,
                    title=title or None,
                    start=start_dt,
                    end=end_dt,
                    location=location or None,
                    notes=notes or None,
                    calendar_name=calendar_name or None
                )
            )
        finally:
            loop.close()

        if result["success"]:
            response = f"Event updated successfully! ID: {event_id}"
            if result.get("conflicts"):
                response += f"\n\nWarning: Now conflicts with {len(result['conflicts'])} event(s):"
                for conflict in result["conflicts"]:
                    response += f"\n- {conflict['title']} ({conflict['start']} - {conflict['end']})"
            return response
        else:
            return f"Error updating event: {result.get('error')}"

    except ValueError as e:
        return f"Error: Invalid date format. Use ISO format. {str(e)}"
    except Exception as e:
        logger.error(f"update_event error: {e}")
        return f"Error updating event: {str(e)}"


# Register update_event tool
registry.register_tool(ToolSpec(
    name="update_event",
    description="Update an existing calendar event. Change the title, time, location, or notes of an event.",
    parameters=[
        ToolParameter(
            name="event_id",
            type="string",
            description="ID of the event to update (from list_events)",
            required=True,
        ),
        ToolParameter(
            name="title",
            type="string",
            description="New event title (optional)",
            required=False,
            default="",
        ),
        ToolParameter(
            name="start",
            type="string",
            description="New start time in ISO format (optional)",
            required=False,
            default="",
        ),
        ToolParameter(
            name="end",
            type="string",
            description="New end time in ISO format (optional)",
            required=False,
            default="",
        ),
        ToolParameter(
            name="location",
            type="string",
            description="New location (optional)",
            required=False,
            default="",
        ),
        ToolParameter(
            name="notes",
            type="string",
            description="New notes/description (optional)",
            required=False,
            default="",
        ),
        ToolParameter(
            name="calendar_name",
            type="string",
            description="Calendar containing the event (optional)",
            required=False,
            default="",
        ),
    ],
    handler=_update_event_impl,
    required_permission=PermissionLevel.SYSTEM,
))


def _delete_event_impl(event_id: str, calendar_name: str = "") -> str:
    """Implementation for delete_event tool."""
    import asyncio
    from .calendar import get_calendar_service, CALDAV_AVAILABLE

    if not CALDAV_AVAILABLE:
        return "Error: Calendar functionality not available. Install caldav: pip install caldav"

    service = get_calendar_service()
    if not service.is_configured:
        return "Error: Calendar not configured. Set calendar credentials in settings."

    try:
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                service.delete_event(
                    event_id=event_id,
                    calendar_name=calendar_name or None
                )
            )
        finally:
            loop.close()

        if result["success"]:
            return f"Event deleted successfully. ID: {event_id}"
        else:
            return f"Error deleting event: {result.get('error')}"

    except Exception as e:
        logger.error(f"delete_event error: {e}")
        return f"Error deleting event: {str(e)}"


# Register delete_event tool
registry.register_tool(ToolSpec(
    name="delete_event",
    description="Delete a calendar event. Permanently removes an event from the calendar.",
    parameters=[
        ToolParameter(
            name="event_id",
            type="string",
            description="ID of the event to delete (from list_events)",
            required=True,
        ),
        ToolParameter(
            name="calendar_name",
            type="string",
            description="Calendar containing the event (optional)",
            required=False,
            default="",
        ),
    ],
    handler=_delete_event_impl,
    required_permission=PermissionLevel.SYSTEM,
))


def _find_free_time_impl(
    duration_minutes: int,
    start_date: str = "",
    end_date: str = "",
    calendar_name: str = "",
    work_hours_start: int = 9,
    work_hours_end: int = 17,
    include_weekends: bool = False
) -> str:
    """Implementation for find_free_time tool."""
    import asyncio
    from .calendar import get_calendar_service, CALDAV_AVAILABLE

    if not CALDAV_AVAILABLE:
        return "Error: Calendar functionality not available. Install caldav: pip install caldav"

    service = get_calendar_service()
    if not service.is_configured:
        return "Error: Calendar not configured. Set calendar credentials in settings."

    try:
        # Parse dates
        start = None
        end = None
        if start_date:
            start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            if start.tzinfo:
                start = start.replace(tzinfo=None)
        if end_date:
            end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            if end.tzinfo:
                end = end.replace(tzinfo=None)

        # Run async function
        loop = asyncio.new_event_loop()
        try:
            slots = loop.run_until_complete(
                service.find_free_time(
                    duration_minutes=duration_minutes,
                    start=start,
                    end=end,
                    calendar_name=calendar_name or None,
                    work_hours_start=work_hours_start,
                    work_hours_end=work_hours_end,
                    include_weekends=include_weekends
                )
            )
        finally:
            loop.close()

        if not slots:
            return f"No free slots of {duration_minutes} minutes found in the specified range."

        # Format output
        lines = [f"Found {len(slots)} free time slot(s) of at least {duration_minutes} minutes:\n"]
        for i, slot in enumerate(slots, 1):
            day_name = slot.start.strftime('%A')
            date_str = slot.start.strftime('%Y-%m-%d')
            time_str = f"{slot.start.strftime('%H:%M')} - {slot.end.strftime('%H:%M')}"
            lines.append(f"{i}. {day_name}, {date_str}: {time_str}")

        return "\n".join(lines)

    except Exception as e:
        logger.error(f"find_free_time error: {e}")
        return f"Error finding free time: {str(e)}"


# Register find_free_time tool
registry.register_tool(ToolSpec(
    name="find_free_time",
    description="Find available time slots in the calendar. Useful for scheduling meetings by finding when the user is free.",
    parameters=[
        ToolParameter(
            name="duration_minutes",
            type="integer",
            description="Minimum duration needed in minutes (e.g., 30, 60)",
            required=True,
        ),
        ToolParameter(
            name="start_date",
            type="string",
            description="Start of search range in ISO format. Default: now",
            required=False,
            default="",
        ),
        ToolParameter(
            name="end_date",
            type="string",
            description="End of search range in ISO format. Default: 7 days from start",
            required=False,
            default="",
        ),
        ToolParameter(
            name="calendar_name",
            type="string",
            description="Calendar to check (optional, checks all)",
            required=False,
            default="",
        ),
        ToolParameter(
            name="work_hours_start",
            type="integer",
            description="Start of work hours (0-23). Default: 9",
            required=False,
            default=9,
        ),
        ToolParameter(
            name="work_hours_end",
            type="integer",
            description="End of work hours (0-23). Default: 17",
            required=False,
            default=17,
        ),
        ToolParameter(
            name="include_weekends",
            type="boolean",
            description="Include Saturday/Sunday in search. Default: false",
            required=False,
            default=False,
        ),
    ],
    handler=_find_free_time_impl,
    required_permission=PermissionLevel.SYSTEM,
))


# ============================================================
# Repository Analysis Tools
# ============================================================

def _read_file_impl(
    file_path: str,
    max_length: int = 50000,
    start_line: int = 1,
    end_line: int = 0,
) -> str:
    """Implementation for read_file tool."""
    from .repository import get_repository_service

    service = get_repository_service()
    result = service.read_file(
        file_path=file_path,
        max_length=max_length if max_length > 0 else None,
        start_line=start_line,
        end_line=end_line if end_line > 0 else None,
    )

    if not result["success"]:
        return f"Error: {result['error']}"

    # Format output with line numbers
    lines = result["content"].split("\n")
    numbered_lines = []
    for i, line in enumerate(lines, start=result.get("start_line", 1)):
        numbered_lines.append(f"{i:5d} | {line}")

    output = "\n".join(numbered_lines)

    # Add metadata header
    header = f"File: {result['path']}\n"
    header += f"Lines: {result.get('start_line', 1)}-{result.get('end_line', result['lines'])} of {result['lines']}\n"
    if result.get("truncated"):
        header += "[Content truncated]\n"
    header += "-" * 60 + "\n"

    return header + output


# Register read_file tool
registry.register_tool(ToolSpec(
    name="read_file",
    description="Read the contents of a file from the codebase. Returns the file contents with line numbers. Useful for reviewing code, understanding implementations, or analyzing files. Respects path security restrictions.",
    parameters=[
        ToolParameter(
            name="file_path",
            type="string",
            description="Path to the file (absolute or relative to project root)",
            required=True,
        ),
        ToolParameter(
            name="max_length",
            type="integer",
            description="Maximum characters to return. Default: 50000. Use smaller values for quick previews.",
            required=False,
            default=50000,
        ),
        ToolParameter(
            name="start_line",
            type="integer",
            description="First line to read (1-indexed). Default: 1",
            required=False,
            default=1,
        ),
        ToolParameter(
            name="end_line",
            type="integer",
            description="Last line to read. Default: 0 (read to end)",
            required=False,
            default=0,
        ),
    ],
    handler=_read_file_impl,
    required_permission=PermissionLevel.LOCAL,  # Requires LOCAL permission
))


def _list_files_impl(
    directory: str = ".",
    pattern: str = "*",
    recursive: bool = False,
    include_hidden: bool = False,
) -> str:
    """Implementation for list_files tool."""
    from .repository import get_repository_service

    service = get_repository_service()
    result = service.list_files(
        directory=directory,
        pattern=pattern,
        recursive=recursive,
        include_hidden=include_hidden,
    )

    if not result["success"]:
        return f"Error: {result['error']}"

    # Format output
    files = result["files"]
    if not files:
        return f"No files found in {result['directory']} matching '{pattern}'"

    lines = [f"Directory: {result['directory']}"]
    lines.append(f"Pattern: {pattern}")
    lines.append(f"Found: {result['total']} items")
    if result.get("truncated"):
        lines.append("[Results truncated]")
    lines.append("-" * 60)

    for f in files:
        if f.is_directory:
            lines.append(f"  📁 {f.path}/")
        else:
            size_str = _format_size(f.size)
            lines.append(f"  📄 {f.path} ({size_str})")

    return "\n".join(lines)


def _format_size(size: int) -> str:
    """Format file size in human-readable form."""
    value: float = float(size)
    for unit in ["B", "KB", "MB", "GB"]:
        if value < 1024:
            return f"{value:.0f}{unit}" if unit == "B" else f"{value:.1f}{unit}"
        value /= 1024
    return f"{value:.1f}TB"


# Register list_files tool
registry.register_tool(ToolSpec(
    name="list_files",
    description="List files in a directory with optional pattern matching. Useful for exploring the codebase structure, finding specific file types, or understanding project organization.",
    parameters=[
        ToolParameter(
            name="directory",
            type="string",
            description="Directory path to list. Default: current project root",
            required=False,
            default=".",
        ),
        ToolParameter(
            name="pattern",
            type="string",
            description="Glob pattern to filter files (e.g., '*.py', '*.ts', 'test_*'). Default: '*' (all files)",
            required=False,
            default="*",
        ),
        ToolParameter(
            name="recursive",
            type="boolean",
            description="Search subdirectories recursively. Default: false",
            required=False,
            default=False,
        ),
        ToolParameter(
            name="include_hidden",
            type="boolean",
            description="Include hidden files/directories (starting with .). Default: false",
            required=False,
            default=False,
        ),
    ],
    handler=_list_files_impl,
    required_permission=PermissionLevel.LOCAL,
))


def _search_code_impl(
    pattern: str,
    directory: str = ".",
    file_pattern: str = "*",
    context_lines: int = 2,
    max_results: int = 50,
    case_sensitive: bool = True,
) -> str:
    """Implementation for search_code tool."""
    from .repository import get_repository_service

    service = get_repository_service()
    result = service.search_code(
        pattern=pattern,
        directory=directory,
        file_pattern=file_pattern,
        context_lines=context_lines,
        max_results=max_results,
        case_sensitive=case_sensitive,
        regex=True,
    )

    if not result["success"]:
        return f"Error: {result['error']}"

    matches = result["matches"]
    if not matches:
        return f"No matches found for '{pattern}' in {result['files_searched']} files"

    # Format output
    lines = [f"Search: '{pattern}'"]
    lines.append(f"Files searched: {result['files_searched']}")
    lines.append(f"Matches: {result['total']}")
    if result.get("truncated"):
        lines.append(f"[Showing first {len(matches)} of {result['total']} matches]")
    lines.append("=" * 60)

    current_file = None
    for match in matches:
        if match.file != current_file:
            lines.append(f"\n📄 {match.file}")
            lines.append("-" * 40)
            current_file = match.file

        # Show context before
        for ctx_line in match.context_before:
            lines.append(f"  {ctx_line}")

        # Highlight match line
        lines.append(f"→ {match.line_number:5d}: {match.line}")

        # Show context after
        for ctx_line in match.context_after:
            lines.append(f"  {ctx_line}")

        lines.append("")

    return "\n".join(lines)


# Register search_code tool
registry.register_tool(ToolSpec(
    name="search_code",
    description="Search for patterns in code files using regex. Similar to ripgrep. Returns matching lines with context. Useful for finding function definitions, class usages, imports, or any code pattern.",
    parameters=[
        ToolParameter(
            name="pattern",
            type="string",
            description="Search pattern (regex). Examples: 'def.*test', 'class\\s+\\w+', 'TODO'",
            required=True,
        ),
        ToolParameter(
            name="directory",
            type="string",
            description="Directory to search. Default: project root",
            required=False,
            default=".",
        ),
        ToolParameter(
            name="file_pattern",
            type="string",
            description="Glob pattern to filter files (e.g., '*.py'). Default: '*' (all text files)",
            required=False,
            default="*",
        ),
        ToolParameter(
            name="context_lines",
            type="integer",
            description="Lines of context before/after match. Default: 2",
            required=False,
            default=2,
        ),
        ToolParameter(
            name="max_results",
            type="integer",
            description="Maximum matches to return. Default: 50",
            required=False,
            default=50,
        ),
        ToolParameter(
            name="case_sensitive",
            type="boolean",
            description="Case-sensitive search. Default: true",
            required=False,
            default=True,
        ),
    ],
    handler=_search_code_impl,
    required_permission=PermissionLevel.LOCAL,
))


def _get_file_info_impl(file_path: str) -> str:
    """Implementation for get_file_info tool."""
    from .repository import get_repository_service

    service = get_repository_service()
    result = service.get_file_info(file_path)

    if not result["success"]:
        return f"Error: {result['error']}"

    # Format output
    lines = [f"Path: {result['path']}"]
    lines.append(f"Name: {result['name']}")
    lines.append(f"Type: {'Directory' if result['is_directory'] else 'File'}")
    if result['is_file']:
        lines.append(f"Size: {_format_size(result['size'])}")
        lines.append(f"Extension: {result['extension'] or 'none'}")
        lines.append(f"Binary: {'Yes' if result['is_binary'] else 'No'}")
        lines.append(f"Readable: {'Yes' if result['can_read'] else 'No'}")
        if result['is_sensitive']:
            lines.append("⚠️ Sensitive file (access restricted)")

    return "\n".join(lines)


# Register get_file_info tool
registry.register_tool(ToolSpec(
    name="get_file_info",
    description="Get information about a file without reading its contents. Returns metadata like size, type, and whether it can be read. Useful for checking file properties before reading.",
    parameters=[
        ToolParameter(
            name="file_path",
            type="string",
            description="Path to the file or directory",
            required=True,
        ),
    ],
    handler=_get_file_info_impl,
    required_permission=PermissionLevel.LOCAL,
))


# ============================================================
# MCP Tool Integration
# ============================================================

def register_mcp_tools_from_manager():
    """Register tools from connected MCP servers into Genesis tool registry.

    This function should be called after MCP manager connects to servers.
    It bridges MCP tools into Genesis's native tool system.
    """
    try:
        from .mcp_client import get_mcp_manager

        manager = get_mcp_manager()
        mcp_tools = manager.get_all_tools()

        for mcp_tool in mcp_tools:
            # Create a handler that routes to MCP
            def make_mcp_handler(tool_name_capture: str):
                async def mcp_handler(**kwargs):
                    """Handler that routes to MCP server."""
                    result = await manager.call_tool(tool_name_capture, kwargs)
                    # Extract text from MCP response
                    if isinstance(result, dict) and "content" in result:
                        content = result["content"]
                        if isinstance(content, list) and len(content) > 0:
                            return content[0].get("text", str(result))
                    return str(result)
                return mcp_handler

            # Convert MCP input schema to Genesis ToolParameter format
            parameters = []
            input_schema = mcp_tool.input_schema
            properties = input_schema.get("properties", {})
            required_fields = input_schema.get("required", [])

            for param_name, param_def in properties.items():
                param_type = param_def.get("type", "string")
                param_desc = param_def.get("description", f"Parameter: {param_name}")
                parameters.append(ToolParameter(
                    name=param_name,
                    type=param_type,
                    description=param_desc,
                    required=param_name in required_fields
                ))

            # Register as Genesis tool with mcp: prefix to avoid naming conflicts
            tool_name = f"mcp:{mcp_tool.server_name}:{mcp_tool.name}"
            spec = ToolSpec(
                name=tool_name,
                description=f"[MCP: {mcp_tool.server_name}] {mcp_tool.description}",
                parameters=parameters,
                handler=make_mcp_handler(mcp_tool.name),
                required_permission=PermissionLevel.LOCAL  # MCP tools require LOCAL by default
            )
            registry.register_tool(spec)
            logger.info(f"Registered MCP tool: {tool_name}")

    except ImportError:
        logger.debug("MCP module not available, skipping MCP tool registration")
    except Exception as e:
        logger.error(f"Failed to register MCP tools: {e}")
