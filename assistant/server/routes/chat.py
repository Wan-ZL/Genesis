"""Chat API endpoint with Claude API (primary) and OpenAI fallback.

Includes graceful degradation features:
- API fallback: Automatically switches between Claude and OpenAI on failures
- Rate limit handling: Tracks rate limits and uses fallback
- Health tracking: Records API success/failure for smart routing
"""
import logging
import base64
import json
import time
import asyncio
from datetime import datetime
from typing import Optional, List, AsyncGenerator
from pathlib import Path
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

import config
from server.services.memory import MemoryService, DEFAULT_CONVERSATION_ID
from server.services.tools import registry as tool_registry
from server.services.retry import api_retry
from server.services.metrics import metrics
from server.services.tool_suggestions import get_suggestion_service
from server.services.degradation import get_degradation_service
from server.services.encryption import is_encrypted, ENCRYPTED_PREFIX
from server.services.ollama import get_ollama_client, OllamaStatus
from server.services.persona import PersonaService
from server.services.settings import SettingsService
from server.services.memory_extractor import get_memory_extractor
from server.services.user_profile import get_user_profile_service

router = APIRouter()
logger = logging.getLogger(__name__)

# Initialize memory service
memory = MemoryService(config.DATABASE_PATH)
# Initialize persona service
persona_service = PersonaService(config.DATABASE_PATH)
# Initialize settings service
settings_service = SettingsService(config.DATABASE_PATH)
# Initialize memory extractor service
memory_extractor = get_memory_extractor()
# Initialize user profile service
user_profile_service = get_user_profile_service()


async def _extract_facts_async(
    user_message: str,
    assistant_message: str,
    conversation_id: str,
    message_id: str
):
    """Extract facts from a conversation turn asynchronously.

    This runs in the background after the response is sent to the user,
    so it doesn't block the API response.
    """
    try:
        logger.debug(f"Starting async fact extraction for message {message_id}")

        # Extract facts using LLM
        facts = await memory_extractor.extract_facts_from_turn(
            user_message=user_message,
            assistant_message=assistant_message,
            conversation_id=conversation_id,
            message_id=message_id,
            use_lightweight_model=True  # Use cheaper model for extraction
        )

        if facts:
            # Store facts with deduplication
            await memory_extractor.store_facts(facts, deduplicate=True)
            logger.info(f"Extracted and stored {len(facts)} facts from conversation turn")

            # Auto-refresh profile from newly extracted facts
            try:
                await user_profile_service.aggregate_from_facts(memory_extractor)
                logger.debug("Profile auto-refreshed from new facts")
            except Exception as profile_err:
                logger.error(f"Profile aggregation failed: {profile_err}")
        else:
            logger.debug("No facts extracted from conversation turn")

    except Exception as e:
        # Don't let extraction failures break the application
        logger.error(f"Fact extraction failed: {e}", exc_info=True)


class ChatMessage(BaseModel):
    """Chat message request model."""
    message: str
    # conversation_id specifies which conversation to add the message to.
    # Defaults to DEFAULT_CONVERSATION_ID ("main") for backward compatibility.
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
    # The conversation_id the message was added to
    conversation_id: str
    timestamp: str
    model: str  # Which model was used
    # Optional: permission escalation request from tool
    permission_escalation: Optional[PermissionEscalation] = None
    # Optional: suggested tools based on user's message
    suggested_tools: Optional[List[SuggestedTool]] = None


def _validate_api_key_safe(key: str, provider: str) -> bool:
    """Validate that an API key is safe to send to external APIs.

    CRITICAL SECURITY CHECK: This prevents encrypted values from being
    accidentally sent to external APIs, which would:
    1. Fail authentication (useless request)
    2. Leak encrypted data in error messages
    3. Potentially expose encryption format to external services

    Args:
        key: The API key to validate
        provider: Provider name for logging (e.g., "Anthropic", "OpenAI")

    Returns:
        True if the key is safe to use, False otherwise
    """
    if not key:
        return False

    if is_encrypted(key):
        logger.error(
            f"SECURITY BLOCK: Refusing to send encrypted API key to {provider}. "
            f"Key starts with '{ENCRYPTED_PREFIX}'. This indicates a decryption failure. "
            f"Check encryption key file and settings."
        )
        return False

    return True


def get_anthropic_client():
    """Get Anthropic client instance.

    Returns None if:
    - No API key is configured
    - API key appears to be encrypted (safety check)
    """
    if not config.ANTHROPIC_API_KEY:
        return None

    if not _validate_api_key_safe(config.ANTHROPIC_API_KEY, "Anthropic"):
        return None

    from anthropic import Anthropic
    return Anthropic(api_key=config.ANTHROPIC_API_KEY)


def get_openai_client():
    """Get OpenAI client instance.

    Returns None if:
    - No API key is configured
    - API key appears to be encrypted (safety check)
    """
    if not config.OPENAI_API_KEY:
        return None

    if not _validate_api_key_safe(config.OPENAI_API_KEY, "OpenAI"):
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
    Records success/failure to degradation service for smart fallback.
    """
    degradation = get_degradation_service()
    client = get_anthropic_client()
    if not client:
        degradation.record_failure("claude")
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

        try:
            response = client.messages.create(**api_kwargs)
            degradation.record_success("claude")
        except Exception as e:
            # Check if it's a rate limit error
            is_rate_limit = "rate" in str(e).lower() or "429" in str(e)
            retry_after = None
            if hasattr(e, 'response') and hasattr(e.response, 'headers'):
                retry_after = e.response.headers.get('retry-after')
                if retry_after:
                    try:
                        retry_after = int(retry_after)
                    except ValueError:
                        retry_after = None
            degradation.record_failure("claude", is_rate_limit=is_rate_limit, retry_after=retry_after)
            raise

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
    Records success/failure to degradation service for smart fallback.
    """
    degradation = get_degradation_service()
    client = get_openai_client()
    if not client:
        degradation.record_failure("openai")
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

        try:
            completion = client.chat.completions.create(**api_kwargs)
            degradation.record_success("openai")
        except Exception as e:
            # Check if it's a rate limit error
            is_rate_limit = "rate" in str(e).lower() or "429" in str(e)
            retry_after = None
            if hasattr(e, 'response') and hasattr(e.response, 'headers'):
                retry_after = e.response.headers.get('retry-after')
                if retry_after:
                    try:
                        retry_after = int(retry_after)
                    except ValueError:
                        retry_after = None
            degradation.record_failure("openai", is_rate_limit=is_rate_limit, retry_after=retry_after)
            raise

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


