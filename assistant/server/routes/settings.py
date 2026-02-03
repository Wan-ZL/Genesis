"""Settings API routes."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from pathlib import Path
import os

import config
from server.services.settings import SettingsService

router = APIRouter()

# Initialize settings service with same database
settings_service = SettingsService(config.DATABASE_PATH)


class SettingsUpdate(BaseModel):
    """Model for updating settings."""
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    model: Optional[str] = None
    permission_level: Optional[int] = None


@router.get("/settings")
async def get_settings():
    """Get current settings (with masked API keys)."""
    return await settings_service.get_display_settings()


@router.post("/settings")
async def update_settings(update: SettingsUpdate):
    """Update settings."""
    updates = {}

    # Only update non-None values
    if update.openai_api_key is not None:
        updates["openai_api_key"] = update.openai_api_key

    if update.anthropic_api_key is not None:
        updates["anthropic_api_key"] = update.anthropic_api_key

    if update.model is not None:
        # Validate model is in available list
        valid_models = [m["id"] for m in SettingsService.AVAILABLE_MODELS]
        if update.model not in valid_models:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid model. Choose from: {', '.join(valid_models)}"
            )
        updates["model"] = update.model

    if update.permission_level is not None:
        if update.permission_level not in [0, 1, 2, 3]:
            raise HTTPException(
                status_code=400,
                detail="Permission level must be 0 (SANDBOX), 1 (LOCAL), 2 (SYSTEM), or 3 (FULL)"
            )
        updates["permission_level"] = update.permission_level

    if updates:
        await settings_service.set_multiple(updates)

        # Update runtime config (takes effect immediately for some settings)
        await _apply_runtime_settings()

    return {
        "status": "updated",
        "updated_keys": list(updates.keys()),
        "settings": await settings_service.get_display_settings()
    }


async def _apply_runtime_settings():
    """Apply settings to runtime configuration.

    Note: Some settings (like API keys) are loaded from env at startup.
    Full effect may require restart for some settings.
    """
    settings = await settings_service.get_all()

    # Update config module values (for new requests)
    if settings.get("openai_api_key"):
        config.OPENAI_API_KEY = settings["openai_api_key"]

    if settings.get("anthropic_api_key"):
        config.ANTHROPIC_API_KEY = settings["anthropic_api_key"]
        config.USE_CLAUDE = True

    # Update model selection
    if settings.get("model"):
        model = settings["model"]
        if "claude" in model:
            config.MODEL = model
            config.CLAUDE_MODEL = model
            config.USE_CLAUDE = True
        else:
            config.MODEL = model
            config.OPENAI_MODEL = model
            config.USE_CLAUDE = False


async def get_active_api_key():
    """Get the currently active API key based on model selection."""
    settings = await settings_service.get_all()
    model = settings.get("model", "gpt-4o")

    if "claude" in model:
        return settings.get("anthropic_api_key") or config.ANTHROPIC_API_KEY
    else:
        return settings.get("openai_api_key") or config.OPENAI_API_KEY


async def get_active_model():
    """Get the currently selected model."""
    return await settings_service.get("model") or config.MODEL
