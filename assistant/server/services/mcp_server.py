"""MCP (Model Context Protocol) Server for exposing Genesis tools to external agents.

This module implements the MCP server specification, allowing external AI agents
to discover and use Genesis tools via the Model Context Protocol.

MCP Protocol: https://spec.modelcontextprotocol.io/
"""

import logging
from typing import Dict, Any, Optional
from fastapi import Request
from fastapi.responses import JSONResponse
from server.services.tools import registry as tool_registry

logger = logging.getLogger(__name__)


class MCPServer:
    """
    MCP Server implementation for Genesis.

    Exposes Genesis tools to external AI agents via the Model Context Protocol.
    Supports both stdio and SSE transports.
    """

    def __init__(self, permission_level: int = 0):
        """Initialize MCP server.

        Args:
            permission_level: Permission level for tool execution (default: SANDBOX)
        """
        self.permission_level = permission_level
        self.protocol_version = "2024-11-05"
        self.server_info = {
            "name": "genesis-mcp-server",
            "version": "0.1.0"
        }

    def handle_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle a JSON-RPC 2.0 request.

        Args:
            request_data: JSON-RPC request object

        Returns:
            JSON-RPC response object
        """
        # Validate JSON-RPC format
        if request_data.get("jsonrpc") != "2.0":
            return self._error_response(
                request_data.get("id"),
                -32600,
                "Invalid Request: jsonrpc must be '2.0'"
            )

        method = request_data.get("method")
        params = request_data.get("params", {})
        request_id = request_data.get("id")

        # Handle notifications (no response needed)
        if request_id is None:
            self._handle_notification(method or "", params)
            return {}

        # Handle method calls
        try:
            if method == "initialize":
                result = self._handle_initialize(params)
            elif method == "tools/list":
                result = self._handle_tools_list(params)
            elif method == "tools/call":
                result = self._handle_tools_call(params)
            elif method == "resources/list":
                result = self._handle_resources_list(params)
            elif method == "prompts/list":
                result = self._handle_prompts_list(params)
            else:
                return self._error_response(
                    request_id,
                    -32601,
                    f"Method not found: {method}"
                )

            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": result
            }

        except Exception as e:
            logger.error(f"Error handling MCP request {method}: {e}")
            return self._error_response(
                request_id,
                -32603,
                f"Internal error: {str(e)}"
            )

    def _error_response(self, request_id: Optional[Any], code: int, message: str) -> Dict[str, Any]:
        """Create a JSON-RPC error response."""
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": code,
                "message": message
            }
        }

    def _handle_notification(self, method: str, _params: Dict[str, Any]):
        """Handle notifications (no response)."""
        if method == "notifications/initialized":
            logger.info("MCP client initialized")
        elif method == "notifications/cancelled":
            logger.info("MCP request cancelled")
        else:
            logger.warning(f"Unknown MCP notification: {method}")

    def _handle_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle initialize method."""
        client_info = params.get("clientInfo", {})
        logger.info(f"MCP client connected: {client_info.get('name', 'unknown')}")

        return {
            "protocolVersion": self.protocol_version,
            "capabilities": {
                "tools": {},
                "resources": {},
                "prompts": {}
            },
            "serverInfo": self.server_info
        }

    def _handle_tools_list(self, _params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tools/list method - return all Genesis tools."""
        # Get all tools from Genesis tool registry
        tools = []
        for spec in tool_registry.get_all_specs():
            # Convert Genesis ToolSpec to MCP tool format
            properties = {}
            required = []

            for param in spec.parameters:
                properties[param.name] = {
                    "type": param.type,
                    "description": param.description
                }
                if param.required:
                    required.append(param.name)

            tools.append({
                "name": spec.name,
                "description": spec.description,
                "inputSchema": {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            })

        return {"tools": tools}

    def _handle_tools_call(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tools/call method - execute a Genesis tool."""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if not tool_name:
            raise ValueError("Tool name is required")

        logger.info(f"MCP tool call: {tool_name} with {arguments}")

        # Execute the tool via Genesis tool registry
        result = tool_registry.execute(tool_name, **arguments)

        if result["success"]:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": str(result["result"])
                    }
                ]
            }
        elif "permission_escalation" in result:
            # Tool requires elevated permission
            escalation = result["permission_escalation"]
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Permission required: {escalation['tool_description']}. "
                               f"Current: {escalation['current_level_name']}, "
                               f"Required: {escalation['required_level_name']}"
                    }
                ],
                "isError": True
            }
        else:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error: {result['error']}"
                    }
                ],
                "isError": True
            }

    def _handle_resources_list(self, _params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle resources/list method - Genesis doesn't expose resources yet."""
        return {"resources": []}

    def _handle_prompts_list(self, _params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle prompts/list method - Genesis doesn't expose prompts yet."""
        return {"prompts": []}


# Global server instance
_mcp_server: Optional[MCPServer] = None


def get_mcp_server() -> MCPServer:
    """Get or create the global MCP server instance."""
    global _mcp_server
    if _mcp_server is None:
        _mcp_server = MCPServer()
    return _mcp_server


async def handle_mcp_message(request: Request) -> JSONResponse:
    """Handle an MCP message request (HTTP endpoint).

    This is the entry point for HTTP/SSE transport.
    """
    try:
        request_data = await request.json()
        server = get_mcp_server()
        response_data = server.handle_request(request_data)

        if not response_data:
            # Notification, no response
            return JSONResponse(content={}, status_code=204)

        return JSONResponse(content=response_data)

    except Exception as e:
        logger.error(f"Error handling MCP message: {e}")
        return JSONResponse(
            content={
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32700,
                    "message": f"Parse error: {str(e)}"
                }
            },
            status_code=400
        )