async def call_ollama_api(messages: list, file_ids: list, user_message: str, system_prompt: str = "") -> tuple[str, str, Optional[dict]]:
    """Call Ollama API for local model inference with tool support.

    Args:
        messages: Conversation history
        file_ids: List of file IDs to attach (limited support)
        user_message: The current user message
        system_prompt: Optional system prompt with tool suggestions

    Returns:
        tuple: (response_text, model_name, permission_escalation_or_none)

    Note: Local models may have limited multimodal support compared to cloud APIs.
    Tool support depends on the specific model being used.
    """
    degradation = get_degradation_service()
    client = get_ollama_client()

    if not await client.is_available():
        degradation.record_failure("ollama")
        raise ValueError("Ollama service not available")

    model_name = f"ollama:{client.model}"

    # Build messages for Ollama (uses same format as OpenAI)
    ollama_messages = []

    # Add system prompt first if provided
    if system_prompt:
        ollama_messages.append({"role": "system", "content": system_prompt})

    # Add conversation history
    for msg in messages[:-1]:
        ollama_messages.append({
            "role": msg["role"],
            "content": msg["content"]
        })

    # Add current user message
    # Note: Most local models don't support multimodal input well
    if file_ids:
        # Include a note about attached files
        file_note = f"\n[Note: {len(file_ids)} file(s) were attached but may not be viewable by this local model]"
        ollama_messages.append({"role": "user", "content": user_message + file_note})
        logger.warning(f"Ollama: Files attached but local model may not support multimodal input")
    else:
        ollama_messages.append({"role": "user", "content": user_message})

    # Get tools in OpenAI format (Ollama uses the same format)
    tools = tool_registry.to_openai_tools()

    # Check if model supports tools
    models = await client.list_models()
    current_model = next((m for m in models if m.name == client.model), None)
    model_supports_tools = current_model and current_model.supports_tools if current_model else False

    # Loop to handle tool calls
    max_tool_iterations = 5
    for iteration in range(max_tool_iterations):
        try:
            response = await client.chat(
                messages=ollama_messages,
                tools=tools if model_supports_tools else None,
                stream=False
            )
            degradation.record_success("ollama")
        except Exception as e:
            degradation.record_failure("ollama")
            raise

        # Extract response content
        message = response.get("message", {})
        content = message.get("content", "")
        tool_calls = message.get("tool_calls", [])

        if not tool_calls:
            # No tool calls, return the response
            return content, model_name, None

        # Process tool calls
        # Ollama tool calls follow the same format as OpenAI
        ollama_messages.append({
            "role": "assistant",
            "content": content,
            "tool_calls": tool_calls
        })

        for tool_call in tool_calls:
            func = tool_call.get("function", {})
            tool_name = func.get("name", "")
            tool_args_str = func.get("arguments", "{}")
            tool_id = tool_call.get("id", f"call_{iteration}")

            try:
                tool_args = json.loads(tool_args_str) if isinstance(tool_args_str, str) else tool_args_str
            except json.JSONDecodeError:
                tool_args = {}

            logger.info(f"Ollama calling tool: {tool_name} with input: {tool_args}")

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
                return escalation_msg, model_name, escalation
            else:
                tool_result = f"Error: {result['error']}"

            ollama_messages.append({
                "role": "tool",
                "tool_call_id": tool_id,
                "content": tool_result,
            })

    # If we exit the loop, return what we have
    return "I apologize, I couldn't complete the task after multiple tool attempts.", model_name, None


# ============================================================================
# Streaming API Support
# ============================================================================


class StreamEvent(BaseModel):
    """SSE event for streaming responses."""
    event: str  # "start", "token", "tool_call", "tool_result", "done", "error"
    data: dict


def format_sse(event: str, data: dict) -> str:
    """Format data as Server-Sent Event."""
    json_data = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {json_data}\n\n"


