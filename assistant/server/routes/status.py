"""Status API endpoint - AI Assistant's own status only."""
import time
from fastapi import APIRouter

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
    """Simple health check endpoint for service monitoring."""
    from assistant.version import __version__
    return {
        "status": "healthy",
        "version": __version__,
        "uptime_seconds": int(time.time() - _start_time)
    }


@router.get("/status")
async def get_status():
    """Get AI Assistant status (not Claude Code status)."""
    from assistant.version import __version__

    return {
        "status": "running",
        "version": __version__,
        "uptime_seconds": int(time.time() - _start_time),
        "message_count": _message_count
    }
