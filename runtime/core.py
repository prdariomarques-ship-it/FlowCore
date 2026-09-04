"""FlowCore Runtime — application lifecycle management.

Responsible for:
- Bootstrapping the application (load config, init database, start API)
- Graceful shutdown (SIGINT / SIGTERM)
- Health checks

Designed to run on Termux / Android with minimal resource footprint.
"""
from __future__ import annotations

import asyncio
import os
import signal
import sys
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
        self._running = True
        logger.info("FlowCore started successfully")

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


def _detect_root() -> Path:
    """Detect project root."""
    return Path(__file__).resolve().parent.parent
