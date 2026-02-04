"""Settings API routes."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from pathlib import Path
import os
import logging

import config
from server.services.settings import SettingsService
from server.services.encryption import is_encrypted, ENCRYPTED_PREFIX

logger = logging.getLogger(__name__)

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


def _validate_api_key(key_name: str, value: str) -> tuple[bool, str]:
    """Validate an API key is safe to use.

    Args:
        key_name: Name of the key (for logging)
        value: The API key value

    Returns:
        Tuple of (is_valid, reason)
    """
    if not value:
        return False, "empty"

    # Critical check: ensure we never use encrypted values
    if is_encrypted(value):
        logger.error(
            f"SECURITY: Attempted to use encrypted value as {key_name}. "
            f"Value starts with '{ENCRYPTED_PREFIX}'. This would leak encrypted data to external APIs. "
            f"Check that decryption is working correctly."
        )
        return False, "encrypted_value"

    # Basic format validation for API keys
    if key_name == "openai_api_key":
        # OpenAI keys start with sk-
        if not value.startswith("sk-"):
            logger.warning(f"OpenAI API key has unexpected format (doesn't start with sk-)")
            # Still allow it, just warn

    if key_name == "anthropic_api_key":
        # Anthropic keys start with sk-ant-
        if not value.startswith("sk-ant-"):
            logger.warning(f"Anthropic API key has unexpected format (doesn't start with sk-ant-)")
            # Still allow it, just warn

    return True, "valid"


async def _apply_runtime_settings():
    """Apply settings to runtime configuration.

    Note: Some settings (like API keys) are loaded from env at startup.
    Full effect may require restart for some settings.

    IMPORTANT: This function validates API keys before applying them to
    prevent encrypted values from being sent to external APIs.
    """
    settings = await settings_service.get_all()

    # Update config module values (for new requests)
    openai_key = settings.get("openai_api_key", "")
    if openai_key:
        is_valid, reason = _validate_api_key("openai_api_key", openai_key)
        if is_valid:
            config.OPENAI_API_KEY = openai_key
        else:
            logger.error(f"Not applying OpenAI API key: {reason}")

    anthropic_key = settings.get("anthropic_api_key", "")
    if anthropic_key:
        is_valid, reason = _validate_api_key("anthropic_api_key", anthropic_key)
        if is_valid:
            config.ANTHROPIC_API_KEY = anthropic_key
            config.USE_CLAUDE = True
        else:
            logger.error(f"Not applying Anthropic API key: {reason}")

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


async def load_settings_on_startup():
    """Load settings from SQLite and apply to runtime config.

    Called during server startup to restore user-configured settings
    (API keys, model selection) that were saved in previous sessions.

    Also validates that encrypted keys can be decrypted. If decryption
    fails, logs an error but continues (falling back to env vars).
    """
    try:
        # First, validate encryption status
        encryption_status = await settings_service.get_encryption_status()

        for key_name, key_status in encryption_status.get("keys", {}).items():
            if key_status.get("has_value") and key_status.get("is_encrypted"):
                # Key exists and is encrypted - verify it can be decrypted
                value = await settings_service.get(key_name)
                if not value:
                    logger.error(
                        f"Startup validation failed: {key_name} is encrypted but "
                        f"decryption returned empty. Check encryption key file."
                    )
                elif is_encrypted(value):
                    # This should never happen - get() should decrypt
                    logger.error(
                        f"Startup validation failed: {key_name} returned encrypted value. "
                        f"Decryption is not working correctly."
                    )
                else:
                    logger.info(f"Startup validation: {key_name} decrypted successfully")

        # Apply settings to runtime config
        await _apply_runtime_settings()
        logger.info("Settings loaded from database")

    except Exception as e:
        logger.error(f"Failed to load settings from database: {type(e).__name__}: {e}")
