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
    logger.info(f"Using model: {config.MODEL}")
    if not config.OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY not set - chat will not work")
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
from server.routes import chat, status, upload, metrics

app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(status.router, prefix="/api", tags=["status"])
app.include_router(upload.router, prefix="/api", tags=["upload"])
app.include_router(metrics.router, prefix="/api", tags=["metrics"])

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
