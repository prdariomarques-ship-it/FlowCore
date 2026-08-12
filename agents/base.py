"""FlowCore Agents — base agent framework.

An Agent is a named unit that can be triggered on demand or on schedule.
Agents are lightweight and run within the executor engine.

This module provides the base class; concrete agents go in ``agents/``.
"""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any

from loguru import logger


class BaseAgent(ABC):
    """Abstract base class for all FlowCore agents.

    Every agent must implement ``run()`` which returns a result dict.
    """

    name: str = "base_agent"
    description: str = ""
    version: str = "0.1.0"

    @abstractmethod
    async def run(self, context: dict | None = None) -> dict[str, Any]:
        """Execute the agent logic.

        Returns a dict with at least ``status`` and ``data`` keys.
        """
        ...

    async def health_check(self) -> dict[str, Any]:
        """Return agent health status."""
        return {
            "name": self.name,
            "status": "ok",
            "version": self.version,
        }


class AgentRegistry:
    """Registry for agent discovery and lookup."""

    def __init__(self) -> None:
        self._agents: dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        self._agents[agent.name] = agent
        logger.info("Agent registered: {}", agent.name)

    def get(self, name: str) -> BaseAgent | None:
        return self._agents.get(name)

    def list(self) -> list[dict[str, Any]]:
        return [
            {
                "name": a.name,
                "description": a.description,
                "version": a.version,
            }
            for a in self._agents.values()
        ]
