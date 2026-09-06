"""Structured Event schemas and data models for FlowCore event-driven architecture."""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class EventPriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class EventStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"


@dataclass
class Event:
    type: str
    source: str
    entity: str
    payload: Dict[str, Any]
    id: str = field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:12]}")
    timestamp: float = field(default_factory=time.time)
    priority: EventPriority = EventPriority.MEDIUM
    status: EventStatus = EventStatus.PENDING
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["priority"] = self.priority.value if isinstance(self.priority, EventPriority) else self.priority
        data["status"] = self.status.value if isinstance(self.status, EventStatus) else self.status
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Event:
        priority = EventPriority(data.get("priority", EventPriority.MEDIUM.value))
        status = EventStatus(data.get("status", EventStatus.PENDING.value))
        return cls(
            id=data.get("id", f"evt_{uuid.uuid4().hex[:12]}"),
            type=data["type"],
            timestamp=data.get("timestamp", time.time()),
            source=data.get("source", "system"),
            entity=data.get("entity", "unknown"),
            payload=data.get("payload", {}),
            priority=priority,
            status=status,
            metadata=data.get("metadata", {}),
        )