async def stream_claude_response(
    messages: list,
    file_ids: list,
    user_message: str,
    system_prompt: str = ""
) -> AsyncGenerator[str, None]:
    """Stream response from Claude API with tool call support.

    Yields SSE-formatted events:
    - start: Initial metadata (model info)
    - token: Text content chunk
    - tool_call: Tool is being called
    - tool_result: Tool execution result
    - done: Stream complete with final metadata
    - error: Error occurred
    """
    client = get_anthropic_client()
    if not client:
        yield format_sse("error", {"message": "Anthropic client not available"})
        return

    # Convert message history for Claude format
    claude_messages = []
    for msg in messages[:-1]:
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

    yield format_sse("start", {"model": config.CLAUDE_MODEL, "provider": "anthropic"})

    # Track accumulated text and tool calls for the conversation loop
    max_tool_iterations = 5
    accumulated_text = ""

    for iteration in range(max_tool_iterations):
        api_kwargs = {
            "model": config.CLAUDE_MODEL,
            "max_tokens": 4096,
            "messages": claude_messages,
            "stream": True,  # Enable streaming
        }
        if system_prompt:
            api_kwargs["system"] = system_prompt
        if tools:
            api_kwargs["tools"] = tools

        try:
            current_text = ""
            tool_use_blocks = []
            current_tool_use = None

            with client.messages.stream(**api_kwargs) as stream:
                for event in stream:
                    # Handle different event types
                    if event.type == "content_block_start":
                        if hasattr(event.content_block, "type"):
                            if event.content_block.type == "tool_use":
                                current_tool_use = {
                                    "id": event.content_block.id,
                                    "name": event.content_block.name,
                                    "input": ""
                                }
                    elif event.type == "content_block_delta":
                        if hasattr(event.delta, "text"):
                            # Text delta
                            text_chunk = event.delta.text
                            current_text += text_chunk
                            yield format_sse("token", {"text": text_chunk})
                        elif hasattr(event.delta, "partial_json"):
                            # Tool input delta
                            if current_tool_use:
                                current_tool_use["input"] += event.delta.partial_json
                    elif event.type == "content_block_stop":
                        if current_tool_use:
                            # Parse tool input and add to list
                            try:
                                current_tool_use["input"] = json.loads(current_tool_use["input"])
                            except json.JSONDecodeError:
                                current_tool_use["input"] = {}
                            tool_use_blocks.append(current_tool_use)
                            current_tool_use = None

            accumulated_text += current_text

            # If no tool calls, we're done
            if not tool_use_blocks:
                break

            # Process tool calls
            tool_results = []
            for tool_block in tool_use_blocks:
                tool_name = tool_block["name"]
                tool_input = tool_block["input"]
                tool_id = tool_block["id"]

                yield format_sse("tool_call", {
                    "name": tool_name,
                    "input": tool_input
                })

                logger.info(f"Claude streaming: calling tool {tool_name}")
                result = tool_registry.execute(tool_name, **tool_input)
                metrics.record_tool_call(tool_name)

                if result["success"]:
                    tool_result_content = str(result["result"])
                    yield format_sse("tool_result", {
                        "name": tool_name,
                        "success": True,
                        "result": tool_result_content
                    })
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": tool_result_content,
                    })
                elif "permission_escalation" in result:
                    escalation = result["permission_escalation"]
                    yield format_sse("tool_result", {
                        "name": tool_name,
                        "success": False,
                        "permission_escalation": escalation
                    })
                    # Return escalation message
                    escalation_msg = (
                        f"I need elevated permissions to use the **{tool_name}** tool.\n\n"
                        f"**Current permission level:** {escalation['current_level_name']}\n"
                        f"**Required permission level:** {escalation['required_level_name']}"
                    )
                    yield format_sse("token", {"text": escalation_msg})
                    accumulated_text += escalation_msg
                    yield format_sse("done", {
                        "total_text": accumulated_text,
                        "model": config.CLAUDE_MODEL,
                        "permission_escalation": escalation
                    })
                    return
                else:
                    error_content = f"Error: {result['error']}"
                    yield format_sse("tool_result", {
                        "name": tool_name,
                        "success": False,
                        "error": result["error"]
                    })
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": error_content,
                        "is_error": True,
                    })

            # Build response content including tool use blocks for conversation continuation
            response_content = []
            if current_text:
                response_content.append({"type": "text", "text": current_text})
            for tb in tool_use_blocks:
                response_content.append({
                    "type": "tool_use",
                    "id": tb["id"],
                    "name": tb["name"],
                    "input": tb["input"]
                })

            # Add messages for next iteration
            claude_messages.append({
                "role": "assistant",
                "content": response_content,
            })
            claude_messages.append({
                "role": "user",
                "content": tool_results,
            })

        except Exception as e:
            logger.error(f"Claude streaming error: {e}")
            yield format_sse("error", {"message": str(e)})
            return

    yield format_sse("done", {
        "total_text": accumulated_text,
        "model": config.CLAUDE_MODEL
    })


