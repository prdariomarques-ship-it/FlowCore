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
        """Bootstrap the application and ensure Core-owned observer ingestion is registered."""
        logger.info(
            "FlowCore starting — platform: termux={} android={} python={}",
            self.platform_info["termux"],
            self.platform_info["android"],
            self.platform_info["python_version"],
        )
        self._ensure_observer_ingestion_job()
        self._running = True
        logger.info("FlowCore started successfully")

    def _ensure_observer_ingestion_job(self) -> None:
        """Register the canonical observer ingestion job through JobScheduler.

        Registration is intentionally best-effort: environments without cron or
        Termux's scheduler can still run the API and invoke the ingestion script
        manually. The Core remains the single owner of this job; Web and Mobile
        only consume the resulting events and derived reports.
        """
        if os.environ.get("FLOWCORE_AUTO_INGEST", "1").lower() in {"0", "false", "no", "off"}:
            logger.info("Observer ingestion auto-registration disabled by FLOWCORE_AUTO_INGEST")
            return

        script = self.root / "scripts" / "ingest_observers.py"
        if not script.exists():
            logger.warning("Observer ingestion script not found: {}", script)
            return

        schedule = os.environ.get("FLOWCORE_OBSERVER_SCHEDULE", "*/15 * * * *")
        try:
            from runtime.job_scheduler import JobScheduler

            registered = JobScheduler().add_job(
                "observer_ingest",
                str(script),
                schedule,
            )
            logger.info(
                "Observer ingestion job ensured: schedule={} registered={}",
                schedule,
                registered,
            )
        except Exception as exc:
            logger.warning("Could not register observer ingestion job: {}", exc)

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
        """Best-effort persistence: a storage failure here (read-only home,
        permissions, disk full — realistic on Termux/Android, see the
        termux_storage check in doctor/service.py) must never turn an
        otherwise-successful diagnostic into a reported failure. Mirrors
        the existing degrade-gracefully convention in api/router.py's
        /api/status Doctor section (try/except, log and move on)."""
        path = Path.home() / ".flowcore" / "flowcore.doctor.json"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
        except OSError as e:
            logger.warning("Doctor: could not write history to {}: {}", path, e)


def _detect_root() -> Path:
    """Detect project root."""
    return Path(__file__).resolve().parent.parent
