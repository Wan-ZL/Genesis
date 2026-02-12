# MCP (Model Context Protocol) Setup Guide

Genesis supports the Model Context Protocol (MCP), the emerging standard for AI agent-to-tool integration. This guide explains how to connect Genesis to external MCP servers and expose Genesis tools as an MCP server.

## Table of Contents

1. [Overview](#overview)
2. [Genesis as MCP Client](#genesis-as-mcp-client)
3. [Genesis as MCP Server](#genesis-as-mcp-server)
4. [Security and Permissions](#security-and-permissions)
5. [Troubleshooting](#troubleshooting)

## Overview

MCP (Model Context Protocol) is a universal standard for connecting AI agents to tools and data sources. It's supported by OpenAI, Google DeepMind, Anthropic, and has 1000+ community-built servers.

### Key Concepts

- **MCP Server**: Exposes tools (like database queries, file operations, API calls)
- **MCP Client**: Connects to servers and uses their tools (Genesis can be a client)
- **Transports**: stdio (subprocess) or SSE (HTTP with Server-Sent Events)
- **Tools**: Functions that the AI can call with specific inputs and outputs

### Genesis MCP Features

- **Client Mode**: Connect to external MCP servers and use their tools
- **Server Mode**: Expose Genesis tools to other AI agents
- **Tool Discovery**: Automatic integration of MCP tools into Genesis tool registry
- **Security**: Permission levels enforced for MCP tool execution
- **Multiple Transports**: Support for both stdio and SSE

## Genesis as MCP Client

Connect Genesis to external MCP servers to use their tools.

### Enable MCP

1. Open Genesis Settings UI
2. Navigate to Advanced Settings
3. Enable "MCP Support"
4. Save settings

Or via CLI:

```bash
python -m cli settings set mcp_enabled true
```

### Add an MCP Server (stdio transport)

**Example: Filesystem MCP Server**

```json
{
  "name": "filesystem",
  "transport": "stdio",
  "command": ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/path/to/allowed/directory"],
  "env": {}
}
```

Via API:

```bash
curl -X POST http://localhost:8080/api/mcp/servers \
  -H "Content-Type: application/json" \
  -d '{
    "name": "filesystem",
    "transport": "stdio",
    "command": ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/Users/yourname/Documents"],
    "env": {}
  }'
```

Via Settings UI:
1. Open Settings > MCP Servers
2. Click "Add Server"
3. Fill in name, transport type, and command
4. Click "Save"

### Add an MCP Server (SSE transport)

**Example: Remote MCP Server**

```json
{
  "name": "remote-api",
  "transport": "sse",
  "url": "https://mcp.example.com",
  "env": {
    "API_KEY": "your-api-key-here"
  }
}
```

Via API:

```bash
curl -X POST http://localhost:8080/api/mcp/servers \
  -H "Content-Type: application/json" \
  -d '{
    "name": "remote-api",
    "transport": "sse",
    "url": "https://mcp.example.com",
    "env": {"API_KEY": "your-key"}
  }'
```

### Connect to a Server

Servers are automatically connected on Genesis startup. To manually connect:

```bash
curl -X POST http://localhost:8080/api/mcp/servers/filesystem/connect
```

### List Available MCP Tools

Once connected, MCP tools appear in Genesis tool registry with the prefix `mcp:server_name:tool_name`.

```bash
# List all MCP tools
curl http://localhost:8080/api/mcp/tools

# Example response:
{
  "tools": [
    {
      "name": "read_file",
      "description": "Read contents of a file",
      "input_schema": {
        "type": "object",
        "properties": {
          "path": {"type": "string", "description": "File path"}
        },
        "required": ["path"]
      },
      "server_name": "filesystem"
    }
  ],
  "total": 1
}
```

### Use MCP Tools in Chat

MCP tools are automatically available to the AI:

**User**: "What's in my Documents folder?"

**AI**: (calls `mcp:filesystem:list_directory` tool) "Here are the files in your Documents folder: ..."

### Disconnect from a Server

```bash
curl -X POST http://localhost:8080/api/mcp/servers/filesystem/disconnect
```

### Remove a Server

```bash
curl -X DELETE http://localhost:8080/api/mcp/servers/filesystem
```

## Genesis as MCP Server

Expose Genesis tools to external AI agents via MCP.

### MCP Server Endpoint

Genesis automatically exposes an MCP server at:

```
POST http://localhost:8080/api/mcp/messages
```

This endpoint implements the MCP JSON-RPC 2.0 protocol.

### Connect an External Agent

From another AI agent or MCP client:

```python
import httpx
import json

# Initialize connection
response = httpx.post(
    "http://localhost:8080/api/mcp/messages",
    json={
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "clientInfo": {"name": "my-agent", "version": "1.0"}
        }
    }
)

print(response.json())
# {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2024-11-05", ...}}
```

### List Available Tools

```python
response = httpx.post(
    "http://localhost:8080/api/mcp/messages",
    json={
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {}
    }
)

tools = response.json()["result"]["tools"]
# Returns all Genesis tools: get_current_datetime, calculate, web_fetch, etc.
```

### Call a Tool

```python
response = httpx.post(
    "http://localhost:8080/api/mcp/messages",
    json={
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "calculate",
            "arguments": {"expression": "15 * 7"}
        }
    }
)

result = response.json()["result"]
# {"content": [{"type": "text", "text": "105"}]}
```

## Popular MCP Servers

### Official MCP Servers

1. **Filesystem** - Read/write local files
   ```bash
   npx -y @modelcontextprotocol/server-filesystem /path/to/directory
   ```

2. **Brave Search** - Web search via Brave API
   ```bash
   npx -y @modelcontextprotocol/server-brave-search
   ```
   Requires: `BRAVE_API_KEY` environment variable

3. **Google Drive** - Access Google Drive files
   ```bash
   npx -y @modelcontextprotocol/server-gdrive
   ```
   Requires: OAuth credentials

4. **Slack** - Send/receive Slack messages
   ```bash
   npx -y @modelcontextprotocol/server-slack
   ```
   Requires: Slack bot token

5. **PostgreSQL** - Query PostgreSQL databases
   ```bash
   npx -y @modelcontextprotocol/server-postgres
   ```
   Requires: Database connection string

### Community MCP Servers

See https://github.com/modelcontextprotocol/servers for 1000+ community-built servers.

## Security and Permissions

### MCP Tool Permissions

MCP tools in Genesis respect the permission system:

- All MCP tools require at least **LOCAL** permission level by default
- Tools that access sensitive resources may require **SYSTEM** permission
- Permission escalation prompts appear if needed

### Sandboxing MCP Servers

For stdio transport, MCP servers run as subprocesses with limited access:

1. **Environment Variables**: Only explicitly configured env vars are passed
2. **Working Directory**: Subprocesses run in Genesis root by default
3. **Network Access**: stdio servers can make network requests unless blocked

**Best Practice**: Use stdio transport for untrusted MCP servers, SSE for trusted ones.

### Authentication for MCP Server

To secure Genesis's MCP server endpoint:

1. Enable authentication in Genesis settings
2. External agents must include `Authorization: Bearer <token>` header
3. Use API keys or JWT tokens

### Restricting Tool Access

Create permission policies for specific MCP tools:

```python
# In custom Genesis configuration
MCP_TOOL_PERMISSIONS = {
    "mcp:filesystem:write_file": "SYSTEM",  # Requires SYSTEM permission
    "mcp:database:execute_sql": "FULL",     # Requires FULL permission
}
```

## Troubleshooting

### Server Won't Connect

**Issue**: `Failed to connect via stdio: [Errno 2] No such file or directory`

**Solution**: Verify the command path exists and is executable.

```bash
# Test command manually
npx -y @modelcontextprotocol/server-filesystem /tmp
```

**Issue**: `Connection refused` for SSE transport

**Solution**: Check if the remote server is running and accessible.

```bash
curl http://localhost:8080/health
```

### Tools Not Appearing

**Issue**: MCP server connects but tools don't appear

**Solution**:
1. Check server logs: `python -m cli logs tail`
2. Verify server is responding to `tools/list`
3. Restart Genesis: `supervisorctl restart assistant`

### Permission Errors

**Issue**: `Error: Tool requires SYSTEM permission`

**Solution**:
1. Open Settings > Permissions
2. Set permission level to required level (SYSTEM or FULL)
3. Re-try the operation

### Subprocess Timeout

**Issue**: stdio server subprocess hangs

**Solution**:
1. Check if server process is stuck: `ps aux | grep mcp`
2. Kill stuck processes: `pkill -f "server-filesystem"`
3. Restart Genesis

### Tool Call Failures

**Issue**: `Error calling MCP tool: RuntimeError: MCP error: ...`

**Solution**:
1. Check MCP server logs (usually stderr of subprocess)
2. Verify tool arguments match the input schema
3. Check network connectivity for SSE transport

## Advanced Configuration

### Custom MCP Server

Create your own MCP server in Python:

```python
# my_mcp_server.py
import json
import sys

def handle_request(request):
    method = request["method"]

    if method == "initialize":
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "my-server", "version": "1.0"}
        }

    elif method == "tools/list":
        return {
            "tools": [
                {
                    "name": "my_tool",
                    "description": "My custom tool",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "input": {"type": "string"}
                        }
                    }
                }
            ]
        }

    elif method == "tools/call":
        tool_name = request["params"]["name"]
        args = request["params"]["arguments"]
        # Execute tool logic here
        return {
            "content": [{"type": "text", "text": f"Result: {args}"}]
        }

# Main loop
for line in sys.stdin:
    request = json.loads(line)
    result = handle_request(request)
    response = {
        "jsonrpc": "2.0",
        "id": request.get("id"),
        "result": result
    }
    print(json.dumps(response), flush=True)
```

Run it:

```bash
python my_mcp_server.py
```

Add to Genesis:

```json
{
  "name": "my-server",
  "transport": "stdio",
  "command": ["python", "/path/to/my_mcp_server.py"],
  "env": {}
}
```

### Monitoring MCP Connections

```bash
# Check all server statuses
curl http://localhost:8080/api/mcp/servers

# Example response:
{
  "mcp_enabled": true,
  "servers": [
    {
      "name": "filesystem",
      "transport": "stdio",
      "connected": true,
      "tool_count": 5
    },
    {
      "name": "database",
      "transport": "sse",
      "connected": false,
      "tool_count": 0
    }
  ]
}
```

### MCP Server Discovery

Genesis automatically discovers MCP servers in common locations:

1. `~/.mcp/servers/` - User-installed MCP servers
2. `/usr/local/lib/mcp/servers/` - System-wide MCP servers
3. Environment variable `MCP_SERVER_PATH`

## Resources

- **MCP Specification**: https://spec.modelcontextprotocol.io/
- **Official MCP Servers**: https://github.com/modelcontextprotocol/servers
- **MCP Community**: https://github.com/modelcontextprotocol
- **Genesis MCP API Docs**: http://localhost:8080/docs#/mcp

## Support

For issues with MCP in Genesis:
1. Check logs: `python -m cli logs tail`
2. File an issue: https://github.com/yourusername/genesis/issues
3. MCP protocol issues: https://github.com/modelcontextprotocol/specification/issues
