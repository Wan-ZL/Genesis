"""Ollama API client for local model inference.

Ollama provides local LLM inference with models like Llama, Mistral, etc.
This service integrates with the assistant's chat API as a fallback when
cloud APIs (OpenAI/Claude) are unavailable or when running in local-only mode.

Key features:
- OpenAI-compatible API (reuses much of the existing code patterns)
- Streaming support for real-time responses
- Tool calling support (if model supports it)
- Automatic model detection and capability checking
- Health monitoring for graceful degradation
"""

import logging
import httpx
import json
import asyncio
from typing import Optional, List, Dict, Any, AsyncGenerator
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

import config

logger = logging.getLogger(__name__)


class OllamaStatus(Enum):
    """Status of the Ollama service."""
    UNKNOWN = "unknown"
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    NO_MODELS = "no_models"


@dataclass
class OllamaModelInfo:
    """Information about an available Ollama model."""
    name: str
    size: int = 0
    digest: str = ""
    modified_at: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    @property
    def supports_tools(self) -> bool:
        """Check if model likely supports tool calling.

        Most newer models (Llama 3+, Mistral, etc.) support function calling.
        """
        name_lower = self.name.lower()
        # Models known to support tool calling
        tool_capable = [
            "llama3", "llama-3", "mistral", "mixtral",
            "codellama", "qwen", "yi", "phi"
        ]
        return any(tc in name_lower for tc in tool_capable)


