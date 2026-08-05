"""FlowCore — Passport generator."""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from passport.schema import AgentIdentity, Passport, RuntimeInfo


class PassportGenerator:
    """Issues Passports by interrogating the runtime and capability registry."""

    def __init__(self, ttl: int = 3600) -> None:
        self.ttl = ttl

    def issue(
        self,
        agent: AgentIdentity,
        *,
        permissions: list[str] | None = None,
        requested_capabilities: list[str] | None = None,
    ) -> Passport:
        """Generate and return a new Passport for *agent*.

        Args:
            agent: Identity of the requesting agent.
            permissions: Explicit permission list; defaults to all capabilities.
            requested_capabilities: Subset to grant; defaults to all available.
        """
        runtime = self._build_runtime_info()
        available = self._available_capabilities()

        # Intersect requested with available; fallback to all available
        if requested_capabilities is not None:
            caps = [c for c in requested_capabilities if c in available]
        else:
            caps = list(available)

        perms = permissions if permissions is not None else list(caps)
        health = self._health_status()

        passport = Passport(
            agent=agent,
            runtime=runtime,
            capabilities=caps,
            permissions=perms,
            health_status=health,
            _ttl=self.ttl,
        )
        logger.info(
            "Passport issued: agent={} caps={} health={} ttl={}s",
            agent.name,
            len(caps),
            health,
            self.ttl,
        )
        return passport

    # ── Internals ─────────────────────────────────────────────────────────────

    def _build_runtime_info(self) -> RuntimeInfo:
        import sys
        import os

        is_termux = bool(os.environ.get("PREFIX"))
        is_android = is_termux and Path("/system/build.prop").exists()

        platform = "android" if is_android else ("termux" if is_termux else "linux")
        caps = self._available_capabilities()

        has_internet = self._check_internet()

        return RuntimeInfo(
            platform=platform,
            is_android=is_android,
            is_termux=is_termux,
            has_internet=has_internet,
            python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            capabilities=caps,
        )

    def _available_capabilities(self) -> list[str]:
        try:
            from capability.registry import CapabilityRegistry

            reg = CapabilityRegistry()
            return [cap for cap, adapter in reg.list_capabilities().items() if adapter]
        except Exception:
            return []

    def _health_status(self) -> str:
        try:
            from doctor.service import DoctorService

            report = DoctorService().run(verbose=False)
            if report.failed > 0:
                return "unhealthy"
            if report.warned > 3:
                return "degraded"
            return "ok"
        except Exception:
            return "unknown"

    def _check_internet(self) -> bool:
        try:
            import socket

            socket.setdefaulttimeout(3)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 53))
            return True
        except Exception:
            return False
