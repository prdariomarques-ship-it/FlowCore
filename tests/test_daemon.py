"""Tests for runtime.daemon — FlowCoreDaemon manager."""

from __future__ import annotations

import os
import signal
import sys
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _make_daemon(tmp_path: Path):
    """Return a FlowCoreDaemon patched to use tmp_path for all state files."""
    import runtime.daemon as _mod

    pid_file = tmp_path / "flowcore.pid"
    state_file = tmp_path / "daemon.state.json"
    log_file = tmp_path / "daemon.log"
    with (
        patch.object(_mod, "_DAEMON_DIR", tmp_path),
        patch.object(_mod, "_PID_FILE", pid_file),
        patch.object(_mod, "_STATE_FILE", state_file),
        patch.object(_mod, "_LOG_FILE", log_file),
    ):
        from runtime.daemon import FlowCoreDaemon

        d = FlowCoreDaemon()
        # keep references so callers can use them
        d._test_pid_file = pid_file
        d._test_state_file = state_file
        d._test_log_file = log_file
        return d


class TestFlowCoreDaemon:
    def test_is_running_false_initially(self, tmp_path):
        import runtime.daemon as _mod

        with (
            patch.object(_mod, "_PID_FILE", tmp_path / "flowcore.pid"),
            patch.object(_mod, "_STATE_FILE", tmp_path / "state.json"),
            patch.object(_mod, "_DAEMON_DIR", tmp_path),
        ):
            from runtime.daemon import FlowCoreDaemon

            d = FlowCoreDaemon()
            assert d.is_running() is False

    def test_status_not_running_initially(self, tmp_path):
        import runtime.daemon as _mod

        with (
            patch.object(_mod, "_PID_FILE", tmp_path / "flowcore.pid"),
            patch.object(_mod, "_STATE_FILE", tmp_path / "state.json"),
            patch.object(_mod, "_DAEMON_DIR", tmp_path),
        ):
            from runtime.daemon import FlowCoreDaemon

            d = FlowCoreDaemon()
            s = d.status()
            assert s["running"] is False

    def test_stop_when_not_running(self, tmp_path):
        import runtime.daemon as _mod

        with (
            patch.object(_mod, "_PID_FILE", tmp_path / "flowcore.pid"),
            patch.object(_mod, "_STATE_FILE", tmp_path / "state.json"),
            patch.object(_mod, "_DAEMON_DIR", tmp_path),
        ):
            from runtime.daemon import FlowCoreDaemon

            d = FlowCoreDaemon()
            result = d.stop()
            assert result["stopped"] is False

    def test_start_spawns_process(self, tmp_path):
        """start() should spawn a subprocess and detect it within 3s."""
        import runtime.daemon as _mod

        pid_file = tmp_path / "flowcore.pid"
        state_file = tmp_path / "state.json"
        log_file = tmp_path / "daemon.log"

        with (
            patch.object(_mod, "_DAEMON_DIR", tmp_path),
            patch.object(_mod, "_PID_FILE", pid_file),
            patch.object(_mod, "_STATE_FILE", state_file),
            patch.object(_mod, "_LOG_FILE", log_file),
        ):
            from runtime.daemon import FlowCoreDaemon

            d = FlowCoreDaemon()
            result = d.start(interval=999)

        try:
            assert result.get("started") is True or result.get("note") == "already running"
            pid = result.get("pid")
            assert pid and pid > 0
        finally:
            # Clean up: kill the spawned child
            pid = result.get("pid")
            if pid:
                try:
                    os.kill(pid, signal.SIGTERM)
                    time.sleep(0.3)
                except (ProcessLookupError, PermissionError):
                    pass

    def test_double_start_idempotent(self, tmp_path):
        """start() returns 'already running' when daemon is already up."""
        import runtime.daemon as _mod

        pid_file = tmp_path / "flowcore.pid"
        pid_file.write_text("99999")  # simulate a running daemon

        with (
            patch.object(_mod, "_DAEMON_DIR", tmp_path),
            patch.object(_mod, "_PID_FILE", pid_file),
            patch.object(_mod, "_STATE_FILE", tmp_path / "state.json"),
            patch.object(_mod, "_LOG_FILE", tmp_path / "daemon.log"),
            patch.object(_mod, "_pid_alive", return_value=True),
        ):
            from runtime.daemon import FlowCoreDaemon

            d = FlowCoreDaemon()
            result = d.start(interval=999)

        assert result.get("started") is False
        assert result.get("note") == "already running"
        assert result.get("pid") == 99999

    def test_read_pid_returns_none_when_no_file(self, tmp_path):
        import runtime.daemon as _mod

        with patch.object(_mod, "_PID_FILE", tmp_path / "missing.pid"):
            from runtime.daemon import FlowCoreDaemon

            d = FlowCoreDaemon()
            assert d._read_pid() is None

    def test_pid_alive_helper_false_for_bad_pid(self):
        from runtime.daemon import _pid_alive

        assert _pid_alive(999999999) is False

    def test_pid_alive_helper_true_for_self(self):
        from runtime.daemon import _pid_alive

        assert _pid_alive(os.getpid()) is True
