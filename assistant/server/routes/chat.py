"""Chat API endpoint with Claude API (primary) and OpenAI fallback."""
import logging
import base64
import json
import time
from datetime import datetime
from typing import Optional, List
from pathlib import Path
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

import config
from server.services.memory import MemoryService, DEFAULT_CONVERSATION_ID
from server.services.tools import registry as tool_registry
from server.services.retry import api_retry
from server.services.metrics import metrics
from server.services.tool_suggestions import get_suggestion_service

router = APIRouter()
logger = logging.getLogger(__name__)

# Initialize memory service
memory = MemoryService(config.DATABASE_PATH)


class ChatMessage(BaseModel):
    """Chat message request model."""
    message: str
    # Deprecated: conversation_id is kept for backward compatibility but ignored
    # All messages now go to the single infinite conversation
    conversation_id: Optional[str] = None
    file_ids: Optional[List[str]] = None


class PermissionEscalation(BaseModel):
    """Permission escalation request model."""
    tool_name: str
    tool_description: str
    current_level: int
    current_level_name: str
    required_level: int
    required_level_name: str
    pending_args: dict = {}


class SuggestedTool(BaseModel):
    """A suggested tool based on the user's message."""
    name: str
    description: str
    relevance_reason: str
    usage_hint: str


class ChatResponse(BaseModel):
    """Chat response model."""
    response: str
    # Always returns DEFAULT_CONVERSATION_ID for the single infinite conversation
    conversation_id: str
    timestamp: str
    model: str  # Which model was used
    # Optional: permission escalation request from tool
    permission_escalation: Optional[PermissionEscalation] = None
    # Optional: suggested tools based on user's message
    suggested_tools: Optional[List[SuggestedTool]] = None


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


@api_retry
async def call_claude_api(messages: list, file_ids: list, user_message: str, system_prompt: str = "") -> tuple[str, str, Optional[dict]]:
    """Call Claude API with tool support and return (response, model_name, escalation).

    Args:
        messages: Conversation history
        file_ids: List of file IDs to attach
        user_message: The current user message
        system_prompt: Optional system prompt with tool suggestions

    Returns:
        tuple: (response_text, model_name, permission_escalation_or_none)

    Includes automatic retry with exponential backoff for transient failures.
    """
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

    # Get tools in Claude format
    tools = tool_registry.to_claude_tools()

    # Loop to handle tool calls
    max_tool_iterations = 5
    for iteration in range(max_tool_iterations):
        api_kwargs = {
            "model": config.CLAUDE_MODEL,
            "max_tokens": 4096,
            "messages": claude_messages,
        }
        if system_prompt:
            api_kwargs["system"] = system_prompt
        if tools:
            api_kwargs["tools"] = tools

        response = client.messages.create(**api_kwargs)

        # Check if response contains tool use
        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

        if not tool_use_blocks:
            # No tool calls, extract text response
            text_blocks = [b for b in response.content if b.type == "text"]
            if text_blocks:
                return text_blocks[0].text, config.CLAUDE_MODEL, None
            return "", config.CLAUDE_MODEL, None

        # Process tool calls
        tool_results = []
        permission_escalation = None  # Track if any tool needs escalation

        for tool_block in tool_use_blocks:
            tool_name = tool_block.name
            tool_input = tool_block.input
            tool_id = tool_block.id

            logger.info(f"Claude calling tool: {tool_name} with input: {tool_input}")

            # Execute the tool and record metrics
            result = tool_registry.execute(tool_name, **tool_input)
            metrics.record_tool_call(tool_name)

            if result["success"]:
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": str(result["result"]),
                })
            elif "permission_escalation" in result:
                # Tool requires elevated permission - return escalation request
                escalation = result["permission_escalation"]
                permission_escalation = escalation
                logger.info(
                    f"Tool {tool_name} requires permission escalation: "
                    f"{escalation['current_level_name']} -> {escalation['required_level_name']}"
                )
                # Return a message asking for permission instead of error
                escalation_msg = (
                    f"I need elevated permissions to use the **{tool_name}** tool.\n\n"
                    f"**Current permission level:** {escalation['current_level_name']}\n"
                    f"**Required permission level:** {escalation['required_level_name']}\n\n"
                    f"Would you like to grant {escalation['required_level_name']} permission? "
                    f"This will allow me to: {escalation['tool_description']}"
                )
                # Return the escalation response immediately
                return escalation_msg, config.CLAUDE_MODEL, escalation
            else:
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": f"Error: {result['error']}",
                    "is_error": True,
                })

        # Add assistant message with tool use and tool results
        claude_messages.append({
            "role": "assistant",
            "content": response.content,
        })
        claude_messages.append({
            "role": "user",
            "content": tool_results,
        })

    # If we exit the loop, return what we have
    return "I apologize, I couldn't complete the task after multiple tool attempts.", config.CLAUDE_MODEL, None


