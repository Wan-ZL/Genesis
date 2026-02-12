"""API routes for user profile management."""
import logging
from typing import Dict, Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException

from server.services.user_profile import get_user_profile_service, PROFILE_SECTIONS

router = APIRouter()
logger = logging.getLogger(__name__)


class UpdateSectionRequest(BaseModel):
    """Request model for updating a profile section."""
    data: Dict[str, str] = Field(..., description="Key-value pairs to update")


class ImportProfileRequest(BaseModel):
    """Request model for importing profile data."""
    version: str = "1.0"
    sections: Dict[str, Dict[str, Any]]
    mode: str = Field("merge", description="'merge' or 'replace'")


@router.get("/profile")
async def get_profile():
    """Get the complete user profile organized by sections.

    Returns:
        Full profile with all sections and their entries
    """
    service = get_user_profile_service()
    profile = await service.get_profile()

    return {
        "sections": profile,
        "section_labels": PROFILE_SECTIONS,
    }


@router.get("/profile/export")
async def export_profile():
    """Export the user profile in a portable JSON format.

    Returns:
        Profile data with version and metadata for backup/transfer
    """
    service = get_user_profile_service()
    export_data = await service.export_profile()

    return export_data


@router.post("/profile/import")
async def import_profile(request: ImportProfileRequest):
    """Import profile from exported JSON format.

    Args:
        request: ImportProfileRequest with version, sections, and mode

    Returns:
        Success confirmation
    """
    service = get_user_profile_service()

    try:
        await service.import_profile(
            data={
                "version": request.version,
                "sections": request.sections,
            },
            mode=request.mode
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "success": True,
        "mode": request.mode,
    }


@router.get("/profile/{section}")
async def get_section(section: str):
    """Get a specific profile section.

    Args:
        section: Section name (personal_info, work, preferences, etc.)

    Returns:
        Entries in the requested section
    """
    service = get_user_profile_service()

    try:
        entries = await service.get_section(section)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "section": section,
        "label": PROFILE_SECTIONS.get(section, section),
        "entries": entries,
    }


@router.put("/profile/{section}")
async def update_section(section: str, request: UpdateSectionRequest):
    """Update a profile section with manual overrides.

    Args:
        section: Section name
        request: UpdateSectionRequest with key-value pairs

    Returns:
        List of updated keys
    """
    service = get_user_profile_service()

    try:
        result = await service.update_section(section, request.data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "success": True,
        "section": section,
        **result,
    }


@router.delete("/profile/{section}/{key}")
async def delete_entry(section: str, key: str):
    """Delete a specific profile entry.

    Args:
        section: Section name
        key: Entry key to delete

    Returns:
        Success confirmation
    """
    service = get_user_profile_service()

    try:
        deleted = await service.delete_entry(section, key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not deleted:
        raise HTTPException(status_code=404, detail="Profile entry not found")

    return {
        "success": True,
        "deleted": {"section": section, "key": key},
    }


@router.delete("/profile")
async def clear_profile():
    """Clear all profile entries.

    This is a destructive operation. Use with caution.

    Returns:
        Success confirmation
    """
    service = get_user_profile_service()
    await service.clear_profile()

    return {
        "success": True,
        "message": "Profile cleared",
    }


@router.post("/profile/aggregate")
async def aggregate_from_facts():
    """Manually trigger profile aggregation from long-term memory facts.

    This normally happens automatically after fact extraction,
    but can be triggered manually to refresh the profile.

    Returns:
        Success confirmation
    """
    from server.services.memory_extractor import get_memory_extractor

    service = get_user_profile_service()
    memory_extractor = get_memory_extractor()

    await service.aggregate_from_facts(memory_extractor)

    return {
        "success": True,
        "message": "Profile aggregated from facts",
    }
