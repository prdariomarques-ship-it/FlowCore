"""FlowCore Runtime Kernel — heart of the FlowCore runtime.

The kernel orchestrates the full boot sequence:

    BOOT → Discover → Doctor → Capabilities → Passport → READY

It knows:
- Which Android version is running
- Whether Termux is installed and healthy
- Which bridges are available
- Which providers are preferred and which are fallbacks
- The complete runtime state (written to flowcore.runtime.json)

All other modules depend on the kernel; the kernel depends on nothing
above the discovery/shell layer.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger
from runtime.discovery import RuntimeDiscovery, RuntimeSnapshot


# ── Runtime passport ──────────────────────────────────────────────────────────


class RuntimePassport:
    """Immutable token issued by the kernel after a successful boot.

    Every subsystem that needs to understand its runtime environment
    receives a RuntimePassport.  The passport encodes what the kernel
    discovered and which capabilities are guaranteed at this boot.
    """

    def __init__(self, snapshot: RuntimeSnapshot, runtime_json_path: Path) -> None:
        self._snap = snapshot
        self._path = runtime_json_path
        self._issued_at = datetime.now(timezone.utc).isoformat()

    # Public read-only properties -------------------------------------------

    @property
    def platform(self) -> str:
        return self._snap.platform_type

    @property
    def is_android(self) -> bool:
        return self._snap.android.detected

    @property
    def is_termux(self) -> bool:
        return self._snap.termux.detected

    @property
    def capabilities(self) -> list[str]:
        return list(self._snap.capabilities)

    @property
    def tools(self) -> dict[str, bool]:
        return {k: v.available for k, v in self._snap.tools.items()}

    @property
    def has_internet(self) -> bool:
        return self._snap.network.internet

    @property
    def issued_at(self) -> str:
        return self._issued_at

    def has_capability(self, name: str) -> bool:
        return name in self._snap.capabilities

    def has_tool(self, name: str) -> bool:
        return self._snap.tools.get(name, None) is not None and (self._snap.tools[name].available)

    def to_dict(self) -> dict[str, Any]:
        snap_dict = self._snap.to_dict()
        snap_dict["issued_at"] = self._issued_at
        snap_dict["runtime_json"] = str(self._path)
        content = json.dumps(snap_dict, sort_keys=True)
        snap_dict["hash"] = hashlib.sha256(content.encode()).hexdigest()[:16]
        return snap_dict

    def __repr__(self) -> str:
        return f"<RuntimePassport platform={self.platform} termux={self.is_termux} caps={len(self.capabilities)}>"


# ── Runtime Kernel ────────────────────────────────────────────────────────────


class RuntimeKernel:
    """Orchestrates the FlowCore boot sequence.

    Usage::

        kernel = RuntimeKernel()
        passport = kernel.boot()
        if passport.has_capability("getBattery"):
            ...
    """

    _RUNTIME_JSON_NAME = "flowcore.runtime.json"

    def __init__(self, root: Path | None = None) -> None:
        self._root = root or self._detect_root()
        self._runtime_json = Path.home() / ".flowcore" / self._RUNTIME_JSON_NAME
        self._passport: RuntimePassport | None = None

    # ── Boot sequence ─────────────────────────────────────────────────────────

    def boot(self, *, verbose: bool = False) -> RuntimePassport:
        """Execute the full boot sequence and return the Runtime Passport.

        Sequence:
            1. Discover   — scan platform, env, tools, network
            2. Doctor     — quick health validation (warns only, does not block)
            3. Capabilities — derive from discovery
            4. Persist    — write flowcore.runtime.json
            5. Passport   — issue and return
        """
        logger.info("FlowCore Runtime Kernel — booting")

        # 1 — Discover
        logger.info("  [1/5] Runtime Discovery")
        discovery = RuntimeDiscovery()
        snapshot = discovery.run()
        if verbose:
            self._log_snapshot(snapshot)

        # 2 — Quick Doctor (non-blocking)
        logger.info("  [2/5] Health Validation")
        issues = self._quick_health(snapshot)
        for issue in issues:
            logger.warning("  ⚠  {}", issue)

        # 3 — Capabilities
        logger.info("  [3/5] Capabilities: {}", snapshot.capabilities)

        # 4 — Persist runtime.json
        logger.info("  [4/5] Writing {}", self._runtime_json)
        self._write_runtime_json(snapshot)

        # 5 — Passport
        logger.info("  [5/5] Runtime Passport issued")
        self._passport = RuntimePassport(snapshot, self._runtime_json)
        logger.info("  → {}", self._passport)

        return self._passport

    @property
    def passport(self) -> RuntimePassport | None:
        return self._passport

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _quick_health(self, snap: RuntimeSnapshot) -> list[str]:
        """Return a list of warning strings for non-critical issues."""
        issues: list[str] = []
        if not snap.tools.get("python3", None) or not snap.tools["python3"].available:
            issues.append("python3 not found — runtime may be degraded")
        if snap.termux.detected and not snap.termux.api_available:
            issues.append("Termux API not installed — install via: pkg install termux-api")
        if snap.termux.detected and not snap.termux.storage_available:
            issues.append("Termux storage not set up — run: termux-setup-storage")
        if not snap.network.dns:
            issues.append("No DNS resolution — network capabilities unavailable")
        return issues

    def _write_runtime_json(self, snap: RuntimeSnapshot) -> None:
        """Best-effort persistence: a storage failure here (read-only home,
        permissions, disk full) must never abort boot() after discovery has
        already succeeded — same reasoning and convention as
        runtime/core.py's FlowCoreRuntime._write_doctor_history()."""
        data = snap.to_dict()
        data["schema_version"] = "1.0"
        data["generated_at"] = datetime.now(timezone.utc).isoformat()

        try:
            self._runtime_json.parent.mkdir(parents=True, exist_ok=True)
            with open(self._runtime_json, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except OSError as e:
            logger.warning("RuntimeKernel: could not write {}: {}", self._runtime_json, e)

    def _log_snapshot(self, snap: RuntimeSnapshot) -> None:
        logger.debug("  Platform: {}", snap.platform_type)
        logger.debug("  Python:   {}", snap.python_version)
        logger.debug("  Termux:   {}", snap.termux.detected)
        logger.debug("  Android:  {}", snap.android.detected)
        tools_ok = [k for k, v in snap.tools.items() if v.available]
        logger.debug("  Tools:    {}", tools_ok)

    @staticmethod
    def _detect_root() -> Path:
        return Path(__file__).resolve().parent.parent
