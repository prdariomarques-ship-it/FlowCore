"""Skill Adapter Protocol and Data Models for DARIUS OSS."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class SkillManifest(BaseModel):
    """Declarative specification defining an agent skill capability."""

    id: str
    name: str
    version: str = "1.0.0"
    description: str
    system_prompt_snippet: str = ""
    required_tools: list[str] = Field(default_factory=list)
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class SkillAdapter(Protocol):
    """Port interface for dynamically loaded and executable agent skills."""

    @property
    def manifest(self) -> SkillManifest:
        """Return the skill metadata and declaration."""
        ...

    async def activate(self, context: dict[str, Any]) -> bool:
        """Initialize and inject skill capabilities into the active runtime context."""
        ...

    async def deactivate(self, context: dict[str, Any]) -> bool:
        """Tear down and unload skill capabilities from the runtime context."""
        ...
