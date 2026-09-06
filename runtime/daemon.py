"""FlowCore — Persistent Background Daemon with Agent Workers Integration.

Runs as a separate process that outlives individual CLI invocations.
Writes its PID and cycle state to disk so other processes can query it.
Implements a watchdog heartbeat loop and executes background agent workers.
"""
from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from runtime.workers import start_all_workers

_DAEMON_DIR = Path.home() / ".flowcore" / "daemon"
_PID_FILE   = _DAEMON_DIR / "flowcore.pid"
_STATE_FILE = _DAEMON_DIR / "daemon.state.json"
_LOG_FILE   = _DAEMON_DIR / "daemon.log"


class FlowCoreDaemon:
    """Start, stop, and query the FlowCore background daemon."""

    def start(self, *, interval: int = 60) -> dict[str, Any]:
        """Start the daemon. Idempotent — returns existing PID if already running."""
        if self.is_running():
            return {"started": False, "pid": self._read_pid(), "note": "already running"}
        _DAEMON_DIR.mkdir(parents=True, exist_ok=True)
        with open(_LOG_FILE, "a") as log:
            proc = subprocess.Popen(
                [sys.executable, __file__, "--interval", str(interval)],
                stdout=log, stderr=log,
                close_fds=True,
                start_new_session=True,
            )
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            pid = self._read_pid()
            if pid and _pid_alive(pid):
                return {"started": True, "pid": pid, "log": str(_LOG_FILE)}
            time.sleep(0.1)
        return {"started": True, "pid": proc.pid, "log": str(_LOG_FILE),
                "note": "pid file not yet written"}

    def stop(self) -> dict[str, Any]:
        """Send SIGTERM to the daemon and clean up PID file."""
        pid = self._read_pid()
        if not pid:
            return {"stopped": False, "note": "daemon not running"}
        try:
            os.kill(pid, signal.SIGTERM)
            for _ in range(20):
                if not _pid_alive(pid):
                    break
                time.sleep(0.1)
            _PID_FILE.unlink(missing_ok=True)
            _STATE_FILE.unlink(missing_ok=True)
            return {"stopped": True, "pid": pid}
        except ProcessLookupError:
            _PID_FILE.unlink(missing_ok=True)
            return {"stopped": True, "pid": pid, "note": "process was already gone"}
        except PermissionError as e:
            return {"stopped": False, "error": str(e)}

    def status(self) -> dict[str, Any]:
        """Return daemon status dictionary."""
        pid = self._read_pid()
        if not pid or not _pid_alive(pid):
            return {"running": False, "pid": pid}
        state: dict[str, Any] = {}
        if _STATE_FILE.exists():
            try:
                state = json.loads(_STATE_FILE.read_text())
            except Exception:
                pass
        uptime = time.time() - state.get("started_at", time.time())
        return {
            "running": True,
            "pid": pid,
            "uptime": round(uptime, 1),
            "cycle": state.get("cycle", 0),
            "log": str(_LOG_FILE),
        }

    def is_running(self) -> bool:
        pid = self._read_pid()
        return bool(pid and _pid_alive(pid))

    def _read_pid(self) -> int | None:
        if not _PID_FILE.exists():
            return None
        try:
            return int(_PID_FILE.read_text().strip())
        except Exception:
            return None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


async def _async_daemon_loop(interval: int) -> None:
    """Async daemon loop running workers and updating state."""
    _DAEMON_DIR.mkdir(parents=True, exist_ok=True)
    my_pid = os.getpid()
    _PID_FILE.write_text(str(my_pid))

    started_at = time.time()
    # Start background agent workers
    await start_all_workers()

    cycle = 0
    while True:
        cycle += 1
        state = {
            "pid": my_pid,
            "cycle": cycle,
            "started_at": started_at,
            "ts": time.time(),
            "interval": interval,
            "workers_active": True,
        }
        try:
            tmp = _STATE_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(state))
            tmp.replace(_STATE_FILE)
        except Exception:
            pass
        await asyncio.sleep(interval)


def _run_daemon_loop(interval: int) -> None:
    try:
        asyncio.run(_async_daemon_loop(interval))
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        _PID_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    import argparse as _ap
    p = _ap.ArgumentParser(description="FlowCore daemon loop")
    p.add_argument("--interval", type=int, default=60)
    p.add_argument("--check", action="store_true", help="Exit 0 if daemon running, 1 otherwise")
    opts = p.parse_args()

    if opts.check:
        sys.exit(0 if FlowCoreDaemon().is_running() else 1)
    else:
        _run_daemon_loop(opts.interval)
