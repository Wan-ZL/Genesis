"""Status API endpoint - AI Assistant's own status only."""
import time
from fastapi import APIRouter

import config
from server.services.ollama import get_ollama_client, check_ollama_available
from server.services.degradation import get_degradation_service

router = APIRouter()

# Track server start time for uptime calculation
_start_time = time.time()
_message_count = 0


def increment_message_count():
    """Called by chat route to track messages."""
    global _message_count
    _message_count += 1


def get_message_count() -> int:
    """Get total message count."""
    return _message_count


@router.get("/health")
async def health_check():
    """Simple health check endpoint for service monitoring.

    Returns basic health status including Ollama availability.
    """
    from version import __version__

    # Check Ollama availability (cached for 30s)
    ollama_available = False
    if config.OLLAMA_ENABLED:
        try:
            ollama_available = await check_ollama_available()
        except Exception:
            pass

    return {
        "status": "healthy",
        "version": __version__,
        "uptime_seconds": int(time.time() - _start_time),
        "ollama_available": ollama_available,
    }


@router.get("/status")
async def get_status():
    """Get AI Assistant status (not Claude Code status).

    Includes detailed status of all model providers (Claude, OpenAI, Ollama).
    """
    from version import __version__

    degradation = get_degradation_service()

    # Get Ollama status
    ollama_status = None
    if config.OLLAMA_ENABLED:
        try:
            client = get_ollama_client()
            ollama_status = client.get_status()
        except Exception:
            ollama_status = {"status": "error"}

    return {
        "status": "running",
        "version": __version__,
        "uptime_seconds": int(time.time() - _start_time),
        "message_count": _message_count,
        "model_providers": {
            "claude": {
                "configured": bool(config.ANTHROPIC_API_KEY),
                "model": config.CLAUDE_MODEL if config.ANTHROPIC_API_KEY else None,
            },
            "openai": {
                "configured": bool(config.OPENAI_API_KEY),
                "model": config.OPENAI_MODEL if config.OPENAI_API_KEY else None,
            },
            "ollama": ollama_status,
        },
        "degradation_mode": degradation.mode.name,
        "local_only_mode": degradation.is_local_only,
    }