@api_retry
async def call_openai_api(messages: list, file_ids: list, user_message: str, system_prompt: str = "") -> tuple[str, str, Optional[dict]]:
    """Call OpenAI API with tool support and return (response, model_name, escalation).

    Args:
        messages: Conversation history
        file_ids: List of file IDs to attach
        user_message: The current user message
        system_prompt: Optional system prompt with tool suggestions

    Returns:
        tuple: (response_text, model_name, permission_escalation_or_none)

    Includes automatic retry with exponential backoff for transient failures.
    """
    client = get_openai_client()
    if not client:
        raise ValueError("OpenAI client not available")

    # Inject system prompt at the beginning if provided
    if system_prompt:
        messages = [{"role": "system", "content": system_prompt}] + messages

    # Build the current message with multimodal content
    if file_ids:
        content_parts = [{"type": "text", "text": user_message}]
        for file_id in file_ids:
            file_content = load_file_for_openai(file_id)
            if file_content:
                content_parts.append(file_content)
        messages[-1] = {"role": "user", "content": content_parts}

    # Get tools in OpenAI format
    tools = tool_registry.to_openai_tools()

    # Loop to handle tool calls
    max_tool_iterations = 5
    for iteration in range(max_tool_iterations):
        api_kwargs = {
            "model": config.OPENAI_MODEL,
            "messages": messages,
        }
        if tools:
            api_kwargs["tools"] = tools

        completion = client.chat.completions.create(**api_kwargs)
        choice = completion.choices[0]

        # Check if response contains tool calls
        if not choice.message.tool_calls:
            return choice.message.content or "", config.OPENAI_MODEL, None

        # Process tool calls
        # First, add the assistant's message with tool calls
        messages.append({
            "role": "assistant",
            "content": choice.message.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    }
                }
                for tc in choice.message.tool_calls
            ]
        })

        # Execute each tool and add results
        for tool_call in choice.message.tool_calls:
            tool_name = tool_call.function.name
            try:
                tool_args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                tool_args = {}

            logger.info(f"OpenAI calling tool: {tool_name} with input: {tool_args}")

            # Execute the tool and record metrics
            result = tool_registry.execute(tool_name, **tool_args)
            metrics.record_tool_call(tool_name)

            if result["success"]:
                tool_result = str(result["result"])
            elif "permission_escalation" in result:
                # Tool requires elevated permission - return escalation request
                escalation = result["permission_escalation"]
                logger.info(
                    f"Tool {tool_name} requires permission escalation: "
                    f"{escalation['current_level_name']} -> {escalation['required_level_name']}"
                )
                escalation_msg = (
                    f"I need elevated permissions to use the **{tool_name}** tool.\n\n"
                    f"**Current permission level:** {escalation['current_level_name']}\n"
                    f"**Required permission level:** {escalation['required_level_name']}\n\n"
                    f"Would you like to grant {escalation['required_level_name']} permission? "
                    f"This will allow me to: {escalation['tool_description']}"
                )
                return escalation_msg, config.OPENAI_MODEL, escalation
            else:
                tool_result = f"Error: {result['error']}"

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": tool_result,
            })

    # If we exit the loop, return what we have
    return "I apologize, I couldn't complete the task after multiple tool attempts.", config.OPENAI_MODEL, None


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatMessage):
    """Send a message and get AI response (Claude primary, OpenAI fallback).

    All messages are stored in a single infinite conversation.
    The conversation_id parameter is deprecated and ignored.
    """
    start_time = time.time()

    # Single infinite conversation - always use the default
    # Note: conversation_id in request is ignored (kept for backward compatibility)

    # Build message content with attachments
    file_refs = []
    if request.file_ids:
        for fid in request.file_ids:
            file_refs.append(fid)

    # Store message with file references
    message_text = request.message
    if file_refs:
        message_text = f"{request.message}\n[Attached files: {', '.join(file_refs)}]"

    await memory.add_to_conversation("user", message_text)

    try:
        # Get conversation history with automatic summarization for long conversations
        messages, context_meta = await memory.get_context_for_api()

        if context_meta["summarized_count"] > 0:
            logger.info(
                f"Context: {context_meta['total_messages']} total msgs, "
                f"{context_meta['summarized_count']} summarized, "
                f"{context_meta['verbatim_count']} verbatim"
            )

        # Analyze user message for relevant tool suggestions
        suggestion_service = get_suggestion_service()
        suggestions = suggestion_service.analyze_message(request.message)

        # Build system prompt with tool suggestions
        system_parts = [
            "You are a helpful AI assistant with access to various system tools.",
            "Be proactive about suggesting tools when they would help the user's task.",
        ]

        if suggestions:
            suggestion_text = suggestion_service.get_system_prompt_injection(suggestions)
            system_parts.append(suggestion_text)
            logger.info(f"Suggesting {len(suggestions)} relevant tools: {[s.name for s in suggestions]}")
        else:
            # Include general tool summary when no specific suggestions
            summary = suggestion_service.get_available_tools_summary()
            if summary:
                system_parts.append(summary)

        system_prompt = "\n".join(system_parts)

        # Try Claude first, fallback to OpenAI
        model_used = None
        assistant_message = None
        permission_escalation = None

        if config.USE_CLAUDE:
            try:
                logger.info(f"Calling Claude API with model {config.CLAUDE_MODEL}, files: {request.file_ids or []}")
                assistant_message, model_used, permission_escalation = await call_claude_api(
                    messages, request.file_ids or [], request.message, system_prompt
                )
            except Exception as e:
                logger.warning(f"Claude API failed, falling back to OpenAI: {e}")

        if assistant_message is None:
            logger.info(f"Calling OpenAI API with model {config.OPENAI_MODEL}, files: {request.file_ids or []}")
            assistant_message, model_used, permission_escalation = await call_openai_api(
                messages, request.file_ids or [], request.message, system_prompt
            )

        # Save assistant response
        await memory.add_to_conversation("assistant", assistant_message)

        logger.info(f"Chat completed in single conversation using {model_used}")

        # Record successful request metrics
        latency_ms = (time.time() - start_time) * 1000
        metrics.record_request("/api/chat", latency_ms, success=True)

        # Convert escalation dict to Pydantic model if present
        escalation_model = None
        if permission_escalation:
            escalation_model = PermissionEscalation(
                tool_name=permission_escalation["tool_name"],
                tool_description=permission_escalation["tool_description"],
                current_level=permission_escalation["current_level"],
                current_level_name=permission_escalation["current_level_name"],
                required_level=permission_escalation["required_level"],
                required_level_name=permission_escalation["required_level_name"],
                pending_args=permission_escalation.get("pending_args", {}),
            )

        # Convert suggestions to response format
        suggested_tools_response = None
        if suggestions:
            suggested_tools_response = [
                SuggestedTool(
                    name=s.name,
                    description=s.description or "",
                    relevance_reason=s.relevance_reason,
                    usage_hint=s.usage_hint or "",
                )
                for s in suggestions
            ]

        return ChatResponse(
            response=assistant_message,
            conversation_id=DEFAULT_CONVERSATION_ID,
            timestamp=datetime.now().isoformat(),
            model=model_used,
            permission_escalation=escalation_model,
            suggested_tools=suggested_tools_response,
        )

    except Exception as e:
        logger.error(f"API error: {e}")
        # Record failed request metrics
        latency_ms = (time.time() - start_time) * 1000
        metrics.record_request("/api/chat", latency_ms, success=False)
        metrics.record_error("/api/chat", type(e).__name__)

        # Remove the user message if API call failed
        await memory.remove_last_message_from_conversation()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversation")
