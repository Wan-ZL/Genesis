"""AI Assistant - FastAPI main entry point."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
import time

import config
from server.services.logging_service import configure_logging, get_logging_service

# Configure logging with rotation
log_dir = config.BASE_DIR / "logs"
logging_service = configure_logging(log_dir)
logger = logging.getLogger(__name__)

# Get access logger for HTTP request logging
access_logger = logging_service.get_access_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info(f"Starting AI Assistant on {config.HOST}:{config.PORT}")

    # Load user settings from database (API keys, model selection)
    # This restores settings saved in previous sessions
    from server.routes.settings import load_settings_on_startup
    await load_settings_on_startup()

    # Check encryption health at startup (logs single warning if issues found)
    from server.services.settings import SettingsService
    settings_service = SettingsService(config.DATABASE_PATH)
    await settings_service.check_encryption_health()

    # Scan for available capabilities (tools, services, etc.)
    from core.capability_scanner import CapabilityScanner
    from core.permissions import get_permission_level
    from server.services.tool_suggestions import get_suggestion_service
    scanner = CapabilityScanner()
    scanner.scan_all()
    available_count = len(scanner.get_available())
    total_count = len(scanner.capabilities)
    logger.info(f"Capability scan complete: {available_count}/{total_count} available")
    logger.info(f"Permission level: {get_permission_level().name}")

    # Initialize tool suggestion service with discovered capabilities
    suggestion_service = get_suggestion_service(scanner.capabilities)
    logger.info("Tool suggestion service initialized")

    # Initialize alert service for error monitoring
    from server.routes.alerts import init_alert_service
    init_alert_service()
    logger.info("Alert service initialized")

    # Initialize audit logging
    from server.services.audit import get_audit_logger
    get_audit_logger()
    logger.info("Audit logging initialized")

    # Initialize and start scheduler service
    from server.routes.schedule import init_scheduler
    await init_scheduler()
    logger.info("Scheduler service started")

    # Initialize and start proactive service
    from server.routes.notifications import init_proactive
    await init_proactive()
    logger.info("Proactive service started")

    # Initialize push notification service
    from server.routes.push import init_push
    init_push()
    logger.info("Push notification service initialized")

    # Initialize degradation service and check actual Ollama availability
    from server.services.degradation import get_degradation_service
    degradation_svc = get_degradation_service()
    await degradation_svc.initialize_ollama_status()
    logger.info("Degradation service initialized with actual Ollama status")

    # Initialize and start Telegram bot service if configured
    from server.services.telegram import get_telegram_service
    telegram_svc = await get_telegram_service()
    if telegram_svc:
        try:
            await telegram_svc.start()
            logger.info("Telegram bot service started")
        except Exception as e:
            logger.error(f"Failed to start Telegram bot: {e}", exc_info=True)
    else:
        logger.info("Telegram bot not configured, skipping")

    # Initialize MCP client manager and connect to configured servers
    from server.services.mcp_client import get_mcp_manager
    from server.services.tools import register_mcp_tools_from_manager
    mcp_manager = get_mcp_manager()
    try:
        await mcp_manager.load_configs_from_settings()
        await mcp_manager.connect_all()
        register_mcp_tools_from_manager()
        tool_count = len(mcp_manager.get_all_tools())
        if tool_count > 0:
            logger.info(f"MCP client initialized: {tool_count} tools from {len(mcp_manager.clients)} server(s)")
        else:
            logger.info("MCP client ready (no servers connected)")
    except Exception as e:
        logger.error(f"Failed to initialize MCP client: {e}", exc_info=True)

    logger.info(f"Using model: {config.MODEL}")
    if not config.OPENAI_API_KEY and not config.ANTHROPIC_API_KEY:
        logger.warning("No API key set - configure via Settings page or .env files")
    yield
    # Stop scheduler on shutdown
    from server.routes.schedule import stop_scheduler
    await stop_scheduler()
    # Stop proactive service on shutdown
    from server.routes.notifications import stop_proactive
    await stop_proactive()
    # Stop Telegram bot on shutdown
    from server.services.telegram import get_telegram_service
    telegram_svc = await get_telegram_service()
    if telegram_svc:
        await telegram_svc.stop()
    # Disconnect all MCP clients on shutdown
    from server.services.mcp_client import get_mcp_manager
    mcp_manager = get_mcp_manager()
    await mcp_manager.disconnect_all()
    logger.info("Shutting down AI Assistant")


app = FastAPI(
    title="AI Assistant",
    description="Always-on multimodal AI assistant",
    version="0.1.0",
    lifespan=lifespan
)

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Add security headers to all responses."""
    response = await call_next(request)

    # Security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

    return response


