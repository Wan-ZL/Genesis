"""Tests for MCP (Model Context Protocol) client and server functionality."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from server.services.mcp_client import (
    MCPClient,
    MCPClientManager,
    MCPServerConfig,
    MCPTool
)
from server.services.mcp_server import MCPServer, get_mcp_server
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ============================================================================
# MCPClient Tests
# ============================================================================

@pytest.fixture
def stdio_config():
    """Sample stdio transport configuration."""
    return MCPServerConfig(
        name="test-stdio",
        transport="stdio",
        command=["python", "-m", "test_server"],
        env={"TEST_VAR": "test_value"}
    )


@pytest.fixture
def sse_config():
    """Sample SSE transport configuration."""
    return MCPServerConfig(
        name="test-sse",
        transport="sse",
        url="http://localhost:8080"
    )


def test_mcp_server_config_creation():
    """Test MCPServerConfig dataclass creation."""
    config = MCPServerConfig(
        name="test",
        transport="stdio",
        command=["echo", "test"]
    )
    assert config.name == "test"
    assert config.transport == "stdio"
    assert config.command == ["echo", "test"]
    assert config.env == {}


def test_mcp_tool_creation():
    """Test MCPTool dataclass creation."""
    tool = MCPTool(
        name="test_tool",
        description="A test tool",
        input_schema={"type": "object"},
        server_name="test_server"
    )
    assert tool.name == "test_tool"
    assert tool.description == "A test tool"
    assert tool.server_name == "test_server"


@pytest.mark.asyncio
async def test_mcp_client_init(stdio_config):
    """Test MCPClient initialization."""
    client = MCPClient(stdio_config)
    assert client.config == stdio_config
    assert client.process is None
    assert not client.is_connected()
    assert len(client.tools) == 0


@pytest.mark.asyncio
async def test_mcp_client_connect_invalid_transport():
    """Test connecting with invalid transport type."""
    config = MCPServerConfig(name="test", transport="invalid")
    client = MCPClient(config)

    with pytest.raises(ValueError, match="Unsupported transport"):
        await client.connect()


@pytest.mark.asyncio
async def test_mcp_client_stdio_connect_no_command():
    """Test stdio connect without command fails."""
    config = MCPServerConfig(name="test", transport="stdio")
    client = MCPClient(config)

    with pytest.raises(ValueError, match="stdio transport requires command"):
        await client.connect()


@pytest.mark.asyncio
async def test_mcp_client_sse_connect_no_url():
    """Test SSE connect without URL fails."""
    config = MCPServerConfig(name="test", transport="sse")
    client = MCPClient(config)

    with pytest.raises(ValueError, match="sse transport requires url"):
        await client.connect()


@pytest.mark.asyncio
async def test_mcp_client_call_tool_not_connected(stdio_config):
    """Test calling tool when not connected fails."""
    client = MCPClient(stdio_config)

    with pytest.raises(RuntimeError, match="not connected"):
        await client.call_tool("test_tool", {})


@pytest.mark.asyncio
async def test_mcp_client_disconnect():
    """Test disconnecting MCP client."""
    config = MCPServerConfig(name="test", transport="stdio", command=["echo"])
    client = MCPClient(config)

    # Mock a connected state
    mock_process = MagicMock()
    mock_process.terminate = MagicMock()
    mock_process.wait = MagicMock()
    client.process = mock_process
    client._connected = True

    await client.disconnect()

    assert not client.is_connected()
    assert client.process is None
    mock_process.terminate.assert_called_once()


# ============================================================================
# MCPClientManager Tests
# ============================================================================

@pytest.fixture
def temp_db_path(tmp_path):
    """Temporary database path for testing."""
    return tmp_path / "test.db"


@pytest.mark.asyncio
async def test_mcp_manager_init(temp_db_path):
    """Test MCPClientManager initialization."""
    manager = MCPClientManager(temp_db_path)
    assert manager.db_path == temp_db_path
    assert len(manager.clients) == 0
    assert len(manager._configs) == 0


@pytest.mark.asyncio
async def test_mcp_manager_load_configs_disabled(temp_db_path):
    """Test loading configs when MCP is disabled."""
    from server.services.settings import SettingsService

    settings_service = SettingsService(temp_db_path)
    await settings_service.set("mcp_enabled", "false")

    manager = MCPClientManager(temp_db_path)
    await manager.load_configs_from_settings()

    assert len(manager._configs) == 0


@pytest.mark.asyncio
async def test_mcp_manager_load_configs_enabled(temp_db_path):
    """Test loading configs when MCP is enabled."""
    from server.services.settings import SettingsService

    settings_service = SettingsService(temp_db_path)
    await settings_service.set("mcp_enabled", "true")

    servers = [
        {
            "name": "server1",
            "transport": "stdio",
            "command": ["python", "-m", "server1"],
            "env": {}
        },
        {
            "name": "server2",
            "transport": "sse",
            "url": "http://localhost:8080",
            "env": {}
        }
    ]
    await settings_service.set("mcp_servers", json.dumps(servers))

    manager = MCPClientManager(temp_db_path)
    await manager.load_configs_from_settings()

    assert len(manager._configs) == 2
    assert manager._configs[0].name == "server1"
    assert manager._configs[1].name == "server2"


@pytest.mark.asyncio
async def test_mcp_manager_connect_server_not_found(temp_db_path):
    """Test connecting to non-existent server."""
    manager = MCPClientManager(temp_db_path)

    with pytest.raises(ValueError, match="not found"):
        await manager.connect_server("nonexistent")


@pytest.mark.asyncio
async def test_mcp_manager_disconnect_server(temp_db_path):
    """Test disconnecting from server."""
    manager = MCPClientManager(temp_db_path)

    # Add a mock client
    mock_client = AsyncMock()
    mock_client.disconnect = AsyncMock()
    manager.clients["test"] = mock_client

    await manager.disconnect_server("test")

    mock_client.disconnect.assert_called_once()
    assert "test" not in manager.clients


@pytest.mark.asyncio
async def test_mcp_manager_get_all_tools(temp_db_path):
    """Test getting all tools from connected servers."""
    manager = MCPClientManager(temp_db_path)

    # Add mock clients with tools
    # get_all_tools() calls client.list_tools() method
    mock_client1 = MagicMock()
    mock_client1.is_connected.return_value = True
    mock_client1.list_tools.return_value = [
        MCPTool("tool1", "desc1", {}, "server1"),
        MCPTool("tool2", "desc2", {}, "server1")
    ]

    mock_client2 = MagicMock()
    mock_client2.is_connected.return_value = True
    mock_client2.list_tools.return_value = [
        MCPTool("tool3", "desc3", {}, "server2")
    ]

    manager.clients["server1"] = mock_client1
    manager.clients["server2"] = mock_client2

    tools = manager.get_all_tools()

    # Verify list_tools was called
    mock_client1.list_tools.assert_called_once()
    mock_client2.list_tools.assert_called_once()

    assert len(tools) == 3
    assert tools[0].name == "tool1"
    assert tools[1].name == "tool2"
    assert tools[2].name == "tool3"


@pytest.mark.asyncio
async def test_mcp_manager_call_tool_not_found(temp_db_path):
    """Test calling non-existent tool."""
    manager = MCPClientManager(temp_db_path)

    with pytest.raises(ValueError, match="not found"):
        await manager.call_tool("nonexistent_tool", {})


@pytest.mark.asyncio
async def test_mcp_manager_get_server_status(temp_db_path):
    """Test getting server connection status."""
    manager = MCPClientManager(temp_db_path)

    # Add a config
    manager._configs = [
        MCPServerConfig(name="test", transport="stdio", command=["echo"])
    ]

    # Add a connected client
    mock_client = MagicMock()
    mock_client.is_connected.return_value = True
    mock_client.tools = [MCPTool("tool1", "desc", {}, "test")]
    manager.clients["test"] = mock_client

    status = manager.get_server_status()

    assert "test" in status
    assert status["test"]["configured"] is True
    assert status["test"]["connected"] is True
    assert status["test"]["tool_count"] == 1


# ============================================================================
# MCPServer Tests
# ============================================================================

def test_mcp_server_init():
    """Test MCPServer initialization."""
    server = MCPServer()
    assert server.permission_level == 0
    assert server.protocol_version == "2024-11-05"
    assert server.server_info["name"] == "genesis-mcp-server"


def test_mcp_server_handle_invalid_jsonrpc():
    """Test handling invalid JSON-RPC version."""
    server = MCPServer()
    request = {"jsonrpc": "1.0", "id": 1, "method": "test"}

    response = server.handle_request(request)

    assert "error" in response
    assert response["error"]["code"] == -32600


def test_mcp_server_handle_notification():
    """Test handling notifications (no response)."""
    server = MCPServer()
    request = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized"
    }

    response = server.handle_request(request)

    assert response == {}  # Notifications return empty dict


def test_mcp_server_handle_unknown_method():
    """Test handling unknown method."""
    server = MCPServer()
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "unknown_method"
    }

    response = server.handle_request(request)

    assert "error" in response
    assert response["error"]["code"] == -32601
    assert "not found" in response["error"]["message"]


def test_mcp_server_handle_initialize():
    """Test initialize method."""
    server = MCPServer()
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "clientInfo": {"name": "test-client", "version": "1.0"}
        }
    }

    response = server.handle_request(request)

    assert "result" in response
    assert response["result"]["protocolVersion"] == "2024-11-05"
    assert "capabilities" in response["result"]
    assert "serverInfo" in response["result"]


def test_mcp_server_handle_tools_list():
    """Test tools/list method."""
    server = MCPServer()
    request = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {}
    }

    response = server.handle_request(request)

    assert "result" in response
    assert "tools" in response["result"]
    # Should have Genesis tools
    assert len(response["result"]["tools"]) > 0


def test_mcp_server_handle_tools_call_success():
    """Test tools/call method with successful execution."""
    server = MCPServer()
    request = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "calculate",
            "arguments": {"expression": "2+2"}
        }
    }

    response = server.handle_request(request)

    assert "result" in response
    assert "content" in response["result"]
    assert response["result"]["content"][0]["type"] == "text"


def test_mcp_server_handle_tools_call_missing_name():
    """Test tools/call without tool name."""
    server = MCPServer()
    request = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {"arguments": {}}
    }

    response = server.handle_request(request)

    assert "error" in response
    assert response["error"]["code"] == -32603


def test_mcp_server_handle_resources_list():
    """Test resources/list method."""
    server = MCPServer()
    request = {
        "jsonrpc": "2.0",
        "id": 5,
        "method": "resources/list",
        "params": {}
    }

    response = server.handle_request(request)

    assert "result" in response
    assert "resources" in response["result"]
    assert len(response["result"]["resources"]) == 0  # Not implemented yet


def test_mcp_server_handle_prompts_list():
    """Test prompts/list method."""
    server = MCPServer()
    request = {
        "jsonrpc": "2.0",
        "id": 6,
        "method": "prompts/list",
        "params": {}
    }

    response = server.handle_request(request)

    assert "result" in response
    assert "prompts" in response["result"]
    assert len(response["result"]["prompts"]) == 0  # Not implemented yet


def test_get_mcp_server_singleton():
    """Test get_mcp_server returns singleton."""
    server1 = get_mcp_server()
    server2 = get_mcp_server()

    assert server1 is server2


# ============================================================================
# API Integration Tests
# ============================================================================

@pytest.fixture
def app_with_mcp():
    """FastAPI app with MCP routes for testing."""
    from server.routes import mcp as mcp_routes

    app = FastAPI()
    app.include_router(mcp_routes.router, prefix="/api")
    return app


@pytest.fixture
def client_with_mcp(app_with_mcp):
    """Test client with MCP routes."""
    return TestClient(app_with_mcp)


@pytest.mark.skip(reason="Requires injecting test database")
def test_list_mcp_servers_empty():
    """Test listing MCP servers when none are configured."""
    pass


def test_mcp_messages_endpoint(client_with_mcp):
    """Test MCP server messages endpoint."""
    response = client_with_mcp.post(
        "/api/mcp/messages",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "clientInfo": {"name": "test", "version": "1.0"}
            }
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert "result" in data
    assert data["result"]["protocolVersion"] == "2024-11-05"


def test_mcp_messages_endpoint_invalid_json(client_with_mcp):
    """Test MCP endpoint with invalid JSON."""
    response = client_with_mcp.post(
        "/api/mcp/messages",
        content="invalid json",
        headers={"Content-Type": "application/json"}
    )

    assert response.status_code == 400
    data = response.json()
    assert "error" in data


def test_mcp_messages_endpoint_tools_list(client_with_mcp):
    """Test listing tools via MCP endpoint."""
    response = client_with_mcp.post(
        "/api/mcp/messages",
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert "result" in data
    assert "tools" in data["result"]
    assert len(data["result"]["tools"]) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
