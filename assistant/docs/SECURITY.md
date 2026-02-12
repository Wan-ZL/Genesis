## Security Hardening Documentation

This document describes the security measures implemented in Genesis to protect against common vulnerabilities and attacks.

## Table of Contents

1. [Overview](#overview)
2. [Threat Model](#threat-model)
3. [Security Features](#security-features)
4. [Configuration](#configuration)
5. [Monitoring](#monitoring)
6. [Best Practices](#best-practices)

## Overview

Genesis implements defense-in-depth security with multiple layers:

- **Input Sanitization**: All user inputs are validated before processing
- **Sandboxed Execution**: Shell commands run in restricted environments
- **Rate Limiting**: Per-tool rate limits prevent abuse
- **Audit Logging**: All tool executions are logged for forensics
- **Trust Levels**: MCP servers are categorized by trust level
- **Security Headers**: HTTP responses include protective headers
- **Permission System**: Tools require explicit permission levels

## Threat Model

### Threats We Protect Against

| Threat | Mitigation |
|--------|-----------|
| **Command Injection** | Input sanitization, sandboxed execution |
| **Path Traversal** | Path validation, allowed directory checks |
| **SSRF (Server-Side Request Forgery)** | URL validation, private IP blocking |
| **Prompt Injection** | Output scanning, pattern detection |
| **Resource Exhaustion** | Rate limiting, timeout limits, output size limits |
| **Privilege Escalation** | Permission system, default-deny |
| **Malicious MCP Servers** | Trust levels, capability restrictions |
| **XSS/Clickjacking** | Security headers (CSP, X-Frame-Options) |

### Out of Scope

- **Physical access attacks**: Genesis assumes trusted physical environment
- **Social engineering**: User must not share credentials
- **Zero-day exploits**: We follow best practices but cannot prevent unknown vulnerabilities

## Security Features

### 1. Input Sanitization

All user inputs are sanitized before tool execution:

```python
from server.services.security import get_security_service

service = get_security_service()

# Shell command sanitization
command, is_safe = service.sanitize_shell_input("ls -la")
if not is_safe:
    raise ValueError("Unsafe command")

# File path validation
path, is_safe, error = service.validate_file_path(
    user_path,
    allowed_dirs=[Path("/allowed/dir")]
)

# URL validation (SSRF protection)
is_safe, error = service.validate_url(user_url)
```

**Blocked patterns:**
- Shell metacharacters: `; & | $ < > ( ) [ ] { } * ? ~`
- Dangerous commands: `rm -rf /`, fork bombs, `mkfs`, etc.
- Private IPs: 127.0.0.0/8, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16
- Sensitive files: `.env`, `secrets`, `.ssh`, credentials

### 2. Sandboxed Execution

Shell commands run in sandboxed environments:

```python
from server.services.sandbox import get_sandbox_executor, SandboxConfig

config = SandboxConfig(
    timeout=30,                    # Max execution time
    max_output_size=1024 * 1024,   # 1MB output limit
    working_directory=Path("/safe/dir"),
    use_macos_sandbox=True,        # Enable macOS sandbox-exec
)

sandbox = get_sandbox_executor(config)
result = sandbox.execute("ls -la")
```

**Sandbox protections:**
- Restricted environment variables (only safe PATH, HOME, USER, etc.)
- Working directory isolation
- Output size limits (prevents memory exhaustion)
- Execution timeouts (prevents CPU exhaustion)
- macOS `sandbox-exec` integration (denies network, IPC, hardware access)

**macOS Sandbox Profile:**
```scheme
(version 1)
(deny default)                    ; Default deny
(allow process-exec*)             ; Allow process execution
(allow file-read*)                ; Allow file reads
(allow file-write*                ; Allow writes only to temp
    (subpath "/tmp")
    (subpath "/var/tmp"))
(deny network*)                   ; Block all network
(deny system-socket)              ; Block system sockets
(deny ipc-posix*)                 ; Block IPC
(deny mach-lookup)                ; Block mach services
```

### 3. Rate Limiting

Per-tool rate limits prevent abuse and resource exhaustion:

```python
from server.services.rate_limiter import get_rate_limiter, RateLimitConfig

limiter = get_rate_limiter()

# Check rate limit before execution
allowed, retry_after, remaining = limiter.check_rate_limit("tool_name")
if not allowed:
    return f"Rate limited. Retry after {retry_after}s"
```

**Default limits:**

| Tool Category | Rate Limit | Burst |
|--------------|------------|-------|
| `run_shell_command` | 5/min | 2 |
| `web_fetch` | 30/min | 10 |
| File operations | 50/min | 10 |
| Calendar operations | 10-20/min | 3-5 |
| MCP tools | 20/min | 5 |
| Default (unknown tools) | 30/min | 10 |

**Custom limits:**
```python
limiter.set_limit("my_tool", RateLimitConfig(
    max_requests=10,
    window_seconds=60,
    burst=5
))
```

### 4. Audit Logging

All tool executions are logged to an append-only SQLite database:

```python
from server.services.audit import get_audit_logger

logger = get_audit_logger()

# Logs are written automatically by ToolRegistry.execute()
# Query logs via API: GET /api/audit
```

**Logged data:**
- Timestamp (ISO format)
- Tool name
- Arguments hash (SHA256, first 16 chars)
- Result summary (truncated to 200 chars)
- User IP address
- Success/failure status
- Execution duration (ms)
- Sandboxed flag
- Rate limited flag

**Privacy:** Argument values are hashed, not stored in plaintext.

**API endpoints:**
```bash
# Query logs
GET /api/audit?tool_name=web_fetch&success=true&limit=100

# Get statistics
GET /api/audit/stats
```

### 5. MCP Trust Levels

MCP servers are categorized by trust level:

| Level | Value | Permissions |
|-------|-------|-------------|
| **UNTRUSTED** | 0 | Read-only, no tool execution |
| **TRUSTED** | 1 | Can execute approved tools |
| **VERIFIED** | 2 | Full access, user explicitly verified |

**Configuration** (`settings.mcp_servers`):
```json
[
  {
    "name": "filesystem",
    "transport": "stdio",
    "command": ["npx", "@modelcontextprotocol/server-filesystem", "/allowed/path"],
    "trust_level": 2
  },
  {
    "name": "untrusted-server",
    "transport": "sse",
    "url": "http://external-server.com/mcp",
    "trust_level": 0
  }
]
```

**Trust level enforcement:**
- UNTRUSTED servers cannot execute tools (PermissionError)
- TRUSTED servers can execute tools (with rate limits and sandboxing)
- VERIFIED servers have full access (still subject to permission system)

### 6. Output Sanitization

Tool outputs are scanned for prompt injection attempts:

```python
from server.services.security import get_security_service

service = get_security_service()
sanitized, detected, patterns = service.detect_prompt_injection(output)

if detected:
    # Output will include warning and redacted patterns
    print(sanitized)
```

**Detected patterns:**
- "ignore previous instructions"
- "disregard all above"
- "system prompt"
- "you are now"
- "act as"
- "forget everything"
- Special tokens: `<|...|>`, `[INST]`, `<s>`, etc.

**Sanitized output format:**
```
[SECURITY WARNING: Potential prompt injection detected and sanitized. Matched 2 pattern(s)]

The original text with [REDACTED] replacing injection attempts.
```

### 7. Security Headers

All HTTP responses include security headers:

```http
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Strict-Transport-Security: max-age=31536000; includeSubDomains
Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: geolocation=(), microphone=(), camera=()
```

**Protection against:**
- MIME sniffing attacks
- Clickjacking
- XSS (reflected)
- Protocol downgrade
- Referrer leakage
- Unnecessary permissions (camera, microphone, geolocation)

### 8. Permission System

Tools require explicit permission levels (see `.claude/rules/07-assistant-core-capabilities.md`):

| Level | Value | Access |
|-------|-------|--------|
| SANDBOX | 0 | Only `assistant/memory/` |
| LOCAL | 1 | Entire Genesis project |
| SYSTEM | 2 | Execute system commands (restricted) |
| FULL | 3 | Complete computer access |

**Configure via environment:**
```bash
export ASSISTANT_PERMISSION_LEVEL=1  # LOCAL (default)
```

**Tool declarations:**
```python
from core.permissions import PermissionLevel

registry.register_tool(ToolSpec(
    name="read_file",
    required_permission=PermissionLevel.LOCAL,
    # ...
))
```

**Enforcement:**
- Tools check permission before execution
- Insufficient permission returns escalation request to user
- User can grant elevated permission via settings

## Configuration

### Environment Variables

```bash
# Permission level (0=SANDBOX, 1=LOCAL, 2=SYSTEM, 3=FULL)
ASSISTANT_PERMISSION_LEVEL=1

# Repository paths (colon-separated, for file tools)
REPOSITORY_PATHS=/path/to/genesis

# Max file size for read operations (bytes)
REPOSITORY_MAX_FILE_SIZE=1048576  # 1MB
```

### Settings (via API)

```bash
# Enable/disable MCP
PUT /api/settings
{
  "mcp_enabled": true,
  "mcp_servers": [...]
}
```

### Custom Rate Limits

```python
# In code or via settings extension
from server.services.rate_limiter import get_rate_limiter, RateLimitConfig

limiter = get_rate_limiter()
limiter.set_limit("my_custom_tool", RateLimitConfig(
    max_requests=100,
    window_seconds=60,
    burst=20
))
```

## Monitoring

### Audit Log Monitoring

```bash
# Check recent failures
curl http://localhost:8080/api/audit?success=false&limit=10

# Get statistics
curl http://localhost:8080/api/audit/stats

# Monitor specific tool
curl http://localhost:8080/api/audit?tool_name=run_shell_command&limit=50
```

### Alert Service Integration

Genesis Alert Service automatically monitors:
- Tool execution failures
- Rate limit violations
- Security warnings

Configure alerts via `/api/alerts` endpoints.

### Log Files

```
assistant/logs/assistant.log    # Main log
assistant/logs/error.log         # Errors only
assistant/memory/audit.db        # Audit log database
```

**Log rotation:** Logs rotate at 10MB, keep 5 backups.

## Best Practices

### For Developers

1. **Always sanitize user input** before passing to tools
2. **Use sandboxed execution** for any system command
3. **Set appropriate permission levels** for new tools (default-deny)
4. **Log sensitive operations** to audit log
5. **Test with malicious inputs** (see tests/test_security.py)
6. **Review audit logs** regularly for anomalies

### For Operators

1. **Set minimum required permission level** (prefer LOCAL over SYSTEM)
2. **Review MCP trust levels** before connecting new servers
3. **Monitor audit logs** for suspicious activity
4. **Configure rate limits** based on usage patterns
5. **Keep dependencies updated** (`pip install -U`)
6. **Enable authentication** in production (`/api/auth/set-password`)

### For MCP Server Integration

1. **Start with UNTRUSTED** trust level for new servers
2. **Verify server source code** before upgrading to TRUSTED
3. **Use VERIFIED** only for official/audited servers
4. **Limit stdio transport** to trusted servers (can execute arbitrary commands)
5. **Prefer SSE transport** for third-party servers (HTTP-only, no shell access)

## Security Checklist

Before deploying Genesis to production:

- [ ] Set `ASSISTANT_PERMISSION_LEVEL` to minimum required (1 or 2)
- [ ] Enable authentication (`/api/auth/set-password`)
- [ ] Review and configure MCP trust levels
- [ ] Set up monitoring for audit logs
- [ ] Configure appropriate rate limits
- [ ] Review security headers for your use case
- [ ] Test with penetration testing tools
- [ ] Keep dependencies updated
- [ ] Back up audit logs regularly
- [ ] Document custom security policies

## Vulnerability Reporting

If you discover a security vulnerability in Genesis:

1. **Do not** create a public GitHub issue
2. Email the maintainers directly (see CONTRIBUTING.md)
3. Include:
   - Vulnerability description
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

We aim to respond within 48 hours and patch critical vulnerabilities within 7 days.

## References

- OWASP Top 10: https://owasp.org/Top10/
- MCP Security Best Practices: https://spec.modelcontextprotocol.io/
- Python Security Guide: https://python.readthedocs.io/en/stable/library/security_warnings.html
- Sandboxing on macOS: `man sandbox-exec`

## Version History

- **2026-02-11**: Initial security hardening implementation (Issue #54)
  - Input/output sanitization
  - Sandboxed tool execution
  - Rate limiting
  - Audit logging
  - MCP trust levels
  - Security headers