@app.middleware("http")
async def access_log_middleware(request: Request, call_next):
    """Log all HTTP requests to access.log."""
    start_time = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start_time) * 1000

    # Log format: IP METHOD PATH STATUS DURATION_MS
    access_logger.info(
        f'{request.client.host if request.client else "-"} '
        f'{request.method} {request.url.path} '
        f'{response.status_code} {duration_ms:.1f}ms'
    )
    return response


# Routes that don't require authentication
PUBLIC_PATHS = {
    "/",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/api/health",
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/refresh",
    "/api/auth/status",
    "/api/auth/set-password",
}

# Path prefixes that are public
PUBLIC_PREFIXES = ("/static/",)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Enforce authentication on protected routes when auth is enabled."""
    from fastapi.responses import JSONResponse
    from server.services.auth import get_auth_service

    path = request.url.path
    auth_service = get_auth_service()

    # Skip auth check if auth is disabled
    if not auth_service.is_auth_enabled():
        return await call_next(request)

    # Skip auth for public paths
    if path in PUBLIC_PATHS or any(path.startswith(p) for p in PUBLIC_PREFIXES):
        return await call_next(request)

    # Extract token from Authorization header
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return JSONResponse(
            status_code=401,
            content={"detail": "Not authenticated"},
            headers={"WWW-Authenticate": "Bearer"}
        )

    token = auth_header[7:]  # Remove "Bearer " prefix
    valid, payload, error = await auth_service.verify_token(token)

    if not valid:
        return JSONResponse(
            status_code=401,
            content={"detail": error or "Invalid authentication"},
            headers={"WWW-Authenticate": "Bearer"}
        )

    # Token is valid, proceed
    return await call_next(request)


# Import and include routers
from server.routes import chat, status, upload, metrics, settings, capabilities, alerts, resources, degradation, auth, schedule, persona, notifications, push, memory_facts, user_profile, mcp, audit

# Auth routes (always accessible)
app.include_router(auth.router, prefix="/api", tags=["auth"])

# Protected API routes
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(status.router, prefix="/api", tags=["status"])
app.include_router(upload.router, prefix="/api", tags=["upload"])
app.include_router(metrics.router, prefix="/api", tags=["metrics"])
app.include_router(settings.router, prefix="/api", tags=["settings"])
app.include_router(capabilities.router, prefix="/api", tags=["capabilities"])
app.include_router(alerts.router, prefix="/api", tags=["alerts"])
app.include_router(resources.router, prefix="/api", tags=["resources"])
app.include_router(degradation.router, prefix="/api", tags=["degradation"])
app.include_router(schedule.router, prefix="/api", tags=["schedule"])
app.include_router(persona.router, prefix="/api", tags=["persona"])
app.include_router(notifications.router, prefix="/api", tags=["notifications"])
app.include_router(push.router, prefix="/api", tags=["push"])
app.include_router(memory_facts.router, prefix="/api", tags=["memory"])
app.include_router(user_profile.router, prefix="/api", tags=["profile"])
app.include_router(mcp.router, prefix="/api", tags=["mcp"])
app.include_router(audit.router, prefix="/api", tags=["audit"])

# Serve static UI files (when they exist)
UI_PATH = Path(__file__).parent.parent / "ui"
if UI_PATH.exists():
    app.mount("/static", StaticFiles(directory=UI_PATH), name="static")

    @app.get("/")
    async def serve_index():
        """Serve the main UI page."""
        index_path = UI_PATH / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        return {"message": "UI not yet implemented. Use /api/chat endpoint."}

    @app.get("/manifest.json")
    async def serve_manifest():
        """Serve PWA manifest with proper MIME type."""
        from fastapi.responses import JSONResponse
        manifest_path = UI_PATH / "manifest.json"
        if manifest_path.exists():
            import json
            with open(manifest_path) as f:
                manifest = json.load(f)
            return JSONResponse(content=manifest, media_type="application/manifest+json")
        return {"error": "Manifest not found"}

    @app.get("/sw.js")
    async def serve_service_worker():
        """Serve service worker with proper MIME type."""
        from fastapi.responses import Response
        sw_path = UI_PATH / "sw.js"
        if sw_path.exists():
            with open(sw_path) as f:
                sw_content = f.read()
            return Response(content=sw_content, media_type="application/javascript")
        return {"error": "Service worker not found"}
else:
    @app.get("/")
    async def root():
        """Root endpoint."""
        return {
            "message": "AI Assistant API",
            "docs": "/docs",
            "status": "/api/status"
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server.main:app",
        host=config.HOST,
        port=config.PORT,
        reload=True
    )
