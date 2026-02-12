"""MCP (Model Context Protocol) Client for connecting to external tool servers.

This module implements the MCP client specification, allowing Genesis to connect
to external MCP servers and use their tools.

MCP Protocol: https://spec.modelcontextprotocol.io/
"""

import json
import logging
import subprocess
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any
from pathlib import Path
import httpx

logger = logging.getLogger(__name__)


@dataclass
class MCPTool:
    """Represents a tool exposed by an MCP server."""
    name: str
    description: str
    input_schema: Dict[str, Any]
    server_name: str  # Which MCP server provides this tool


@dataclass
class MCPServerConfig:
    """Configuration for an MCP server connection."""
    name: str
    transport: str  # "stdio" or "sse"
    command: Optional[List[str]] = None  # For stdio transport
    url: Optional[str] = None  # For SSE transport
    env: Dict[str, str] = field(default_factory=dict)  # Environment variables


class MCPClient:
    """
    MCP Client implementation.

    Supports connecting to MCP servers via:
    - stdio transport (launch subprocess, communicate via stdin/stdout)
    - SSE transport (HTTP with Server-Sent Events)
    """

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self.process: Optional[subprocess.Popen] = None
        self.http_client: Optional[httpx.AsyncClient] = None
        self.tools: List[MCPTool] = []
        self._request_id = 0
        self._connected = False

    async def connect(self) -> Dict[str, Any]:
        """Connect to the MCP server and initialize capabilities.

        Returns:
            Server info including capabilities and protocol version
        """
        if self.config.transport == "stdio":
            return await self._connect_stdio()
        elif self.config.transport == "sse":
            return await self._connect_sse()
        else:
            raise ValueError(f"Unsupported transport: {self.config.transport}")

    async def _connect_stdio(self) -> Dict[str, Any]:
        """Connect via stdio transport (subprocess)."""
        if not self.config.command:
            raise ValueError("stdio transport requires command")

        try:
            # Launch subprocess
            self.process = subprocess.Popen(
                self.config.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={**self.config.env},
                text=True,
                bufsize=1
            )

            # Send initialize request
            response = await self._send_request_stdio("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "roots": {"listChanged": True}
                },
                "clientInfo": {
                    "name": "genesis",
                    "version": "0.1.0"
                }
            })

            # Send initialized notification
            await self._send_notification_stdio("notifications/initialized")

            # List available tools
            tools_response = await self._send_request_stdio("tools/list", {})
            self.tools = [
                MCPTool(
                    name=tool["name"],
                    description=tool.get("description", ""),
                    input_schema=tool.get("inputSchema", {}),
                    server_name=self.config.name
                )
                for tool in tools_response.get("tools", [])
            ]

            self._connected = True
            logger.info(f"MCP stdio client connected to {self.config.name}: {len(self.tools)} tools")
            return response

        except Exception as e:
            logger.error(f"Failed to connect via stdio: {e}")
            if self.process:
                self.process.kill()
                self.process = None
            raise

    async def _connect_sse(self) -> Dict[str, Any]:
        """Connect via SSE transport (HTTP)."""
        if not self.config.url:
            raise ValueError("sse transport requires url")

        try:
            self.http_client = httpx.AsyncClient(timeout=30.0)

            # Send initialize request
            response = await self._send_request_sse("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "genesis",
                    "version": "0.1.0"
                }
            })

            # List available tools
            tools_response = await self._send_request_sse("tools/list", {})
            self.tools = [
                MCPTool(
                    name=tool["name"],
                    description=tool.get("description", ""),
                    input_schema=tool.get("inputSchema", {}),
                    server_name=self.config.name
                )
                for tool in tools_response.get("tools", [])
            ]

            self._connected = True
            logger.info(f"MCP SSE client connected to {self.config.url}: {len(self.tools)} tools")
            return response

        except Exception as e:
            logger.error(f"Failed to connect via SSE: {e}")
            if self.http_client:
                await self.http_client.aclose()
                self.http_client = None
            raise

    async def disconnect(self):
        """Disconnect from the MCP server."""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None

        if self.http_client:
            await self.http_client.aclose()
            self.http_client = None

        self._connected = False
        logger.info(f"MCP client disconnected from {self.config.name}")

    def is_connected(self) -> bool:
        """Check if client is currently connected."""
        return self._connected

    def list_tools(self) -> List[MCPTool]:
        """Get list of tools available from this server."""
        return self.tools

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool on the MCP server.

        Args:
            tool_name: Name of the tool to call
            arguments: Arguments to pass to the tool

        Returns:
            Tool execution result
        """
        if not self._connected:
            raise RuntimeError("MCP client not connected")

        if self.config.transport == "stdio":
            return await self._send_request_stdio("tools/call", {
                "name": tool_name,
                "arguments": arguments
            })
        else:
            return await self._send_request_sse("tools/call", {
                "name": tool_name,
                "arguments": arguments
            })

    async def _send_request_stdio(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Send JSON-RPC request via stdio."""
        if not self.process or not self.process.stdin or not self.process.stdout:
            raise RuntimeError("Process not running")

        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params
        }

        # Send request
        self.process.stdin.write(json.dumps(request) + "\n")
        self.process.stdin.flush()

        # Read response
        response_line = self.process.stdout.readline()
        if not response_line:
            raise RuntimeError("No response from MCP server")

        response = json.loads(response_line)

        if "error" in response:
            raise RuntimeError(f"MCP error: {response['error']}")

        return response.get("result", {})

    async def _send_notification_stdio(self, method: str, params: Optional[Dict[str, Any]] = None):
        """Send JSON-RPC notification via stdio (no response expected)."""
        if not self.process or not self.process.stdin:
            raise RuntimeError("Process not running")

        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {}
        }

        self.process.stdin.write(json.dumps(notification) + "\n")
        self.process.stdin.flush()

    async def _send_request_sse(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Send JSON-RPC request via SSE/HTTP."""
        if not self.http_client:
            raise RuntimeError("HTTP client not initialized")

        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params
        }

        response = await self.http_client.post(
            f"{self.config.url}/messages",
            json=request,
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()

        result = response.json()

        if "error" in result:
            raise RuntimeError(f"MCP error: {result['error']}")

        return result.get("result", {})


class MCPClientManager:
    """
    Manages multiple MCP server connections.

    Handles connecting, disconnecting, and routing tool calls
    to the appropriate MCP server.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.clients: Dict[str, MCPClient] = {}
        self._configs: List[MCPServerConfig] = []

    async def load_configs_from_settings(self):
        """Load MCP server configurations from settings database."""
        # Import here to avoid circular dependency
        from server.services.settings import SettingsService

        settings_service = SettingsService(self.db_path)
        settings = await settings_service.get_all()

        mcp_enabled = settings.get("mcp_enabled", False)
        if not mcp_enabled:
            logger.info("MCP support is disabled in settings")
            return

        mcp_servers_json = settings.get("mcp_servers", "[]")
        try:
            servers = json.loads(mcp_servers_json)
            self._configs = [
                MCPServerConfig(
                    name=s["name"],
                    transport=s["transport"],
                    command=s.get("command"),
                    url=s.get("url"),
                    env=s.get("env", {})
                )
                for s in servers
            ]
            logger.info(f"Loaded {len(self._configs)} MCP server configs")
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to parse MCP server configs: {e}")

    async def connect_server(self, name: str) -> Dict[str, Any]:
        """Connect to a specific MCP server.

        Args:
            name: Name of the MCP server to connect to

        Returns:
            Server info
        """
        config = next((c for c in self._configs if c.name == name), None)
        if not config:
            raise ValueError(f"MCP server '{name}' not found in configs")

        if name in self.clients:
            if self.clients[name].is_connected():
                logger.warning(f"MCP server '{name}' already connected")
                return {}
            else:
                # Remove disconnected client
                del self.clients[name]

        client = MCPClient(config)
        server_info = await client.connect()
        self.clients[name] = client

        return server_info

    async def disconnect_server(self, name: str):
        """Disconnect from a specific MCP server."""
        if name in self.clients:
            await self.clients[name].disconnect()
            del self.clients[name]

    async def connect_all(self):
        """Connect to all configured MCP servers."""
        for config in self._configs:
            try:
                await self.connect_server(config.name)
            except Exception as e:
                logger.error(f"Failed to connect to MCP server '{config.name}': {e}")

    async def disconnect_all(self):
        """Disconnect from all MCP servers."""
        for name in list(self.clients.keys()):
            try:
                await self.disconnect_server(name)
            except Exception as e:
                logger.error(f"Failed to disconnect from '{name}': {e}")

    def get_all_tools(self) -> List[MCPTool]:
        """Get list of all tools from all connected MCP servers."""
        tools = []
        for client in self.clients.values():
            if client.is_connected():
                tools.extend(client.list_tools())
        return tools

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool on the appropriate MCP server.

        Args:
            tool_name: Name of the tool (may include server prefix like "server:tool")
            arguments: Arguments to pass to the tool

        Returns:
            Tool execution result
        """
        # Find which server provides this tool
        for client in self.clients.values():
            if client.is_connected():
                for tool in client.tools:
                    if tool.name == tool_name:
                        return await client.call_tool(tool_name, arguments)

        raise ValueError(f"MCP tool '{tool_name}' not found")

    def get_server_status(self) -> Dict[str, Dict[str, Any]]:
        """Get connection status for all configured servers."""
        status = {}
        for config in self._configs:
            client = self.clients.get(config.name)
            status[config.name] = {
                "configured": True,
                "connected": client.is_connected() if client else False,
                "transport": config.transport,
                "tool_count": len(client.tools) if client and client.is_connected() else 0
            }
        return status


# Global manager instance
_mcp_manager: Optional[MCPClientManager] = None


def get_mcp_manager(db_path: Optional[Path] = None) -> MCPClientManager:
    """Get or create the global MCP manager instance."""
    global _mcp_manager
    if _mcp_manager is None:
        if db_path is None:
            import config
            db_path = config.DATABASE_PATH
        _mcp_manager = MCPClientManager(db_path)
    return _mcp_manager
