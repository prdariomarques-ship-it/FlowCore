"""LLM Adapter Protocol and Data Models for DARIUS OSS."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class LLMMessage(BaseModel):
    """Normalized chat completion message representation."""

    role: Literal["system", "user", "assistant", "tool"]
    content: str
    name: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


class LLMUsage(BaseModel):
    """Token consumption metrics for an LLM invocation."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class LLMResponse(BaseModel):
    """Structured response from an LLM adapter."""

    content: str
    model: str
    provider: str
    usage: dict[str, int] = Field(default_factory=dict)
    latency_ms: int = 0
    finish_reason: str | None = None


@runtime_checkable
class LLMAdapter(Protocol):
    """Port interface for interchangeable LLM providers (Ollama, DeepSeek, OpenRouter, etc.)."""

    async def generate(self, messages: list[LLMMessage], **kwargs: Any) -> LLMResponse:
        """Generate a complete response from the model."""
        ...

    async def stream(self, messages: list[LLMMessage], **kwargs: Any) -> AsyncIterator[str]:
        """Stream token responses asynchronously from the model."""
        ...

    async def health(self) -> dict[str, Any]:
        """Check provider connectivity, responsiveness, and available models."""
        ...
