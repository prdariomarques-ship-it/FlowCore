"""FlowCore Agent Events — the extensible event vocabulary the autonomous
Agent Runtime is built on (§4 of the "System of Execution" architecture).

Deliberately a single, generic `AgentEvent` shape with a free-form `type`
string rather than a hard-coded enum: adding a new event kind (e.g.
MEETING_APPROACHING, DOCUMENT_ADDED) is a matter of a producer emitting a
new `type` value and CoreOrchestrator registering a handler for it — no
change needed here. This mirrors agents/contracts.py's existing
dataclass-with-to_dict() style rather than introducing a new schema
library.

Every event belongs to exactly one office_id — see
storage/agent_event_repo.py, which persists these the same tenant-scoped
way every other table in this codebase is (storage/client_repo.py,
storage/tenant_repo.py, ...).
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Literal

EventPriority = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW", "NEUTRAL"]
EventStatus = Literal["pending", "processing", "processed", "failed", "ignored", "resolved"]


@dataclass
class AgentEvent:
    type: str
    source: str
    # What this event is about -- e.g. {"kind": "client", "id": "demo-client-21"}.
    # A dict rather than a bare string so an event can name both the kind
    # of thing and its id without inventing a second field for the kind.
    entity: dict[str, str]
    payload: dict[str, Any] = field(default_factory=dict)
    priority: EventPriority = "MEDIUM"
    status: EventStatus = "pending"
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: secrets.token_hex(12))
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "timestamp": self.timestamp,
            "source": self.source,
            "entity": self.entity,
            "payload": self.payload,
            "priority": self.priority,
            "status": self.status,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AgentEvent":
        return cls(
            id=d["id"], type=d["type"], timestamp=d["timestamp"], source=d["source"],
            entity=d["entity"], payload=d.get("payload", {}), priority=d.get("priority", "MEDIUM"),
            status=d.get("status", "pending"), metadata=d.get("metadata", {}),
        )

    def dedup_key(self) -> str:
        """Identifies "the same situation" across observation cycles --
        same office (implicit, callers scope by office_id separately),
        same type, same entity, same payload shape -- so a still-ongoing
        violation doesn't get re-published (and re-notified) every single
        cycle. Deliberately excludes id/timestamp/status/metadata."""
        import hashlib
        import json

        key_material = json.dumps(
            {"type": self.type, "entity": self.entity, "payload": self.payload}, sort_keys=True, default=str,
        )
        return hashlib.sha256(key_material.encode("utf-8")).hexdigest()[:24]
