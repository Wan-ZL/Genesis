"""Chat API endpoint with Claude API (primary) and OpenAI fallback."""
import logging
import base64
from datetime import datetime
from typing import Optional, List
from pathlib import Path
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

import config
from server.services.memory import MemoryService

router = APIRouter()
logger = logging.getLogger(__name__)

# Initialize memory service
memory = MemoryService(config.DATABASE_PATH)


class ChatMessage(BaseModel):
    """Chat message request model."""
    message: str
    conversation_id: Optional[str] = None
    file_ids: Optional[List[str]] = None


class ChatResponse(BaseModel):
    """Chat response model."""
    response: str
    conversation_id: str
    timestamp: str
    model: str  # Which model was used


def get_anthropic_client():
    """Get Anthropic client instance."""
    if not config.ANTHROPIC_API_KEY:
        return None
    from anthropic import Anthropic
    return Anthropic(api_key=config.ANTHROPIC_API_KEY)


def get_openai_client():
    """Get OpenAI client instance."""
    if not config.OPENAI_API_KEY:
        return None
    from openai import OpenAI
    return OpenAI(api_key=config.OPENAI_API_KEY)


def load_file_for_claude(file_id: str) -> Optional[dict]:
    """Load a file and prepare it for Claude API (vision format)."""
    files = list(config.FILES_PATH.glob(f"{file_id}.*"))
    if not files:
        return None

    file_path = files[0]
    ext = file_path.suffix.lower()

    with open(file_path, "rb") as f:
        content = f.read()

    base64_data = base64.b64encode(content).decode("utf-8")

    media_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }

    if ext in media_types:
        # Claude vision format
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_types[ext],
                "data": base64_data,
            }
        }
    elif ext == ".pdf":
        # Claude supports PDF via document type
        return {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": base64_data,
            }
        }

    return None


def load_file_for_openai(file_id: str) -> Optional[dict]:
    """Load a file and prepare it for OpenAI API."""
    files = list(config.FILES_PATH.glob(f"{file_id}.*"))
    if not files:
        return None

    file_path = files[0]
    ext = file_path.suffix.lower()

    with open(file_path, "rb") as f:
        content = f.read()

    base64_data = base64.b64encode(content).decode("utf-8")

    media_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }

    if ext in media_types:
        return {
            "type": "image_url",
            "image_url": {
                "url": f"data:{media_types[ext]};base64,{base64_data}"
            }
        }
    elif ext == ".pdf":
        return {
            "type": "text",
            "text": f"[PDF attached: {file_path.name}, {len(content)} bytes. PDF content analysis not yet implemented.]"
        }

    return None


async def call_claude_api(messages: list, file_ids: list, user_message: str) -> tuple[str, str]:
    """Call Claude API and return (response, model_name)."""
    client = get_anthropic_client()
    if not client:
        raise ValueError("Anthropic client not available")

    # Convert message history for Claude format
    # Claude expects: [{"role": "user"|"assistant", "content": str|list}]
    claude_messages = []
    for msg in messages[:-1]:  # Exclude last message, we'll rebuild it
        claude_messages.append({
            "role": msg["role"],
            "content": msg["content"]
        })

    # Build the current message with multimodal content
    if file_ids:
        content_parts = [{"type": "text", "text": user_message}]
        for file_id in file_ids:
            file_content = load_file_for_claude(file_id)
            if file_content:
                content_parts.append(file_content)
        claude_messages.append({"role": "user", "content": content_parts})
    else:
        claude_messages.append({"role": "user", "content": user_message})

    response = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=4096,
        messages=claude_messages
    )

    return response.content[0].text, config.CLAUDE_MODEL


async def call_openai_api(messages: list, file_ids: list, user_message: str) -> tuple[str, str]:
    """Call OpenAI API and return (response, model_name)."""
    client = get_openai_client()
    if not client:
        raise ValueError("OpenAI client not available")

    # Build the current message with multimodal content
    if file_ids:
        content_parts = [{"type": "text", "text": user_message}]
        for file_id in file_ids:
            file_content = load_file_for_openai(file_id)
            if file_content:
                content_parts.append(file_content)
        messages[-1] = {"role": "user", "content": content_parts}

    completion = client.chat.completions.create(
        model=config.OPENAI_MODEL,
        messages=messages
    )

    return completion.choices[0].message.content, config.OPENAI_MODEL


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatMessage):
    """Send a message and get AI response (Claude primary, OpenAI fallback)."""
    # Create new conversation or use existing
    if request.conversation_id:
        if not await memory.conversation_exists(request.conversation_id):
            raise HTTPException(status_code=404, detail="Conversation not found")
        conversation_id = request.conversation_id
    else:
        conversation_id = await memory.create_conversation()

    # Build message content with attachments
    file_refs = []
    if request.file_ids:
        for fid in request.file_ids:
            file_refs.append(fid)

    # Store message with file references
    message_text = request.message
    if file_refs:
        message_text = f"{request.message}\n[Attached files: {', '.join(file_refs)}]"

    await memory.add_message(conversation_id, "user", message_text)

    try:
        # Get conversation history
        messages = await memory.get_conversation_messages(conversation_id)

        # Try Claude first, fallback to OpenAI
        model_used = None
        assistant_message = None

        if config.USE_CLAUDE:
            try:
                logger.info(f"Calling Claude API with model {config.CLAUDE_MODEL}, files: {request.file_ids or []}")
                assistant_message, model_used = await call_claude_api(
                    messages, request.file_ids or [], request.message
                )
            except Exception as e:
                logger.warning(f"Claude API failed, falling back to OpenAI: {e}")

        if assistant_message is None:
            logger.info(f"Calling OpenAI API with model {config.OPENAI_MODEL}, files: {request.file_ids or []}")
            assistant_message, model_used = await call_openai_api(
                messages, request.file_ids or [], request.message
            )

        # Save assistant response
        await memory.add_message(conversation_id, "assistant", assistant_message)

        logger.info(f"Chat completed for conversation {conversation_id} using {model_used}")

        return ChatResponse(
            response=assistant_message,
            conversation_id=conversation_id,
            timestamp=datetime.now().isoformat(),
            model=model_used
        )

    except Exception as e:
        logger.error(f"API error: {e}")
        # Remove the user message if API call failed
        await memory.remove_last_message(conversation_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversations")
async def list_conversations():
    """List all conversations."""
    conversations = await memory.list_conversations()
    return {"conversations": conversations}


@router.get("/conversation/{conversation_id}")
async def get_conversation(conversation_id: str):
    """Get a single conversation with messages."""
    conversation = await memory.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation
