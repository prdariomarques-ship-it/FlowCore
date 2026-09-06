"""Base tool specification with permissions, risk levels, and audit log."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, Optional


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class BaseTool(ABC):
    name: str
    description: str
    permission: str
    risk_level: RiskLevel = RiskLevel.LOW

    @abstractmethod
    def run(self, **kwargs: Any) -> Dict[str, Any]:
        """Execute tool logic."""
        pass

    def schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "permission": self.permission,
            "risk_level": self.risk_level.value,
        }
