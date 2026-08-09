"""FlowCore Runtime — application lifecycle management.

Responsible for:
- Bootstrapping the application (load config, init database, start API)
- Graceful shutdown (SIGINT / SIGTERM)
- Health checks

Designed to run on Termux / Android with minimal resource footprint.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.loader import load_config
from loguru import logger

# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

_IS_TERMUX = bool(os.environ.get("PREFIX"))
_IS_ANDROID = _IS_TERMUX or os.path.exists("/system/bin/app_process")


def detect_platform() -> dict[str, Any]:
    """Return platform detection results."""
    info = {
        "termux": _IS_TERMUX,
        "android": _IS_ANDROID,
        "python_version": sys.version.split()[0],
        "os_name": os.name,
        "prefix": os.environ.get("PREFIX", "/usr"),
    }
    return info


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class FlowCoreRuntime:
    """Main application runtime.

    Usage::

        runtime = FlowCoreRuntime()
        await runtime.start()
        await runtime.stop()
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or _detect_root()
        self.cfg = load_config()
        self._running = False
        self._shutdown_event = asyncio.Event()
        self.platform_info = detect_platform()

    async def start(self) -> None:
        """Bootstrap the application."""
        logger.info(
            "FlowCore starting — platform: termux={} android={} python={}",
            self.platform_info["termux"],
            self.platform_info["android"],
            self.platform_info["python_version"],
        )
        self._running = True
        logger.info("FlowCore started successfully")

    async def stop(self) -> None:
        """Gracefully shut down."""
        if not self._running:
            return
        self._running = False
        self._shutdown_event.set()
        logger.info("FlowCore stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    def run_doctor(self) -> dict[str, Any]:
        """Real, end-to-end health diagnostic — the "Health checks"
        responsibility documented above, previously unimplemented.

        Resolves CPU / memory / disk through the Capability Registry (so
        the result reflects whatever adapter is actually available on this
        host, never a hardcoded platform assumption), and combines that
        with DoctorService's existing component checks and this runtime's
        own platform detection. Every call is logged (existing Observability
        convention: loguru) and the report is persisted to
        ~/.flowcore/flowcore.doctor.json (same convention RuntimeKernel
        already uses for flowcore.runtime.json), giving the last run a
        retrievable History.
        """
        from capability.resolver import ProviderResolver
        from doctor.service import DoctorService

        resolver = ProviderResolver()
        cpu = resolver.resolve("getCpuInfo")
        memory = resolver.resolve("getMemoryInfo")
        disk = resolver.resolve("getDiskUsage", str(self.root))
        components = DoctorService().run()

        report: dict[str, Any] = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "environment": self.platform_info,
            "cpu": cpu.to_dict(),
            "memory": memory.to_dict(),
            "disk": disk.to_dict(),
            "components": components.to_dict(),
        }

        logger.info(
            "Doctor: cpu={} memory={} disk={} components={}/{} passed",
            cpu.success,
            memory.success,
            disk.success,
            components.passed,
            len(components.checks),
        )
        self._write_doctor_history(report)
        return report

    def _write_doctor_history(self, report: dict[str, Any]) -> None:
        path = Path.home() / ".flowcore" / "flowcore.doctor.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)


def _detect_root() -> Path:
    """Detect project root."""
    return Path(__file__).resolve().parent.parent