async def stream_openai_response(
    messages: list,
    file_ids: list,
    user_message: str,
    system_prompt: str = ""
) -> AsyncGenerator[str, None]:
    """Stream response from OpenAI API with tool call support.

    Yields SSE-formatted events:
    - start: Initial metadata (model info)
    - token: Text content chunk
    - tool_call: Tool is being called
    - tool_result: Tool execution result
    - done: Stream complete with final metadata
    - error: Error occurred
    """
    client = get_openai_client()
    if not client:
        yield format_sse("error", {"message": "OpenAI client not available"})
        return

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

    yield format_sse("start", {"model": config.OPENAI_MODEL, "provider": "openai"})

    max_tool_iterations = 5
    accumulated_text = ""

    for iteration in range(max_tool_iterations):
        api_kwargs = {
            "model": config.OPENAI_MODEL,
            "messages": messages,
            "stream": True,
        }
        if tools:
            api_kwargs["tools"] = tools

        try:
            current_text = ""
            tool_calls = {}  # id -> {name, arguments}

            stream = client.chat.completions.create(**api_kwargs)

            for chunk in stream:
                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta

                # Handle text content
                if delta.content:
                    current_text += delta.content
                    yield format_sse("token", {"text": delta.content})

                # Handle tool calls
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        tc_id = tc.id or list(tool_calls.keys())[-1] if tool_calls else None
                        if tc.id:
                            # New tool call
                            tool_calls[tc.id] = {
                                "name": tc.function.name if tc.function else "",
                                "arguments": tc.function.arguments if tc.function else ""
                            }
                        elif tc_id and tc.function:
                            # Continuation of existing tool call
                            if tc.function.name:
                                tool_calls[tc_id]["name"] = tc.function.name
                            if tc.function.arguments:
                                tool_calls[tc_id]["arguments"] += tc.function.arguments

            accumulated_text += current_text

            # If no tool calls, we're done
            if not tool_calls:
                break

            # Process tool calls
            tool_call_list = []
            for tc_id, tc_data in tool_calls.items():
                try:
                    tool_args = json.loads(tc_data["arguments"])
                except json.JSONDecodeError:
                    tool_args = {}

                tool_call_list.append({
                    "id": tc_id,
                    "type": "function",
                    "function": {
                        "name": tc_data["name"],
                        "arguments": tc_data["arguments"]
                    }
                })

            # Add assistant message with tool calls
            messages.append({
                "role": "assistant",
                "content": current_text or None,
                "tool_calls": tool_call_list
            })

            # Execute tools and add results
            for tc_id, tc_data in tool_calls.items():
                tool_name = tc_data["name"]
                try:
                    tool_args = json.loads(tc_data["arguments"])
                except json.JSONDecodeError:
                    tool_args = {}

                yield format_sse("tool_call", {
                    "name": tool_name,
                    "input": tool_args
                })

                logger.info(f"OpenAI streaming: calling tool {tool_name}")
                result = tool_registry.execute(tool_name, **tool_args)
                metrics.record_tool_call(tool_name)

                if result["success"]:
                    tool_result_content = str(result["result"])
                    yield format_sse("tool_result", {
                        "name": tool_name,
                        "success": True,
                        "result": tool_result_content
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": tool_result_content,
                    })
                elif "permission_escalation" in result:
                    escalation = result["permission_escalation"]
                    yield format_sse("tool_result", {
                        "name": tool_name,
                        "success": False,
                        "permission_escalation": escalation
                    })
                    escalation_msg = (
                        f"I need elevated permissions to use the **{tool_name}** tool.\n\n"
                        f"**Current permission level:** {escalation['current_level_name']}\n"
                        f"**Required permission level:** {escalation['required_level_name']}"
                    )
                    yield format_sse("token", {"text": escalation_msg})
                    accumulated_text += escalation_msg
                    yield format_sse("done", {
                        "total_text": accumulated_text,
                        "model": config.OPENAI_MODEL,
                        "permission_escalation": escalation
                    })
                    return
                else:
                    error_content = f"Error: {result['error']}"
                    yield format_sse("tool_result", {
                        "name": tool_name,
                        "success": False,
                        "error": result["error"]
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": error_content,
                    })

        except Exception as e:
            logger.error(f"OpenAI streaming error: {e}")
            yield format_sse("error", {"message": str(e)})
            return

    yield format_sse("done", {
        "total_text": accumulated_text,
        "model": config.OPENAI_MODEL
    })


async def stream_ollama_response(
    messages: list,
    file_ids: list,
    user_message: str,
    system_prompt: str = ""
) -> AsyncGenerator[str, None]:
    """Stream response from Ollama with tool call support.

    Yields SSE-formatted events:
    - start: Initial metadata (model info)
    - token: Text content chunk
    - tool_call: Tool is being called
    - tool_result: Tool execution result
    - done: Stream complete with final metadata
    - error: Error occurred
    """
    client = get_ollama_client()
    if not await client.is_available():
        yield format_sse("error", {"message": "Ollama service not available"})
        return

    model_name = f"ollama:{client.model}"

    # Build messages for Ollama
    ollama_messages = []

    if system_prompt:
        ollama_messages.append({"role": "system", "content": system_prompt})

    for msg in messages[:-1]:
        ollama_messages.append({
            "role": msg["role"],
            "content": msg["content"]
        })

    if file_ids:
        file_note = f"\n[Note: {len(file_ids)} file(s) were attached but may not be viewable by this local model]"
        ollama_messages.append({"role": "user", "content": user_message + file_note})
    else:
        ollama_messages.append({"role": "user", "content": user_message})

    # Get tools in OpenAI format
    tools = tool_registry.to_openai_tools()

    # Check if model supports tools
    models = await client.list_models()
    current_model = next((m for m in models if m.name == client.model), None)
    model_supports_tools = current_model and current_model.supports_tools if current_model else False

    yield format_sse("start", {"model": model_name, "provider": "ollama"})

    max_tool_iterations = 5
    accumulated_text = ""

    for iteration in range(max_tool_iterations):
        try:
            current_text = ""
            tool_calls = []

            # Stream from Ollama
            stream_generator = await client.chat(
                messages=ollama_messages,
                tools=tools if model_supports_tools else None,
                stream=True
            )

            async for chunk in stream_generator:
                if chunk.get("done"):
                    # Final chunk may contain tool calls
                    message = chunk.get("message", {})
                    if message.get("tool_calls"):
                        tool_calls = message["tool_calls"]
                    break

                message = chunk.get("message", {})
                content = message.get("content", "")

                if content:
                    current_text += content
                    yield format_sse("token", {"text": content})

                # Check for tool calls in streaming response
                if message.get("tool_calls"):
                    tool_calls.extend(message["tool_calls"])

            accumulated_text += current_text

            # If no tool calls, we're done
            if not tool_calls:
                break

            # Process tool calls
            ollama_messages.append({
                "role": "assistant",
                "content": current_text,
                "tool_calls": tool_calls
            })

            for tool_call in tool_calls:
                func = tool_call.get("function", {})
                tool_name = func.get("name", "")
                tool_args_str = func.get("arguments", "{}")
                tool_id = tool_call.get("id", f"call_{iteration}")

                try:
                    tool_args = json.loads(tool_args_str) if isinstance(tool_args_str, str) else tool_args_str
                except json.JSONDecodeError:
                    tool_args = {}

                yield format_sse("tool_call", {
                    "name": tool_name,
                    "input": tool_args
                })

                logger.info(f"Ollama streaming: calling tool {tool_name}")
                result = tool_registry.execute(tool_name, **tool_args)
                metrics.record_tool_call(tool_name)

                if result["success"]:
                    tool_result_content = str(result["result"])
                    yield format_sse("tool_result", {
                        "name": tool_name,
                        "success": True,
                        "result": tool_result_content
                    })
                    ollama_messages.append({
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "content": tool_result_content,
                    })
                elif "permission_escalation" in result:
                    escalation = result["permission_escalation"]
                    yield format_sse("tool_result", {
                        "name": tool_name,
                        "success": False,
                        "permission_escalation": escalation
                    })
                    escalation_msg = (
                        f"I need elevated permissions to use the **{tool_name}** tool.\n\n"
                        f"**Current permission level:** {escalation['current_level_name']}\n"
                        f"**Required permission level:** {escalation['required_level_name']}"
                    )
                    yield format_sse("token", {"text": escalation_msg})
                    accumulated_text += escalation_msg
                    yield format_sse("done", {
                        "total_text": accumulated_text,
                        "model": model_name,
                        "permission_escalation": escalation
                    })
                    return
                else:
                    error_content = f"Error: {result['error']}"
                    yield format_sse("tool_result", {
                        "name": tool_name,
                        "success": False,
                        "error": result["error"]
                    })
                    ollama_messages.append({
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "content": error_content,
                    })

        except Exception as e:
            logger.error(f"Ollama streaming error: {e}")
            yield format_sse("error", {"message": str(e)})
            return

    yield format_sse("done", {
        "total_text": accumulated_text,
        "model": model_name
    })


