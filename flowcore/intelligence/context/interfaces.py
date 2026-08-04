from __future__ import annotations

from typing import Dict, Any, List, Optional
from pathlib import Path


class IContextEngine:
    """Interface for the core ContextEngine orchestrator."""
    def validate(self, force_refresh: bool = False) -> Any:
        raise NotImplementedError()


class ICapabilityRegistry:
    """Interface for Capability resolution registry."""
    def resolve(self, capability_name: str) -> Dict[str, Any]:
        raise NotImplementedError()


class IRuntimeSerializer:
    """Interface for runtime and platform configurations serializer."""
    def serialize(self, workspace_path: Path) -> Dict[str, Any]:
        raise NotImplementedError()


class IPassportBuilder:
    """Interface for building and verifying the FlowCorePassport transit card."""
    def build_passport(self, frame: Any) -> Any:
        raise NotImplementedError()
