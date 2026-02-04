"""Authentication API routes."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from server.services.auth import AuthService, AuthConfig, get_auth_service


router = APIRouter()
security = HTTPBearer(auto_error=False)


class LoginRequest(BaseModel):
    """Login request body."""
    username: str
    password: str


class LoginResponse(BaseModel):
    """Login response body."""
    success: bool
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None  # seconds
    token_type: str = "Bearer"
    error: Optional[str] = None


class RefreshRequest(BaseModel):
    """Refresh token request body."""
    refresh_token: str


class AuthStatusResponse(BaseModel):
    """Auth status response."""
    auth_enabled: bool
    auth_configured: bool
    username: str
    logged_in: bool = False
    expires_at: Optional[str] = None
    sessions: list = []


def get_client_ip(request: Request) -> str:
    """Extract client IP from request."""
    # Check for forwarded headers (reverse proxy)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def get_user_agent(request: Request) -> str:
    """Extract user agent from request."""
    return request.headers.get("User-Agent", "unknown")[:200]


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    auth_service: AuthService = Depends(get_auth_service)
) -> Optional[str]:
    """
    Dependency that extracts and validates the current user from JWT.
    Returns username if authenticated, None otherwise.
    """
    if not auth_service.is_auth_enabled():
        # Auth disabled - treat as authenticated
        return "local"

    if not credentials:
        return None

    valid, payload, error = await auth_service.verify_token(credentials.credentials)
    if not valid or not payload:
        return None

    return payload.get("sub")


async def require_auth(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    auth_service: AuthService = Depends(get_auth_service)
) -> str:
    """
    Dependency that requires authentication.
    Raises 401 if not authenticated.
    """
    if not auth_service.is_auth_enabled():
        # Auth disabled - treat as authenticated
        return "local"

    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"}
        )

    valid, payload, error = await auth_service.verify_token(credentials.credentials)
    if not valid or not payload:
        raise HTTPException(
            status_code=401,
            detail=error or "Invalid authentication",
            headers={"WWW-Authenticate": "Bearer"}
        )

    return payload.get("sub")


@router.get("/auth/status")
async def get_auth_status(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    auth_service: AuthService = Depends(get_auth_service)
) -> AuthStatusResponse:
    """Get authentication status."""
    auth_enabled = auth_service.is_auth_enabled()
    password_hash = await auth_service.get_password_hash()
    auth_configured = bool(password_hash)

    logged_in = False
    expires_at = None
    sessions = []

    if credentials:
        valid, payload, _ = await auth_service.verify_token(credentials.credentials)
        if valid and payload:
            logged_in = True
            exp = payload.get("exp")
            if exp:
                expires_at = datetime.fromtimestamp(exp, timezone.utc).isoformat()
            # Get active sessions for the user
            username = payload.get("sub", "")
            if username:
                sessions = await auth_service.get_active_sessions(username)

    return AuthStatusResponse(
        auth_enabled=auth_enabled,
        auth_configured=auth_configured,
        username=AuthConfig.get_username(),
        logged_in=logged_in,
        expires_at=expires_at,
        sessions=sessions
    )


@router.post("/auth/login")
async def login(
    request: Request,
    body: LoginRequest,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service)
) -> LoginResponse:
    """
    Authenticate and receive JWT tokens.

    Returns access_token for API calls and refresh_token for getting new access tokens.
    """
    if not auth_service.is_auth_enabled():
        return LoginResponse(
            success=False,
            error="Authentication is disabled. Enable with ASSISTANT_AUTH_ENABLED=true"
        )

    ip_address = get_client_ip(request)
    user_agent = get_user_agent(request)

    # Authenticate
    success, error = await auth_service.authenticate(
        body.username, body.password, ip_address
    )

    if not success:
        return LoginResponse(success=False, error=error)

    # Create tokens
    access_token = await auth_service.create_access_token(
        body.username, ip_address, user_agent
    )
    refresh_token = await auth_service.create_refresh_token(
        body.username, ip_address, user_agent
    )

    # Set secure cookie for refresh token (optional, for browser clients)
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=True,  # Requires HTTPS
        samesite="strict",
        max_age=AuthConfig.get_refresh_token_expire_days() * 24 * 60 * 60
    )

    return LoginResponse(
        success=True,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=AuthConfig.get_token_expire_minutes() * 60
    )


@router.post("/auth/refresh")
async def refresh_tokens(
    request: Request,
    body: Optional[RefreshRequest] = None,
    auth_service: AuthService = Depends(get_auth_service)
) -> LoginResponse:
    """
    Get new access token using refresh token.

    Refresh token can be in request body or cookie.
    """
    if not auth_service.is_auth_enabled():
        return LoginResponse(
            success=False,
            error="Authentication is disabled"
        )

    # Get refresh token from body or cookie
    refresh_token = None
    if body and body.refresh_token:
        refresh_token = body.refresh_token
    else:
        refresh_token = request.cookies.get("refresh_token")

    if not refresh_token:
        return LoginResponse(
            success=False,
            error="Refresh token required"
        )

    # Verify refresh token
    valid, payload, error = await auth_service.verify_token(refresh_token)
    if not valid or not payload:
        return LoginResponse(success=False, error=error or "Invalid refresh token")

    # Check token type
    if payload.get("type") != "refresh":
        return LoginResponse(success=False, error="Invalid token type")

    # Create new access token
    username = payload.get("sub", "")
    ip_address = get_client_ip(request)
    user_agent = get_user_agent(request)

    access_token = await auth_service.create_access_token(
        username, ip_address, user_agent
    )

    return LoginResponse(
        success=True,
        access_token=access_token,
        expires_in=AuthConfig.get_token_expire_minutes() * 60
    )


@router.post("/auth/logout")
async def logout(
    request: Request,
    response: Response,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Logout and revoke current token.
    """
    if not auth_service.is_auth_enabled():
        return {"success": True, "message": "Authentication is disabled"}

    # Revoke access token if provided
    if credentials:
        await auth_service.revoke_token(credentials.credentials)

    # Revoke refresh token from cookie if present
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        await auth_service.revoke_token(refresh_token)

    # Clear refresh token cookie
    response.delete_cookie(
        key="refresh_token",
        httponly=True,
        secure=True,
        samesite="strict"
    )

    return {"success": True, "message": "Logged out successfully"}