@router.post("/chat/stream")
async def chat_stream(request: ChatMessage):
    """Stream chat response using Server-Sent Events (SSE).

    This endpoint provides real-time streaming of AI responses as they are generated.
    It supports both Claude and OpenAI APIs with automatic fallback.

    Event types:
    - start: Stream started, includes model info
    - token: Text chunk from the AI
    - tool_call: Tool is being invoked
    - tool_result: Result from tool execution
    - done: Stream complete, includes total text
    - error: An error occurred

    Messages are stored in the specified conversation (defaults to "main").
    """
    start_time = time.time()

    # Use specified conversation_id or default to "main"
    conversation_id = request.conversation_id or DEFAULT_CONVERSATION_ID

    # Ensure the conversation exists
    if conversation_id == DEFAULT_CONVERSATION_ID:
        await memory._ensure_initialized()
        await memory._ensure_default_conversation()
    else:
        exists = await memory.conversation_exists(conversation_id)
        if not exists:
            raise HTTPException(status_code=404, detail="Conversation not found")

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

    # Auto-title conversation from first user message
    conv = await memory.get_conversation(conversation_id)
    if conv and conv.get("title") in ("New Conversation", "New conversation") and len(conv.get("messages", [])) == 1:
        await memory.auto_title_conversation(conversation_id, request.message)

    async def generate_response() -> AsyncGenerator[str, None]:
        """Generate streaming response with error handling and memory persistence."""
        accumulated_response = ""
        model_used = None
        has_error = False

        try:
            # Get conversation history
            if conversation_id == DEFAULT_CONVERSATION_ID:
                messages, context_meta = await memory.get_context_for_api()
            else:
                messages = await memory.get_conversation_messages(conversation_id)
                context_meta = {"total_messages": len(messages) - 1, "summarized_count": 0, "verbatim_count": len(messages) - 1}

            if context_meta["summarized_count"] > 0:
                logger.info(
                    f"Context: {context_meta['total_messages']} total msgs, "
                    f"{context_meta['summarized_count']} summarized, "
                    f"{context_meta['verbatim_count']} verbatim"
                )

            # Get default system prompt from settings
            settings = await settings_service.get_all()
            default_system_prompt = settings.get("system_prompt", "")

            # Get effective system prompt for this conversation
            base_system_prompt = await persona_service.get_active_system_prompt(
                conversation_id=conversation_id,
                default_system_prompt=default_system_prompt
            )

            # Recall relevant facts for long-term memory context
            recalled_facts = await memory_extractor.recall_facts(
                query=request.message,  # Use user message for relevance
                limit=10  # Top 10 most relevant facts
            )
            facts_context = memory_extractor.format_facts_for_system_prompt(recalled_facts)
            if facts_context:
                logger.info(f"Recalled {len(recalled_facts)} relevant facts for context")

            # Get user profile summary for context
            profile_summary = await user_profile_service.get_profile_summary()
            if profile_summary:
                logger.info("Injecting user profile summary into system prompt")

            # Analyze user message for relevant tool suggestions
            suggestion_service = get_suggestion_service()
            suggestions = suggestion_service.analyze_message(request.message)

            # Build system prompt (base + profile + facts + tool suggestions)
            system_parts = [base_system_prompt]

            if profile_summary:
                system_parts.append(profile_summary)

            if facts_context:
                system_parts.append(facts_context)

            if suggestions:
                suggestion_text = suggestion_service.get_system_prompt_injection(suggestions)
                system_parts.append(suggestion_text)
                logger.info(f"Suggesting {len(suggestions)} relevant tools: {[s.name for s in suggestions]}")
            else:
                summary = suggestion_service.get_available_tools_summary()
                if summary:
                    system_parts.append(summary)

            system_prompt = "\n\n".join(system_parts)

            # Smart API selection using degradation service
            degradation = get_degradation_service()
            preferred_api = "claude" if config.USE_CLAUDE else "openai"
            selected_api = degradation.get_preferred_api(preferred_api)

            stream_generator = None

            # Try selected API first
            if selected_api == "ollama" and config.OLLAMA_ENABLED:
                try:
                    ollama_client = get_ollama_client()
                    logger.info(f"Starting Ollama stream with model {ollama_client.model}")
                    if degradation.mode.name not in ("NORMAL", "LOCAL_ONLY"):
                        logger.info(f"Degradation mode: {degradation.mode.name}")
                    stream_generator = stream_ollama_response(
                        messages, request.file_ids or [], request.message, system_prompt
                    )
                    model_used = f"ollama:{ollama_client.model}"
                except Exception as e:
                    logger.warning(f"Ollama streaming init failed: {e}")
                    stream_generator = None
            elif selected_api == "claude" and config.ANTHROPIC_API_KEY:
                try:
                    logger.info(f"Starting Claude stream with model {config.CLAUDE_MODEL}")
                    if degradation.mode.name not in ("NORMAL", "OPENAI_UNAVAILABLE"):
                        logger.info(f"Degradation mode: {degradation.mode.name}")
                    stream_generator = stream_claude_response(
                        messages, request.file_ids or [], request.message, system_prompt
                    )
                    model_used = config.CLAUDE_MODEL
                except Exception as e:
                    logger.warning(f"Claude streaming init failed: {e}")
                    stream_generator = None
            elif selected_api == "openai" and config.OPENAI_API_KEY:
                try:
                    logger.info(f"Starting OpenAI stream with model {config.OPENAI_MODEL}")
                    if degradation.mode.name not in ("NORMAL", "CLAUDE_UNAVAILABLE"):
                        logger.info(f"Degradation mode: {degradation.mode.name}")
                    stream_generator = stream_openai_response(
                        messages, request.file_ids or [], request.message, system_prompt
                    )
                    model_used = config.OPENAI_MODEL
                except Exception as e:
                    logger.warning(f"OpenAI streaming init failed: {e}")
                    stream_generator = None

            # Fallback chain: primary cloud -> secondary cloud -> ollama
            if stream_generator is None:
                fallback_api = "openai" if selected_api == "claude" else "claude"
                if fallback_api == "openai" and config.OPENAI_API_KEY:
                    try:
                        logger.info(f"Falling back to OpenAI stream with model {config.OPENAI_MODEL}")
                        stream_generator = stream_openai_response(
                            messages, request.file_ids or [], request.message, system_prompt
                        )
                        model_used = config.OPENAI_MODEL
                    except Exception as e:
                        logger.warning(f"OpenAI fallback failed: {e}")
                elif fallback_api == "claude" and config.ANTHROPIC_API_KEY:
                    try:
                        logger.info(f"Falling back to Claude stream with model {config.CLAUDE_MODEL}")
                        stream_generator = stream_claude_response(
                            messages, request.file_ids or [], request.message, system_prompt
                        )
                        model_used = config.CLAUDE_MODEL
                    except Exception as e:
                        logger.warning(f"Claude fallback failed: {e}")

            # Final fallback to Ollama if cloud APIs failed
            if stream_generator is None and config.OLLAMA_ENABLED:
                try:
                    ollama_client = get_ollama_client()
                    if await ollama_client.is_available():
                        logger.info(f"Final fallback to Ollama with model {ollama_client.model}")
                        stream_generator = stream_ollama_response(
                            messages, request.file_ids or [], request.message, system_prompt
                        )
                        model_used = f"ollama:{ollama_client.model}"
                except Exception as e:
                    logger.warning(f"Ollama fallback failed: {e}")

            if stream_generator is None:
                raise ValueError("No API available for streaming")

            # Forward events from the stream
            async for event_str in stream_generator:
                yield event_str

                # Extract accumulated text from done event for memory storage
                if event_str.startswith("event: done"):
                    try:
                        data_line = event_str.split("data: ", 1)[1].split("\n")[0]
                        done_data = json.loads(data_line)
                        accumulated_response = done_data.get("total_text", "")
                    except (IndexError, json.JSONDecodeError):
                        pass
                elif event_str.startswith("event: error"):
                    has_error = True

        except Exception as e:
            logger.error(f"Streaming error: {e}")
            yield format_sse("error", {"message": str(e)})
            has_error = True

        # Save assistant response to memory if we got something
        if accumulated_response:
            message_id = await memory.add_message(conversation_id, "assistant", accumulated_response)
            logger.info(f"Stream completed, saved {len(accumulated_response)} chars to memory")

            # Extract facts from this conversation turn (async, non-blocking)
            asyncio.create_task(
                _extract_facts_async(
                    user_message=request.message,
                    assistant_message=accumulated_response,
                    conversation_id=conversation_id,
                    message_id=message_id
                )
            )
        elif has_error:
            # Remove user message if streaming failed completely
            await memory.remove_last_message(conversation_id)

        # Record metrics
        latency_ms = (time.time() - start_time) * 1000
        metrics.record_request("/api/chat/stream", latency_ms, success=not has_error)
        if has_error:
            metrics.record_error("/api/chat/stream", "StreamError")

    return StreamingResponse(
        generate_response(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatMessage):
    """Send a message and get AI response (Claude primary, OpenAI fallback).

    Messages are stored in the specified conversation (defaults to "main").
    The first user message in a new conversation auto-generates its title.
    """
    start_time = time.time()

    # Use specified conversation_id or default to "main"
    conversation_id = request.conversation_id or DEFAULT_CONVERSATION_ID

    # Ensure the conversation exists
    if conversation_id == DEFAULT_CONVERSATION_ID:
        await memory._ensure_initialized()
        await memory._ensure_default_conversation()
    else:
        exists = await memory.conversation_exists(conversation_id)
        if not exists:
            raise HTTPException(status_code=404, detail="Conversation not found")

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

    # Auto-title conversation from first user message if it's a non-default conversation
    # with the default "New Conversation" title
    conv = await memory.get_conversation(conversation_id)
    if conv and conv.get("title") in ("New Conversation", "New conversation") and len(conv.get("messages", [])) == 1:
        await memory.auto_title_conversation(conversation_id, request.message)

    try:
        # Get conversation history
        if conversation_id == DEFAULT_CONVERSATION_ID:
            messages, context_meta = await memory.get_context_for_api()
        else:
            messages = await memory.get_conversation_messages(conversation_id)
            context_meta = {"total_messages": len(messages) - 1, "summarized_count": 0, "verbatim_count": len(messages) - 1}

        if context_meta["summarized_count"] > 0:
            logger.info(
                f"Context: {context_meta['total_messages']} total msgs, "
                f"{context_meta['summarized_count']} summarized, "
                f"{context_meta['verbatim_count']} verbatim"
            )

        # Get default system prompt from settings
        settings = await settings_service.get_all()
        default_system_prompt = settings.get("system_prompt", "")

        # Get effective system prompt for this conversation
        base_system_prompt = await persona_service.get_active_system_prompt(
            conversation_id=conversation_id,
            default_system_prompt=default_system_prompt
        )

        # Recall relevant facts for long-term memory context
        recalled_facts = await memory_extractor.recall_facts(
            query=request.message,  # Use user message for relevance
            limit=10  # Top 10 most relevant facts
        )
        facts_context = memory_extractor.format_facts_for_system_prompt(recalled_facts)
        if facts_context:
            logger.info(f"Recalled {len(recalled_facts)} relevant facts for context")

        # Get user profile summary for context
        profile_summary = await user_profile_service.get_profile_summary()
        if profile_summary:
            logger.info("Injecting user profile summary into system prompt")

        # Analyze user message for relevant tool suggestions
        suggestion_service = get_suggestion_service()
        suggestions = suggestion_service.analyze_message(request.message)

        # Build system prompt (base + profile + facts + tool suggestions)
        system_parts = [base_system_prompt]

        if profile_summary:
            system_parts.append(profile_summary)

        if facts_context:
            system_parts.append(facts_context)

        if suggestions:
            suggestion_text = suggestion_service.get_system_prompt_injection(suggestions)
            system_parts.append(suggestion_text)
            logger.info(f"Suggesting {len(suggestions)} relevant tools: {[s.name for s in suggestions]}")
        else:
            # Include general tool summary when no specific suggestions
            summary = suggestion_service.get_available_tools_summary()
            if summary:
                system_parts.append(summary)

        system_prompt = "\n\n".join(system_parts)

        # Smart API selection using degradation service
        degradation = get_degradation_service()

        # Check network availability first
        network_available = await degradation.check_network()
        if not network_available:
            logger.warning("Network unavailable, API calls may fail")

        # Determine preferred API based on config and health
        preferred_api = "claude" if config.USE_CLAUDE else "openai"
        selected_api = degradation.get_preferred_api(preferred_api)

        model_used = None
        assistant_message = None
        permission_escalation = None
        last_error = None

        # Try selected API first
        if selected_api == "ollama" and config.OLLAMA_ENABLED:
            try:
                ollama_client = get_ollama_client()
                logger.info(f"Calling Ollama API with model {ollama_client.model}, files: {request.file_ids or []}")
                if degradation.mode.name not in ("NORMAL", "LOCAL_ONLY"):
                    logger.info(f"Degradation mode: {degradation.mode.name}")
                assistant_message, model_used, permission_escalation = await call_ollama_api(
                    messages, request.file_ids or [], request.message, system_prompt
                )
            except Exception as e:
                last_error = e
                logger.warning(f"Ollama API failed: {e}")

        elif selected_api == "claude" and config.ANTHROPIC_API_KEY:
            try:
                logger.info(f"Calling Claude API with model {config.CLAUDE_MODEL}, files: {request.file_ids or []}")
                if degradation.mode.name not in ("NORMAL", "OPENAI_UNAVAILABLE"):
                    logger.info(f"Degradation mode: {degradation.mode.name}")
                assistant_message, model_used, permission_escalation = await call_claude_api(
                    messages, request.file_ids or [], request.message, system_prompt
                )
            except Exception as e:
                last_error = e
                logger.warning(f"Claude API failed: {e}")

        elif selected_api == "openai" and config.OPENAI_API_KEY:
            try:
                logger.info(f"Calling OpenAI API with model {config.OPENAI_MODEL}, files: {request.file_ids or []}")
                if degradation.mode.name not in ("NORMAL", "CLAUDE_UNAVAILABLE"):
                    logger.info(f"Degradation mode: {degradation.mode.name}")
                assistant_message, model_used, permission_escalation = await call_openai_api(
                    messages, request.file_ids or [], request.message, system_prompt
                )
            except Exception as e:
                last_error = e
                logger.warning(f"OpenAI API failed: {e}")

        # Cloud API fallback chain if primary failed (not if using Ollama)
        if assistant_message is None and selected_api != "ollama":
            fallback_api = "openai" if selected_api == "claude" else "claude"

            if fallback_api == "openai" and config.OPENAI_API_KEY:
                try:
                    logger.info(f"Falling back to OpenAI API with model {config.OPENAI_MODEL}")
                    assistant_message, model_used, permission_escalation = await call_openai_api(
                        messages, request.file_ids or [], request.message, system_prompt
                    )
                except Exception as e:
                    last_error = e
                    logger.error(f"OpenAI fallback also failed: {e}")

            elif fallback_api == "claude" and config.ANTHROPIC_API_KEY:
                try:
                    logger.info(f"Falling back to Claude API with model {config.CLAUDE_MODEL}")
                    assistant_message, model_used, permission_escalation = await call_claude_api(
                        messages, request.file_ids or [], request.message, system_prompt
                    )
                except Exception as e:
                    last_error = e
                    logger.error(f"Claude fallback also failed: {e}")

        # Final fallback to Ollama if all cloud APIs failed
        if assistant_message is None and config.OLLAMA_ENABLED:
            try:
                ollama_client = get_ollama_client()
                if await ollama_client.is_available():
                    logger.info(f"Final fallback to Ollama with model {ollama_client.model}")
                    assistant_message, model_used, permission_escalation = await call_ollama_api(
                        messages, request.file_ids or [], request.message, system_prompt
                    )
            except Exception as e:
                last_error = e
                logger.error(f"Ollama fallback also failed: {e}")

        # If still no response, raise the last error
        if assistant_message is None:
            raise last_error or ValueError("No API available")

        # Save assistant response
        message_id = await memory.add_message(conversation_id, "assistant", assistant_message)

        logger.info(f"Chat completed in conversation {conversation_id} using {model_used}")

        # Extract facts from this conversation turn (async, non-blocking)
        asyncio.create_task(
            _extract_facts_async(
                user_message=request.message,
                assistant_message=assistant_message,
                conversation_id=conversation_id,
                message_id=message_id
            )
        )

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
            conversation_id=conversation_id,
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
        await memory.remove_last_message(conversation_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversation")
async def get_the_conversation():
    """Get the default 'main' conversation with messages.

    This endpoint returns messages from the default conversation.
    For backward compatibility with single-conversation clients.
    """
    conversation = await memory.get_conversation(DEFAULT_CONVERSATION_ID)
    if not conversation:
        # Auto-create if doesn't exist
        await memory._ensure_default_conversation()
        conversation = await memory.get_conversation(DEFAULT_CONVERSATION_ID)
    return conversation


@router.get("/conversations")
async def list_conversations():
    """List all conversations with metadata.

    Returns conversations sorted by most recently active, including:
    - id, title, created_at, updated_at, message_count, preview
    """
    # Ensure default conversation exists
    await memory._ensure_initialized()
    await memory._ensure_default_conversation()

    conversations = await memory.list_conversations()
    return {"conversations": conversations}


class CreateConversationRequest(BaseModel):
    """Request body for creating a new conversation."""
    title: Optional[str] = None


@router.post("/conversations")
async def create_conversation(request: CreateConversationRequest = None):
    """Create a new conversation.

    Args:
        request: Optional body with title field

    Returns:
        The newly created conversation object
    """
    title = None
    if request and request.title:
        title = request.title

    conversation_id = await memory.create_conversation(title=title or "New Conversation")
    conversation = await memory.get_conversation(conversation_id)
    return conversation


class RenameConversationRequest(BaseModel):
    """Request body for renaming a conversation."""
    title: str


@router.put("/conversations/{conversation_id}")
async def rename_conversation(conversation_id: str, request: RenameConversationRequest):
    """Rename a conversation.

    Args:
        conversation_id: The conversation to rename
        request: Body with new title

    Returns:
        The updated conversation object
    """
    if not request.title or not request.title.strip():
        raise HTTPException(status_code=400, detail="Title cannot be empty")

    success = await memory.rename_conversation(conversation_id, request.title.strip())
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conversation = await memory.get_conversation(conversation_id)
    return conversation


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """Delete a conversation and all its messages.

    Args:
        conversation_id: The conversation to delete

    Returns:
        Success confirmation
    """
    if conversation_id == DEFAULT_CONVERSATION_ID:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete the default conversation. Use clear instead."
        )

    success = await memory.delete_conversation(conversation_id)
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return {"success": True, "deleted": conversation_id}


@router.get("/conversation/export")
async def export_conversation():
    """Export the default conversation in a portable JSON format.

    Returns a JSON object with:
    - version: Export format version
    - exported_at: ISO timestamp
    - message_count: Number of messages
    - messages: Array of message objects with role, content, timestamp
    - files: Array of file references (metadata only, not content)

    The export can be imported on another instance or after reinstall.
    """
    export_data = await memory.export_conversation()
    return export_data


class ImportRequest(BaseModel):
    """Request body for importing conversation data."""
    version: str = "1.0"
    messages: list
    mode: str = "merge"  # "merge" or "replace"


@router.post("/conversation/import")
async def import_conversation(request: ImportRequest):
    """Import conversation from exported JSON format.

    Args:
        request: ImportRequest with:
            - version: Export format version (must be "1.0")
            - messages: Array of message objects
            - mode: "merge" (default, skip duplicates) or "replace" (clear existing)

    Returns:
        Import statistics with counts of imported/skipped messages
    """
    try:
        result = await memory.import_conversation(
            data={
                "version": request.version,
                "messages": request.messages
            },
            mode=request.mode
        )
        return {
            "success": True,
            **result
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    """Get a conversation by ID with all its messages.

    Args:
        conversation_id: The conversation to retrieve

    Returns:
        Conversation object with id, title, messages, timestamps
    """
    conversation = await memory.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.get("/messages/search")
async def search_messages(
    q: str,
    limit: int = 50,
    offset: int = 0,
    cross_conversation: bool = False
):
    """Search messages by keyword across conversations or within a specific one.

    Args:
        q: Search query (required)
        limit: Maximum results (default 50, max 100)
        offset: Pagination offset
        cross_conversation: If true, search all conversations. If false, search only the default conversation.

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

    # Search across all conversations or just the default one
    conversation_id = None if cross_conversation else DEFAULT_CONVERSATION_ID
    results = await memory.search_messages(
        query=q.strip(),
        conversation_id=conversation_id,
        limit=limit,
        offset=offset
    )

    return {
        "query": q.strip(),
        "count": len(results),
        "cross_conversation": cross_conversation,
        "results": results
    }


@router.delete("/conversations/{conversation_id}/messages/{message_id}")
async def delete_message(conversation_id: str, message_id: str):
    """Delete a single message from a conversation.

    Args:
        conversation_id: The conversation containing the message
        message_id: The message to delete

    Returns:
        Success confirmation
    """
    success = await memory.delete_message(conversation_id, message_id)
    if not success:
        raise HTTPException(status_code=404, detail="Message not found")

    return {"success": True, "deleted": message_id}
