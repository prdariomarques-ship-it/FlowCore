"""FlowCore — Passport data schema."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


@dataclass
class AgentIdentity:
    """Identity of the agent requesting execution."""
    name: str
    version: str = "0.1.0"
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AgentIdentity":
        return cls(
            name=d["name"],
            version=d.get("version", "0.1.0"),
            description=d.get("description", ""),
        )


@dataclass
class RuntimeInfo:
    """Snapshot of the runtime at passport issuance."""
    platform: str          # "android" | "termux" | "linux"
    is_android: bool
    is_termux: bool
    has_internet: bool
    python_version: str
    capabilities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RuntimeInfo":
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


@dataclass
class Passport:
    """Execution passport — issued to an agent before it runs."""
    agent: AgentIdentity
    runtime: RuntimeInfo
    capabilities: list[str]          # subset the agent is allowed to use
    permissions: list[str]           # fine-grained permission list
    health_status: str               # "ok" | "degraded" | "unhealthy"
    issued_at: str = field(default_factory=_now_iso)
    expires_at: str = ""
    hash: str = ""

    # TTL in seconds at issuance (stored for validator)
    _ttl: int = field(default=3600, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.expires_at:
            expires_ts = time.time() + self._ttl
            self.expires_at = _iso(expires_ts)
        if not self.hash:
            self.hash = self._compute_hash()

    def _compute_hash(self) -> str:
        payload = json.dumps({
            "agent": self.agent.to_dict(),
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "capabilities": sorted(self.capabilities),
            "permissions": sorted(self.permissions),
            "health_status": self.health_status,
        }, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()

    def is_expired(self) -> bool:
        try:
            exp = datetime.fromisoformat(self.expires_at)
            return datetime.now(timezone.utc) > exp
        except Exception:
            return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent.to_dict(),
            "runtime": self.runtime.to_dict(),
            "capabilities": self.capabilities,
            "permissions": self.permissions,
            "health_status": self.health_status,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "hash": self.hash,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Passport":
        agent   = AgentIdentity.from_dict(d["agent"])
        runtime = RuntimeInfo.from_dict(d["runtime"])
        p = cls(
            agent=agent,
            runtime=runtime,
            capabilities=d.get("capabilities", []),
            permissions=d.get("permissions", []),
            health_status=d.get("health_status", "ok"),
            issued_at=d.get("issued_at", _now_iso()),
            expires_at=d.get("expires_at", ""),
            hash=d.get("hash", ""),
        )
        return p
