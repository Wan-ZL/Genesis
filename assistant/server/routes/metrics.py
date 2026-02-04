"""Metrics API endpoint."""
import logging
from fastapi import APIRouter

from server.services.metrics import metrics
from server.services.memory import MemoryService
from server.services.resources import get_resource_service
import config

router = APIRouter()
logger = logging.getLogger(__name__)

# Initialize memory service for conversation stats
memory = MemoryService(config.DATABASE_PATH)

# Initialize resource service
resources = get_resource_service(files_path=config.FILES_PATH)


@router.get("/metrics")
async def get_metrics():
    """Get current system metrics."""
    # Get base metrics
    data = metrics.to_dict()

    # Add conversation statistics from memory
    try:
        conversations = await memory.list_conversations()
        total_messages = sum(c.get("message_count", 0) for c in conversations)
        data["conversations"] = {
            "total": len(conversations),
            "total_messages": total_messages,
        }
    except Exception as e:
        logger.warning(f"Could not fetch conversation stats: {e}")
        data["conversations"] = {"total": 0, "total_messages": 0}

    # Add file statistics
    try:
        files = await memory.list_files()
        total_size = sum(f.get("size", 0) for f in files)
        data["files"] = {
            "total": len(files),
            "total_size_bytes": total_size,
        }
    except Exception as e:
        logger.warning(f"Could not fetch file stats: {e}")
        data["files"] = {"total": 0, "total_size_bytes": 0}

    # Add resource metrics (memory, CPU, disk)
    try:
        resource_data = resources.to_dict()
        data["resources"] = {
            "memory_mb": resource_data["memory"]["process_mb"],
            "cpu_percent": resource_data["cpu"]["process_percent"],
            "disk_percent": resource_data["disk"]["percent"],
            "status": resource_data["status"],
        }
    except Exception as e:
        logger.warning(f"Could not fetch resource stats: {e}")
        data["resources"] = {"memory_mb": 0, "cpu_percent": 0, "disk_percent": 0, "status": "unknown"}

    return data


@router.post("/metrics/reset")
async def reset_metrics():
    """Reset metrics (for testing/debugging)."""
    metrics.reset()
    return {"status": "ok", "message": "Metrics reset"}
