"""FlowCore Flow schema — Flow, FlowStep, FlowRun dataclasses."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field


@dataclass
class FlowStep:
    agent: str
    context: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"agent": self.agent, "context": self.context}

    @classmethod
    def from_dict(cls, d: dict) -> "FlowStep":
        return cls(agent=d["agent"], context=d.get("context") or {})


@dataclass
class Flow:
    id: str
    name: str
    steps: list[FlowStep]
    created_at: float
    description: str = ""

    @classmethod
    def new(
        cls,
        name: str,
        steps: list[dict] | None = None,
        description: str = "",
    ) -> "Flow":
        return cls(
            id=uuid.uuid4().hex[:12],
            name=name,
            steps=[FlowStep.from_dict(s) for s in (steps or [])],
            created_at=time.time(),
            description=description,
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Flow":
        return cls(
            id=d["id"],
            name=d["name"],
            steps=[FlowStep.from_dict(s) for s in d.get("steps") or []],
            created_at=d.get("created_at", time.time()),
            description=d.get("description", ""),
        )


@dataclass
class FlowRun:
    id: str
    flow_id: str
    flow_name: str
    status: str  # pending | running | completed | failed
    step_results: list[dict]
    created_at: float
    started_at: float | None = None
    finished_at: float | None = None
    error: str | None = None

    @classmethod
    def new(cls, flow: "Flow") -> "FlowRun":
        return cls(
            id=uuid.uuid4().hex[:16],
            flow_id=flow.id,
            flow_name=flow.name,
            status="pending",
            step_results=[],
            created_at=time.time(),
        )

    @property
    def duration_seconds(self) -> float | None:
        if self.started_at and self.finished_at:
            return round(self.finished_at - self.started_at, 3)
        return None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "flow_id": self.flow_id,
            "flow_name": self.flow_name,
            "status": self.status,
            "step_results": self.step_results,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_seconds": self.duration_seconds,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FlowRun":
        return cls(
            id=d["id"],
            flow_id=d["flow_id"],
            flow_name=d.get("flow_name", ""),
            status=d["status"],
            step_results=d.get("step_results") or [],
            created_at=d.get("created_at", time.time()),
            started_at=d.get("started_at"),
            finished_at=d.get("finished_at"),
            error=d.get("error"),
        )
