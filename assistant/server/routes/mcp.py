"""MCP API routes for managing MCP server connections and tool calls."""

import json
import logging
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Request

import config
from server.services.mcp_client import get_mcp_manager
from server.services.mcp_server import handle_mcp_message
from server.services.settings import SettingsService

router = APIRouter()
logger = logging.getLogger(__name__)

# Initialize services
settings_service = SettingsService(config.DATABASE_PATH)


class MCPServerConfigRequest(BaseModel):
    """Request model for adding/updating MCP server configuration."""
    name: str = Field(..., description="Server name (unique identifier)")
    transport: str = Field(..., description="Transport type: 'stdio' or 'sse'")
    command: Optional[List[str]] = Field(None, description="Command for stdio transport")
    url: Optional[str] = Field(None, description="URL for SSE transport")
    env: Dict[str, str] = Field(default_factory=dict, description="Environment variables")


class MCPToolCallRequest(BaseModel):
    """Request model for calling an MCP tool."""
    tool_name: str = Field(..., description="Name of the tool to call")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Tool arguments")


@router.get("/mcp/servers")
async def list_mcp_servers():
    """List all configured MCP servers.

    Returns:
        List of MCP server configurations and their connection status
    """
    try:
        # Get configured servers from settings
        settings = await settings_service.get_all()
        mcp_enabled = settings.get("mcp_enabled", False)
        mcp_servers_json = settings.get("mcp_servers", "[]")

        servers = []
        try:
            servers = json.loads(mcp_servers_json)
        except json.JSONDecodeError:
            logger.error("Failed to parse mcp_servers JSON")

        # Get connection status from manager
        manager = get_mcp_manager()
        await manager.load_configs_from_settings()
        status = manager.get_server_status()

        # Merge config with status
        result = []
        for server in servers:
            name = server["name"]
            result.append({
                **server,
                "connected": status.get(name, {}).get("connected", False),
                "tool_count": status.get(name, {}).get("tool_count", 0)
            })

        return {
            "mcp_enabled": mcp_enabled,
            "servers": result
        }

    except Exception as e:
        logger.error(f"Error listing MCP servers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mcp/servers")
async def add_mcp_server(config_req: MCPServerConfigRequest):
    """Add a new MCP server configuration.

    Args:
        config_req: MCP server configuration

    Returns:
        Success message with updated server list
    """
    try:
        # Validate transport-specific requirements
        if config_req.transport == "stdio" and not config_req.command:
            raise HTTPException(
                status_code=400,
                detail="stdio transport requires 'command'"
            )
        if config_req.transport == "sse" and not config_req.url:
            raise HTTPException(
                status_code=400,
                detail="sse transport requires 'url'"
            )

        # Get current servers
        settings = await settings_service.get_all()
        mcp_servers_json = settings.get("mcp_servers", "[]")
        servers = json.loads(mcp_servers_json)

        # Check if name already exists
        if any(s["name"] == config_req.name for s in servers):
            raise HTTPException(
                status_code=409,
                detail=f"Server '{config_req.name}' already exists"
            )

        # Add new server
        servers.append({
            "name": config_req.name,
            "transport": config_req.transport,
            "command": config_req.command,
            "url": config_req.url,
            "env": config_req.env
        })

        # Save to settings
        await settings_service.set("mcp_servers", json.dumps(servers))

        # Reload manager configs
        manager = get_mcp_manager()
        await manager.load_configs_from_settings()

        return {
            "success": True,
            "message": f"MCP server '{config_req.name}' added successfully",
            "server_count": len(servers)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding MCP server: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/mcp/servers/{name}")
async def remove_mcp_server(name: str):
    """Remove an MCP server configuration.

    Args:
        name: Name of the server to remove

    Returns:
        Success message
    """
    try:
        # Disconnect if connected
        manager = get_mcp_manager()
        await manager.disconnect_server(name)

        # Get current servers
        settings = await settings_service.get_all()
        mcp_servers_json = settings.get("mcp_servers", "[]")
        servers = json.loads(mcp_servers_json)

        # Remove server
        servers = [s for s in servers if s["name"] != name]

        # Save to settings
        await settings_service.set("mcp_servers", json.dumps(servers))

        # Reload manager configs
        await manager.load_configs_from_settings()

        return {
            "success": True,
            "message": f"MCP server '{name}' removed successfully"
        }

    except Exception as e:
        logger.error(f"Error removing MCP server: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/mcp/servers/{name}/status")
async def get_server_status(name: str):
    """Get connection status for a specific MCP server.

    Args:
        name: Name of the server

    Returns:
        Server connection status and tool count
    """
    try:
        manager = get_mcp_manager()
        await manager.load_configs_from_settings()
        status = manager.get_server_status()

        if name not in status:
            raise HTTPException(status_code=404, detail=f"Server '{name}' not found")

        return status[name]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting server status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mcp/servers/{name}/connect")
async def connect_server(name: str):
    """Connect to a specific MCP server.

    Args:
        name: Name of the server to connect to

    Returns:
        Server info and connection status
    """
    try:
        manager = get_mcp_manager()
        await manager.load_configs_from_settings()

        server_info = await manager.connect_server(name)

        return {
            "success": True,
            "message": f"Connected to MCP server '{name}'",
            "server_info": server_info
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error connecting to MCP server: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mcp/servers/{name}/disconnect")
async def disconnect_server(name: str):
    """Disconnect from a specific MCP server.

    Args:
        name: Name of the server to disconnect from

    Returns:
        Success message
    """
    try:
        manager = get_mcp_manager()
        await manager.disconnect_server(name)

        return {
            "success": True,
            "message": f"Disconnected from MCP server '{name}'"
        }

    except Exception as e:
        logger.error(f"Error disconnecting from MCP server: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/mcp/tools")
async def list_mcp_tools():
    """List all tools available from connected MCP servers.

    Returns:
        List of MCP tools with their schemas
    """
    try:
        manager = get_mcp_manager()
        await manager.load_configs_from_settings()

        tools = manager.get_all_tools()

        return {
            "tools": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.input_schema,
                    "server_name": tool.server_name
                }
                for tool in tools
            ],
            "total": len(tools)
        }

    except Exception as e:
        logger.error(f"Error listing MCP tools: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mcp/tools/{tool_name}/call")
async def call_mcp_tool(tool_name: str, request: MCPToolCallRequest):
    """Call a tool from a connected MCP server.

    Args:
        tool_name: Name of the tool to call
        request: Tool arguments

    Returns:
        Tool execution result
    """
    try:
        manager = get_mcp_manager()
        await manager.load_configs_from_settings()

        result = await manager.call_tool(tool_name, request.arguments)

        return {
            "success": True,
            "result": result
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error calling MCP tool: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mcp/messages")
async def mcp_server_endpoint(request: Request):
    """MCP server endpoint for external agents to call Genesis tools.

    This endpoint implements the MCP protocol, allowing external AI agents
    to discover and use Genesis tools.

    Spec: https://spec.modelcontextprotocol.io/
    """
    return await handle_mcp_message(request)