async def get_the_conversation():
    """Get the single infinite conversation with messages.

    In the single-conversation model, there is only one conversation
    that grows forever. This endpoint returns all messages.
    """
    conversation = await memory.get_conversation(DEFAULT_CONVERSATION_ID)
    if not conversation:
        # Auto-create if doesn't exist
        await memory._ensure_default_conversation()
        conversation = await memory.get_conversation(DEFAULT_CONVERSATION_ID)
    return conversation


@router.get("/conversations")
async def list_conversations():
    """List all conversations (deprecated).

    In the single-conversation model, this returns only the default conversation.
    Kept for backward compatibility.
    """
    conversations = await memory.list_conversations()
    return {"conversations": conversations}


@router.get("/conversation/{conversation_id}")
async def get_conversation(conversation_id: str):
    """Get a conversation by ID (deprecated).

    In the single-conversation model, only DEFAULT_CONVERSATION_ID is used.
    Kept for backward compatibility.
    """
    conversation = await memory.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.get("/messages/search")
async def search_messages(
    q: str,
    limit: int = 50,
    offset: int = 0
):
    """Search messages by keyword in the infinite conversation.

    Args:
        q: Search query (required)
        limit: Maximum results (default 50, max 100)
        offset: Pagination offset

    Returns:
        List of matching messages with snippets and context
    """
    if not q or len(q.strip()) < 2:
        raise HTTPException(
            status_code=400,
            detail="Search query must be at least 2 characters"
        )

    # Cap limit to prevent abuse
    limit = min(limit, 100)

    # Search in the single infinite conversation
    results = await memory.search_messages(
        query=q.strip(),
        conversation_id=DEFAULT_CONVERSATION_ID,
        limit=limit,
        offset=offset
    )

    return {
        "query": q.strip(),
        "count": len(results),
        "results": results
    }
