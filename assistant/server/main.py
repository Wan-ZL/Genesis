"""AI Assistant - FastAPI main entry point."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

import config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info(f"Starting AI Assistant on {config.HOST}:{config.PORT}")

    # Load user settings from database (API keys, model selection)
    # This restores settings saved in previous sessions
    from server.routes.settings import load_settings_on_startup
    await load_settings_on_startup()

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

    logger.info(f"Using model: {config.MODEL}")
    if not config.OPENAI_API_KEY and not config.ANTHROPIC_API_KEY:
        logger.warning("No API key set - configure via Settings page or .env files")
    yield
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

# Import and include routers
from server.routes import chat, status, upload, metrics, settings, capabilities

app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(status.router, prefix="/api", tags=["status"])
app.include_router(upload.router, prefix="/api", tags=["upload"])
app.include_router(metrics.router, prefix="/api", tags=["metrics"])
app.include_router(settings.router, prefix="/api", tags=["settings"])
app.include_router(capabilities.router, prefix="/api", tags=["capabilities"])

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
