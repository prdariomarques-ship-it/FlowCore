"""FlowCore — Persistent Background Daemon.

Runs as a separate process that outlives individual CLI invocations.
Writes its PID and cycle state to disk so other processes can query it.
Implements a watchdog heartbeat loop; survives Android kills via
the checkpoint pattern: state is written before each sleep cycle.

Running the daemon loop
-----------------------
The daemon loop lives in this same module under ``if __name__ == "__main__"``.
``FlowCoreDaemon.start()`` spawns it as a subprocess pointing at this file.

Usage (via FlowCoreDaemon)::

    d = FlowCoreDaemon()
    d.start()              # → {"started": True, "pid": 12345, ...}
    d.status()             # → {"running": True, "pid": 12345, "uptime": 42.1}
    d.stop()               # → {"stopped": True, "pid": 12345}

Usage (daemon loop directly)::

    python3 runtime/daemon.py          # starts and stays running
    python3 runtime/daemon.py --check  # exits 0 if running, 1 if not
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


_DAEMON_DIR = Path.home() / ".flowcore" / "daemon"
_PID_FILE = _DAEMON_DIR / "flowcore.pid"
_STATE_FILE = _DAEMON_DIR / "daemon.state.json"
_LOG_FILE = _DAEMON_DIR / "daemon.log"


# ── Manager (used by CLI and other modules) ───────────────────────────────────


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
                stdout=log,
                stderr=log,
                close_fds=True,
                start_new_session=True,
            )
        # Give the child time to write its PID file
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            pid = self._read_pid()
            if pid and _pid_alive(pid):
                return {"started": True, "pid": pid, "log": str(_LOG_FILE)}
            time.sleep(0.1)
        # Fallback: use the Popen pid
        return {"started": True, "pid": proc.pid, "log": str(_LOG_FILE), "note": "pid file not yet written"}

    def stop(self) -> dict[str, Any]:
        """Send SIGTERM to the daemon and clean up PID file."""
        pid = self._read_pid()
        if not pid:
            return {"stopped": False, "note": "daemon not running"}
        try:
            os.kill(pid, signal.SIGTERM)
            # Wait up to 2s for clean shutdown
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


# ── Shared helper ─────────────────────────────────────────────────────────────


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


# ── Daemon loop (runs in the child process) ───────────────────────────────────


def _run_daemon_loop(interval: int) -> None:
    """Heartbeat loop executed inside the spawned subprocess."""
    _DAEMON_DIR.mkdir(parents=True, exist_ok=True)

    my_pid = os.getpid()
    _PID_FILE.write_text(str(my_pid))

    started_at = time.time()
    running = True

    def _handle_term(sig: int, frame: object) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, _handle_term)
    signal.signal(signal.SIGINT, _handle_term)

    cycle = 0
    while running:
        cycle += 1
        state = {
            "pid": my_pid,
            "cycle": cycle,
            "started_at": started_at,
            "ts": time.time(),
            "interval": interval,
        }
        try:
            tmp = _STATE_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(state))
            tmp.replace(_STATE_FILE)
        except Exception:
            pass

        # Sleep in small slices so SIGTERM is handled promptly
        slept = 0.0
        while running and slept < interval:
            time.sleep(0.5)
            slept += 0.5

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