@router.post("/auth/logout-all")
async def logout_all(
    username: str = Depends(require_auth),
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Revoke all sessions for the current user.
    """
    if not auth_service.is_auth_enabled():
        return {"success": True, "message": "Authentication is disabled"}

    await auth_service.revoke_all_sessions(username)
    return {"success": True, "message": "All sessions revoked"}


@router.post("/auth/set-password")
async def set_password(
    request: Request,
    body: dict,
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Set the initial password (only works if no password is set).

    For subsequent password changes, authentication is required.
    """
    password = body.get("password")
    if not password or len(password) < 8:
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 8 characters"
        )

    # Check if password is already set
    existing_hash = await auth_service.get_password_hash()
    if existing_hash:
        raise HTTPException(
            status_code=403,
            detail="Password already set. Use change-password endpoint."
        )

    await auth_service.set_password(password)

    return {"success": True, "message": "Password set successfully"}


@router.post("/auth/change-password")
async def change_password(
    request: Request,
    body: dict,
    username: str = Depends(require_auth),
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Change password (requires authentication).
    """
    current_password = body.get("current_password")
    new_password = body.get("new_password")

    if not current_password or not new_password:
        raise HTTPException(
            status_code=400,
            detail="Both current_password and new_password required"
        )

    if len(new_password) < 8:
        raise HTTPException(
            status_code=400,
            detail="New password must be at least 8 characters"
        )

    # Verify current password
    ip_address = get_client_ip(request)
    success, error = await auth_service.authenticate(
        username, current_password, ip_address
    )
    if not success:
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    # Set new password
    await auth_service.set_password(new_password)

    # Revoke all other sessions (optional security measure)
    await auth_service.revoke_all_sessions(username)

    return {"success": True, "message": "Password changed. Please log in again."}
