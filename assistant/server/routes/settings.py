"""Settings API routes."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from pathlib import Path
import os
import logging

import config
from server.services.settings import SettingsService
from server.services.encryption import is_encrypted, ENCRYPTED_PREFIX
from server.services.ollama import get_ollama_client, OllamaStatus
from server.services.degradation import get_degradation_service

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
    # Ollama settings
    ollama_host: Optional[str] = None
    ollama_model: Optional[str] = None
    ollama_enabled: Optional[bool] = None
    local_only_mode: Optional[bool] = None


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

    # Ollama settings
    if update.ollama_host is not None:
        updates["ollama_host"] = update.ollama_host

    if update.ollama_model is not None:
        updates["ollama_model"] = update.ollama_model

    if update.ollama_enabled is not None:
        updates["ollama_enabled"] = str(update.ollama_enabled).lower()

    if update.local_only_mode is not None:
        updates["local_only_mode"] = str(update.local_only_mode).lower()
        # Update degradation service immediately
        degradation = get_degradation_service()
        degradation.set_local_only_mode(update.local_only_mode)

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

        # Load Ollama settings
        settings = await settings_service.get_all()

        # Apply local_only_mode to degradation service
        local_only = settings.get("local_only_mode", False)
        if isinstance(local_only, str):
            local_only = local_only.lower() == "true"
        if local_only:
            degradation = get_degradation_service()
            degradation.set_local_only_mode(True)
            logger.info("Local-only mode enabled from settings")

        # Update Ollama config
        ollama_host = settings.get("ollama_host")
        if ollama_host:
            config.OLLAMA_HOST = ollama_host

        ollama_model = settings.get("ollama_model")
        if ollama_model:
            config.OLLAMA_MODEL = ollama_model

        ollama_enabled = settings.get("ollama_enabled", True)
        if isinstance(ollama_enabled, str):
            ollama_enabled = ollama_enabled.lower() == "true"
        config.OLLAMA_ENABLED = ollama_enabled

    except Exception as e:
        logger.error(f"Failed to load settings from database: {type(e).__name__}: {e}")


# ============================================================================
# Ollama-specific endpoints
# ============================================================================


@router.get("/ollama/status")
async def get_ollama_status():
    """Get Ollama service status and available models."""
    client = get_ollama_client()
    status = await client.check_health()

    models = []
    if status == OllamaStatus.AVAILABLE:
        for model_info in await client.list_models():
            models.append({
                "name": model_info.name,
                "size": model_info.size,
                "supports_tools": model_info.supports_tools,
            })

    return {
        "status": status.value,
        "host": client.host,
        "current_model": client.model,
        "available_models": models,
        "ollama_enabled": config.OLLAMA_ENABLED,
    }


@router.get("/ollama/models")
async def list_ollama_models():
    """List available Ollama models.

    Returns a list of locally installed models that can be used for inference.
    """
    if not config.OLLAMA_ENABLED:
        raise HTTPException(
            status_code=400,
            detail="Ollama is disabled. Enable it in settings."
        )

    client = get_ollama_client()

    if not await client.is_available():
        raise HTTPException(
            status_code=503,
            detail=f"Ollama service not available at {client.host}. "
                   "Make sure Ollama is running (ollama serve)."
        )

    models = await client.list_models()
    return {
        "models": [
            {
                "name": m.name,
                "size": m.size,
                "size_gb": round(m.size / (1024 ** 3), 2) if m.size else 0,
                "supports_tools": m.supports_tools,
                "digest": m.digest,
            }
            for m in models
        ]
    }


class OllamaModelSelect(BaseModel):
    """Model for selecting an Ollama model."""
    model: str


@router.post("/ollama/model")
async def select_ollama_model(request: OllamaModelSelect):
    """Select which Ollama model to use.

    The model must be installed locally (use `ollama pull <model>` to install).
    """
    client = get_ollama_client()

    if not await client.is_available():
        raise HTTPException(
            status_code=503,
            detail="Ollama service not available"
        )

    # Verify model exists
    if not await client.has_model(request.model):
        available = [m.name for m in await client.list_models()]
        raise HTTPException(
            status_code=400,
            detail=f"Model '{request.model}' not found. Available: {', '.join(available)}"
        )

    # Update settings
    await settings_service.set("ollama_model", request.model)

    # Update runtime config
    config.OLLAMA_MODEL = request.model
    client.model = request.model

    return {
        "status": "updated",
        "model": request.model
    }


class LocalOnlyModeRequest(BaseModel):
    """Request to enable/disable local-only mode."""
    enabled: bool


@router.post("/ollama/local-only")
async def set_local_only_mode(request: LocalOnlyModeRequest):
    """Enable or disable local-only mode (Ollama only, no cloud APIs).

    When enabled, all requests will use Ollama regardless of cloud API availability.
    This is useful for:
    - Privacy-sensitive conversations
    - Offline operation
    - Reducing API costs
    """
    # Verify Ollama is available if enabling
    if request.enabled:
        client = get_ollama_client()
        if not await client.is_available():
            raise HTTPException(
                status_code=503,
                detail="Cannot enable local-only mode: Ollama is not available. "
                       "Start Ollama first (ollama serve)."
            )

    # Update settings
    await settings_service.set("local_only_mode", str(request.enabled).lower())

    # Update degradation service
    degradation = get_degradation_service()
    degradation.set_local_only_mode(request.enabled)

    return {
        "status": "updated",
        "local_only_mode": request.enabled
    }
