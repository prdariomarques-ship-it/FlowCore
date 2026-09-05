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
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.loader import get_config, load_config
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
# Database initialisation
# ---------------------------------------------------------------------------

async def init_database(cfg: dict) -> Any:
    """Initialise the SQLite database and create tables if missing."""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy import text

    url = cfg["database"]["url"]
    engine = create_async_engine(url, echo=False)

    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS flows (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                status TEXT DEFAULT 'created',
                config TEXT,
                created_at REAL,
                updated_at REAL
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS executions (
                id TEXT PRIMARY KEY,
                flow_id TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                result TEXT,
                started_at REAL,
                finished_at REAL,
                FOREIGN KEY (flow_id) REFERENCES flows(id)
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at REAL
            )
        """))

    logger.info("Database initialised: {}", url)
    return engine


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
        self.db_engine = await init_database(self.cfg)
        self._register_observer_ingestion()
        self._running = True
        logger.info("FlowCore started successfully")

    def _register_observer_ingestion(self) -> None:
        """Register the recurring observer-ingestion job (P0 — ingestão
        contínua), unless explicitly disabled. Never fails startup — a
        scheduler error here is logged and skipped, not raised.
        """
        if os.environ.get("FLOWCORE_AUTO_INGEST", "1") == "0":
            return
        schedule = os.environ.get("FLOWCORE_OBSERVER_SCHEDULE", "*/15 * * * *")
        script = self.root / "scripts" / "ingest_observers.py"
        try:
            from runtime.job_scheduler import JobScheduler
            JobScheduler().add_job("observer_ingest", str(script), schedule)
        except Exception as exc:
            logger.warning("Could not register observer_ingest job (non-fatal): {}", exc)

    async def stop(self) -> None:
        """Gracefully shut down."""
        if not self._running:
            return
        self._running = False
        self._shutdown_event.set()
        if hasattr(self, "db_engine"):
            await self.db_engine.dispose()
        logger.info("FlowCore stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    def run_doctor(self) -> dict[str, Any]:
        """Doctor Flow: USER -> Runtime -> Capability Registry -> Doctor
        Capability -> Execution -> real result -> Observability -> History.

        Resolves cpu/memory/disk readings through the capability registry
        (never raises — an unsupported or failed capability comes back as
        an explicit success=False reading) and runs DoctorService's full
        component check suite independently, then persists the combined
        report to ~/.flowcore/flowcore.doctor.json for history. A failure
        to persist history degrades silently — it must never turn an
        otherwise-successful diagnostic into a reported failure.
        """
        from capability.resolver import ProviderResolver
        from doctor.service import DoctorService

        resolver = ProviderResolver()
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "environment": self.platform_info,
            "cpu": resolver.resolve("getCpuUsage").to_dict(),
            "memory": resolver.resolve("getMemoryUsage").to_dict(),
            "disk": resolver.resolve("getDiskUsage", str(self.root)).to_dict(),
            "components": DoctorService().run().to_dict(),
        }

        try:
            history_dir = Path.home() / ".flowcore"
            history_dir.mkdir(parents=True, exist_ok=True)
            (history_dir / "flowcore.doctor.json").write_text(json.dumps(report))
        except OSError:
            logger.warning("Doctor: could not persist history file (non-fatal)")

        return report


def _detect_root() -> Path:
    """Detect project root."""
    return Path(__file__).resolve().parent.parent