class OllamaClient:
    """Client for interacting with the Ollama API.

    Ollama provides a REST API for local model inference.
    API documentation: https://github.com/ollama/ollama/blob/main/docs/api.md
    """

    def __init__(
        self,
        host: str = None,
        model: str = None,
        timeout: int = None
    ):
        """Initialize Ollama client.

        Args:
            host: Ollama API host (default: from config or http://localhost:11434)
            model: Default model to use (default: from config or llama3.2:3b)
            timeout: Request timeout in seconds (default: from config or 120)
        """
        self.host = (host or config.OLLAMA_HOST).rstrip("/")
        self.model = model or config.OLLAMA_MODEL
        self.timeout = timeout or config.OLLAMA_TIMEOUT

        self._status = OllamaStatus.UNKNOWN
        self._last_check: Optional[datetime] = None
        self._available_models: List[OllamaModelInfo] = []
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout, connect=10.0)
            )
        return self._http_client

    async def close(self):
        """Close the HTTP client."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None

    async def check_health(self) -> OllamaStatus:
        """Check if Ollama is running and has models available.

        Returns:
            OllamaStatus indicating the service state
        """
        try:
            client = await self._get_client()

            # Check if Ollama is running
            response = await client.get(f"{self.host}/api/tags")
            if response.status_code != 200:
                self._status = OllamaStatus.UNAVAILABLE
                return self._status

            data = response.json()
            models = data.get("models", [])

            if not models:
                self._status = OllamaStatus.NO_MODELS
                self._available_models = []
            else:
                self._status = OllamaStatus.AVAILABLE
                self._available_models = [
                    OllamaModelInfo(
                        name=m.get("name", ""),
                        size=m.get("size", 0),
                        digest=m.get("digest", ""),
                        modified_at=m.get("modified_at"),
                        details=m.get("details", {})
                    )
                    for m in models
                ]

            self._last_check = datetime.now()
            return self._status

        except httpx.ConnectError:
            logger.debug(f"Ollama not reachable at {self.host}")
            self._status = OllamaStatus.UNAVAILABLE
            self._last_check = datetime.now()
            return self._status
        except Exception as e:
            logger.warning(f"Ollama health check failed: {e}")
            self._status = OllamaStatus.UNAVAILABLE
            self._last_check = datetime.now()
            return self._status

    async def is_available(self) -> bool:
        """Check if Ollama is available and ready to use.

        Caches the result for 30 seconds to avoid excessive health checks.
        """
        # Check cache
        if self._last_check:
            age = (datetime.now() - self._last_check).total_seconds()
            if age < 30:  # Cache for 30 seconds
                return self._status == OllamaStatus.AVAILABLE

        status = await self.check_health()
        return status == OllamaStatus.AVAILABLE

    async def list_models(self) -> List[OllamaModelInfo]:
        """Get list of available models.

        Returns cached list if health was recently checked.
        """
        # Refresh if needed
        if not self._available_models or self._status != OllamaStatus.AVAILABLE:
            await self.check_health()
        return self._available_models

    async def has_model(self, model_name: str) -> bool:
        """Check if a specific model is available."""
        models = await self.list_models()
        return any(m.name == model_name for m in models)

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: str = None,
        tools: List[Dict] = None,
        stream: bool = False
    ) -> Dict[str, Any]:
        """Send a chat completion request to Ollama.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model to use (default: self.model)
            tools: Optional list of tool definitions (OpenAI format)
            stream: If True, returns an async generator for streaming

        Returns:
            Response dict with 'message' containing the assistant's response
        """
        client = await self._get_client()
        model = model or self.model

        # Build request payload
        payload = {
            "model": model,
            "messages": messages,
            "stream": stream,
        }

        # Add tools if provided and model supports them
        if tools:
            # Convert OpenAI tool format to Ollama format
            # Ollama uses the same format as OpenAI for tools
            payload["tools"] = tools

        logger.debug(f"Ollama chat request: model={model}, messages={len(messages)}")

        if stream:
            # Return async generator for streaming
            return self._stream_chat(client, payload)

        # Non-streaming request
        response = await client.post(
            f"{self.host}/api/chat",
            json=payload
        )

        if response.status_code != 200:
            error_text = response.text
            logger.error(f"Ollama chat error: {response.status_code} - {error_text}")
            raise Exception(f"Ollama API error: {response.status_code} - {error_text}")

        return response.json()

    async def _stream_chat(
        self,
        client: httpx.AsyncClient,
        payload: Dict
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream chat responses from Ollama.

        Yields:
            Partial response dicts as they arrive
        """
        async with client.stream(
            "POST",
            f"{self.host}/api/chat",
            json=payload
        ) as response:
            if response.status_code != 200:
                error_text = await response.aread()
                raise Exception(f"Ollama API error: {response.status_code} - {error_text}")

            async for line in response.aiter_lines():
                if line:
                    try:
                        data = json.loads(line)
                        yield data
                    except json.JSONDecodeError:
                        continue

    async def generate(
        self,
        prompt: str,
        model: str = None,
        stream: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """Generate a completion (non-chat mode).

        Args:
            prompt: The prompt text
            model: Model to use (default: self.model)
            stream: If True, returns an async generator
            **kwargs: Additional parameters (temperature, top_p, etc.)

        Returns:
            Response dict with 'response' containing the generated text
        """
        client = await self._get_client()
        model = model or self.model

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": stream,
            **kwargs
        }

        if stream:
            return self._stream_generate(client, payload)

        response = await client.post(
            f"{self.host}/api/generate",
            json=payload
        )

        if response.status_code != 200:
            raise Exception(f"Ollama API error: {response.status_code}")

        return response.json()

    async def _stream_generate(
        self,
        client: httpx.AsyncClient,
        payload: Dict
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream generate responses from Ollama."""
        async with client.stream(
            "POST",
            f"{self.host}/api/generate",
            json=payload
        ) as response:
            if response.status_code != 200:
                error_text = await response.aread()
                raise Exception(f"Ollama API error: {response.status_code} - {error_text}")

            async for line in response.aiter_lines():
                if line:
                    try:
                        data = json.loads(line)
                        yield data
                    except json.JSONDecodeError:
                        continue

    def get_status(self) -> Dict[str, Any]:
        """Get current status information."""
        return {
            "status": self._status.value,
            "host": self.host,
            "model": self.model,
            "available_models": [m.name for m in self._available_models],
            "last_check": self._last_check.isoformat() if self._last_check else None,
        }


# Global singleton instance
_ollama_client: Optional[OllamaClient] = None


def get_ollama_client() -> OllamaClient:
    """Get the global Ollama client instance."""
    global _ollama_client
    if _ollama_client is None:
        _ollama_client = OllamaClient()
    return _ollama_client


async def check_ollama_available() -> bool:
    """Quick check if Ollama is available.

    Convenience function for health checks.
    """
    if not config.OLLAMA_ENABLED:
        return False
    client = get_ollama_client()
    return await client.is_available()
