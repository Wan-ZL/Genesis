"""Capabilities and permissions API routes.

Exposes endpoints for:
- Viewing discovered system capabilities
- Getting/setting permission levels
- Refreshing capability scan
- Viewing permission audit log
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.capability_scanner import CapabilityScanner, CapabilityType
from core.permissions import PermissionLevel, get_permission_level, set_permission_level
from server.services.audit_log import AuditLogService
import config

logger = logging.getLogger(__name__)
router = APIRouter()

# Singleton scanner instance
_scanner: Optional[CapabilityScanner] = None

# Singleton audit log service
_audit_log: Optional[AuditLogService] = None


def get_scanner() -> CapabilityScanner:
    """Get or create the capability scanner singleton."""
    global _scanner
    if _scanner is None:
        _scanner = CapabilityScanner()
    return _scanner


def get_audit_log() -> AuditLogService:
    """Get or create the audit log service singleton."""
    global _audit_log
    if _audit_log is None:
        _audit_log = AuditLogService(config.DATABASE_PATH)
    return _audit_log


class CapabilityResponse(BaseModel):
    """Response for a single capability."""
    name: str
    type: str
    available: bool
    path: Optional[str] = None
    version: Optional[str] = None
    description: Optional[str] = None


class CapabilitiesResponse(BaseModel):
    """Response for capabilities listing."""
    capabilities: list[CapabilityResponse]
    total: int
    available: int
    summary: str


class PermissionResponse(BaseModel):
    """Response for permission level."""
    level: int
    name: str
    description: str


class SetPermissionRequest(BaseModel):
    """Request to change permission level."""
    level: int
    reason: Optional[str] = None


class AuditLogEntry(BaseModel):
    """A single audit log entry."""
    id: str
    timestamp: str
    old_level: int
    old_level_name: str
    new_level: int
    new_level_name: str
    source: str
    ip_address: Optional[str]
    user_agent: Optional[str]
    reason: Optional[str]
    change: str


class AuditLogResponse(BaseModel):
    """Response for audit log listing."""
    entries: list[AuditLogEntry]
    total: int
    limit: int
    offset: int


PERMISSION_DESCRIPTIONS = {
    PermissionLevel.SANDBOX: "Only access assistant/memory/ directory",
    PermissionLevel.LOCAL: "Access entire Genesis project",
    PermissionLevel.SYSTEM: "Execute system commands (restricted)",
    PermissionLevel.FULL: "Complete computer access",
}


@router.get("/capabilities", response_model=CapabilitiesResponse)
async def list_capabilities(
    available_only: bool = False,
    type_filter: Optional[str] = None
):
    """List all discovered capabilities.

    Args:
        available_only: If true, only return available capabilities
        type_filter: Filter by capability type (cli_tool, service, system, mcp_server)
    """
    scanner = get_scanner()

    # Get capabilities based on filters
    if available_only:
        caps = scanner.get_available()
    else:
        caps = scanner.capabilities

    # Filter by type if specified
    if type_filter:
        try:
            cap_type = CapabilityType(type_filter)
            caps = {k: v for k, v in caps.items() if v.type == cap_type}
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid type_filter. Must be one of: {[t.value for t in CapabilityType]}"
            )

    # Build response
    capability_list = [
        CapabilityResponse(
            name=cap.name,
            type=cap.type.value,
            available=cap.available,
            path=cap.path,
            version=cap.version,
            description=cap.description,
        )
        for cap in caps.values()
    ]

    return CapabilitiesResponse(
        capabilities=capability_list,
        total=len(scanner.capabilities),
        available=len(scanner.get_available()),
        summary=scanner.get_summary(),
    )


@router.post("/capabilities/refresh", response_model=CapabilitiesResponse)
async def refresh_capabilities():
    """Force a full rescan of all capabilities."""
    scanner = get_scanner()
    logger.info("Refreshing capability scan...")
    scanner.refresh()

    return CapabilitiesResponse(
        capabilities=[
            CapabilityResponse(
                name=cap.name,
                type=cap.type.value,
                available=cap.available,
                path=cap.path,
                version=cap.version,
                description=cap.description,
            )
            for cap in scanner.capabilities.values()
        ],
        total=len(scanner.capabilities),
        available=len(scanner.get_available()),
        summary=scanner.get_summary(),
    )


@router.get("/permissions", response_model=PermissionResponse)
async def get_permissions():
    """Get current permission level."""
    level = get_permission_level()
    return PermissionResponse(
        level=level.value,
        name=level.name,
        description=PERMISSION_DESCRIPTIONS[level],
    )


@router.get("/permissions/levels")
async def list_permission_levels():
    """List all available permission levels."""
    return {
        "levels": [
            {
                "level": pl.value,
                "name": pl.name,
                "description": PERMISSION_DESCRIPTIONS[pl],
            }
            for pl in PermissionLevel
        ]
    }


@router.post("/permissions", response_model=PermissionResponse)
async def update_permission(request: SetPermissionRequest, req: Request):
    """Update the permission level.

    Note: This changes the runtime permission level. For persistence,
    also update the settings via /api/settings endpoint.
    """
    try:
        new_level = PermissionLevel(request.level)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid permission level. Must be 0-3."
        )

    old_level = get_permission_level()
    set_permission_level(new_level)

    # Log the permission change to audit log
    audit_log = get_audit_log()
    client_ip = req.client.host if req.client else None
    user_agent = req.headers.get("user-agent")

    await audit_log.log_permission_change(
        old_level=old_level.value,
        old_level_name=old_level.name,
        new_level=new_level.value,
        new_level_name=new_level.name,
        source="api",
        ip_address=client_ip,
        user_agent=user_agent,
        reason=request.reason
    )

    logger.info(f"Permission level changed: {old_level.name} -> {new_level.name}")

    return PermissionResponse(
        level=new_level.value,
        name=new_level.name,
        description=PERMISSION_DESCRIPTIONS[new_level],
    )


@router.get("/permissions/audit", response_model=AuditLogResponse)
async def get_permission_audit_log(
    limit: int = 50,
    offset: int = 0,
    source: Optional[str] = None
):
    """Get permission change audit log.

    Args:
        limit: Maximum entries to return (default 50)
        offset: Pagination offset (default 0)
        source: Filter by change source ("api", "cli", "settings")
    """
    audit_log = get_audit_log()

    entries = await audit_log.get_audit_log(
        limit=limit,
        offset=offset,
        source_filter=source
    )
    total = await audit_log.get_audit_count(source_filter=source)

    return AuditLogResponse(
        entries=[AuditLogEntry(**entry) for entry in entries],
        total=total,
        limit=limit,
        offset=offset
    )
