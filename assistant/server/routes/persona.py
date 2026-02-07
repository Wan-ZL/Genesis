"""Persona API routes for custom system prompts."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from pathlib import Path

import config
from server.services.persona import PersonaService

router = APIRouter()

# Initialize persona service
persona_service = PersonaService(config.DATABASE_PATH)


class PersonaResponse(BaseModel):
    """Response model for persona templates."""
    id: str
    name: str
    description: str
    system_prompt: str
    is_builtin: bool
    created_at: str
    updated_at: str


class CreatePersonaRequest(BaseModel):
    """Request model for creating a persona."""
    name: str
    description: str = ""
    system_prompt: str


class UpdatePersonaRequest(BaseModel):
    """Request model for updating a persona."""
    name: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None


class SetConversationPersonaRequest(BaseModel):
    """Request model for setting a conversation's persona."""
    persona_id: Optional[str] = None
    custom_system_prompt: Optional[str] = None


@router.get("/personas")
async def list_personas():
    """Get all persona templates (built-in + custom).

    Returns:
        List of all available persona templates
    """
    personas = await persona_service.get_all_personas()
    return {
        "personas": [
            PersonaResponse(
                id=p.id,
                name=p.name,
                description=p.description,
                system_prompt=p.system_prompt,
                is_builtin=p.is_builtin,
                created_at=p.created_at,
                updated_at=p.updated_at,
            )
            for p in personas
        ]
    }


@router.get("/personas/{persona_id}")
async def get_persona(persona_id: str):
    """Get a specific persona template by ID.

    Args:
        persona_id: The persona ID

    Returns:
        The persona template
    """
    persona = await persona_service.get_persona(persona_id)
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")

    return PersonaResponse(
        id=persona.id,
        name=persona.name,
        description=persona.description,
        system_prompt=persona.system_prompt,
        is_builtin=persona.is_builtin,
        created_at=persona.created_at,
        updated_at=persona.updated_at,
    )


@router.post("/personas")
async def create_persona(request: CreatePersonaRequest):
    """Create a new custom persona template.

    Args:
        request: Persona details (name, description, system_prompt)

    Returns:
        The created persona

    Raises:
        400: If system_prompt exceeds 4000 characters
    """
    try:
        persona = await persona_service.create_persona(
            name=request.name,
            description=request.description,
            system_prompt=request.system_prompt
        )
        return PersonaResponse(
            id=persona.id,
            name=persona.name,
            description=persona.description,
            system_prompt=persona.system_prompt,
            is_builtin=persona.is_builtin,
            created_at=persona.created_at,
            updated_at=persona.updated_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/personas/{persona_id}")
async def update_persona(persona_id: str, request: UpdatePersonaRequest):
    """Update a custom persona template.

    Built-in personas cannot be updated.

    Args:
        persona_id: The persona to update
        request: Updated fields (name, description, system_prompt)

    Returns:
        The updated persona

    Raises:
        400: If trying to update built-in or system_prompt exceeds 4000 chars
        404: If persona not found
    """
    try:
        success = await persona_service.update_persona(
            persona_id=persona_id,
            name=request.name,
            description=request.description,
            system_prompt=request.system_prompt
        )
        if not success:
            raise HTTPException(
                status_code=400,
                detail="Cannot update built-in persona or persona not found"
            )

        persona = await persona_service.get_persona(persona_id)
        if not persona:
            raise HTTPException(status_code=404, detail="Persona not found after update")

        return PersonaResponse(
            id=persona.id,
            name=persona.name,
            description=persona.description,
            system_prompt=persona.system_prompt,
            is_builtin=persona.is_builtin,
            created_at=persona.created_at,
            updated_at=persona.updated_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/personas/{persona_id}")
async def delete_persona(persona_id: str):
    """Delete a custom persona template.

    Built-in personas cannot be deleted.

    Args:
        persona_id: The persona to delete

    Returns:
        Success confirmation

    Raises:
        400: If trying to delete built-in persona
        404: If persona not found
    """
    success = await persona_service.delete_persona(persona_id)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete built-in persona or persona not found"
        )

    return {"success": True, "deleted": persona_id}


@router.put("/conversations/{conversation_id}/persona")
async def set_conversation_persona(conversation_id: str, request: SetConversationPersonaRequest):
    """Set the persona for a specific conversation.

    This allows per-conversation system prompt overrides.

    Args:
        conversation_id: The conversation
        request: Persona settings (persona_id or custom_system_prompt)

    Returns:
        Success confirmation

    Raises:
        400: If custom_system_prompt exceeds 4000 characters
    """
    try:
        await persona_service.set_conversation_persona(
            conversation_id=conversation_id,
            persona_id=request.persona_id,
            custom_system_prompt=request.custom_system_prompt
        )
        return {
            "success": True,
            "conversation_id": conversation_id,
            "persona_id": request.persona_id,
            "custom_system_prompt_set": bool(request.custom_system_prompt)
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/conversations/{conversation_id}/persona")
async def get_conversation_persona(conversation_id: str):
    """Get the persona settings for a conversation.

    Args:
        conversation_id: The conversation

    Returns:
        Persona settings (persona_id, custom_system_prompt) or empty dict
    """
    persona_settings = await persona_service.get_conversation_persona(conversation_id)
    if not persona_settings:
        return {
            "conversation_id": conversation_id,
            "persona_id": None,
            "custom_system_prompt": None
        }

    return {
        "conversation_id": conversation_id,
        **persona_settings
    }
