"""API routes for long-term memory facts management."""
import logging
from typing import Optional, List
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Query

from server.services.memory_extractor import get_memory_extractor

router = APIRouter()
logger = logging.getLogger(__name__)


class FactResponse(BaseModel):
    """Response model for a single fact."""
    id: str
    fact_type: str
    key: str
    value: str
    source_conversation_id: str
    source_message_id: str
    confidence: float
    created_at: str
    updated_at: str


class FactsListResponse(BaseModel):
    """Response model for list of facts."""
    facts: List[FactResponse]
    count: int
    limit: int
    offset: int


@router.get("/memory/facts", response_model=FactsListResponse)
async def list_facts(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    fact_type: Optional[str] = Query(None, description="Filter by fact type")
):
    """List all stored facts with pagination.

    Args:
        limit: Maximum number of facts to return (1-500)
        offset: Pagination offset
        fact_type: Optional filter by fact type (preference, personal_info, work_context, etc.)

    Returns:
        List of facts with pagination metadata
    """
    service = get_memory_extractor()

    facts = await service.get_all_facts(
        limit=limit,
        offset=offset,
        fact_type=fact_type
    )

    fact_responses = [
        FactResponse(
            id=f.id,
            fact_type=f.fact_type,
            key=f.key,
            value=f.value,
            source_conversation_id=f.source_conversation_id,
            source_message_id=f.source_message_id,
            confidence=f.confidence,
            created_at=f.created_at,
            updated_at=f.updated_at
        )
        for f in facts
    ]

    return FactsListResponse(
        facts=fact_responses,
        count=len(fact_responses),
        limit=limit,
        offset=offset
    )


@router.get("/memory/facts/{fact_id}", response_model=FactResponse)
async def get_fact(fact_id: str):
    """Get a specific fact by ID.

    Args:
        fact_id: The fact ID to retrieve

    Returns:
        The fact details
    """
    service = get_memory_extractor()
    fact = await service.get_fact(fact_id)

    if not fact:
        raise HTTPException(status_code=404, detail="Fact not found")

    return FactResponse(
        id=fact.id,
        fact_type=fact.fact_type,
        key=fact.key,
        value=fact.value,
        source_conversation_id=fact.source_conversation_id,
        source_message_id=fact.source_message_id,
        confidence=fact.confidence,
        created_at=fact.created_at,
        updated_at=fact.updated_at
    )


@router.delete("/memory/facts/{fact_id}")
async def delete_fact(fact_id: str):
    """Delete a specific fact by ID.

    Args:
        fact_id: The fact ID to delete

    Returns:
        Success confirmation
    """
    service = get_memory_extractor()
    success = await service.delete_fact(fact_id)

    if not success:
        raise HTTPException(status_code=404, detail="Fact not found")

    return {"success": True, "deleted": fact_id}


@router.delete("/memory/facts")
async def delete_all_facts():
    """Delete all stored facts.

    This is a destructive operation that clears all long-term memory.
    Use with caution.

    Returns:
        Number of facts deleted
    """
    service = get_memory_extractor()
    count = await service.delete_all_facts()

    return {"success": True, "deleted_count": count}


@router.get("/memory/search")
async def search_facts(
    q: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(50, ge=1, le=100),
    fact_type: Optional[str] = Query(None, description="Filter by fact type")
):
    """Search facts using FTS5 full-text search.

    Args:
        q: Search query (minimum 2 characters)
        limit: Maximum number of results (1-100)
        fact_type: Optional filter by fact type

    Returns:
        List of matching facts ordered by relevance
    """
    service = get_memory_extractor()

    fact_types = [fact_type] if fact_type else None
    facts = await service.recall_facts(
        query=q,
        fact_types=fact_types,
        limit=limit
    )

    fact_responses = [
        FactResponse(
            id=f.id,
            fact_type=f.fact_type,
            key=f.key,
            value=f.value,
            source_conversation_id=f.source_conversation_id,
            source_message_id=f.source_message_id,
            confidence=f.confidence,
            created_at=f.created_at,
            updated_at=f.updated_at
        )
        for f in facts
    ]

    return {
        "query": q,
        "count": len(fact_responses),
        "facts": fact_responses
    }
