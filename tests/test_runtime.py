"""Tests for runtime.discovery and runtime.kernel."""

from __future__ import annotations

import os
import sys
import json
from pathlib import Path

import pytest

# Ensure project root is importable
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ── RuntimeDiscovery ──────────────────────────────────────────────────────────


class TestRuntimeDiscovery:
    def _discovery(self):
        from runtime.discovery import RuntimeDiscovery

        return RuntimeDiscovery()

    def test_run_returns_snapshot(self):
        from runtime.discovery import RuntimeSnapshot

        snap = self._discovery().run()
        assert isinstance(snap, RuntimeSnapshot)

    def test_platform_type_is_string(self):
        snap = self._discovery().run()
        assert snap.platform_type in ("termux", "android", "docker", "linux", "macos", "windows")

    def test_python_version_present(self):
        snap = self._discovery().run()
        assert snap.python_version
        assert "." in snap.python_version

    def test_python_path_is_executable(self):
        snap = self._discovery().run()
        assert snap.python_path
        assert os.path.exists(snap.python_path)

    def test_env_home_is_set(self):
        snap = self._discovery().run()
        assert snap.env.home

    def test_tools_are_dict(self):
        snap = self._discovery().run()
        assert isinstance(snap.tools, dict)
        assert "python3" in snap.tools or "python" in snap.tools

    def test_to_dict_serialisable(self):
        snap = self._discovery().run()
        d = snap.to_dict()
        # Must be JSON-serialisable
        json.dumps(d)

    def test_capabilities_is_list_of_strings(self):
        snap = self._discovery().run()
        assert isinstance(snap.capabilities, list)
        assert all(isinstance(c, str) for c in snap.capabilities)

    def test_read_file_cap_on_non_windows(self):
        if sys.platform == "win32":
            pytest.skip("Linux-only")
        snap = self._discovery().run()
        assert "readFile" in snap.capabilities
        assert "writeFile" in snap.capabilities
        assert "listDirectory" in snap.capabilities

    def test_run_shell_cap_on_non_windows(self):
        if sys.platform == "win32":
            pytest.skip("Linux-only")
        snap = self._discovery().run()
        assert "runShell" in snap.capabilities


# ── RuntimeKernel ─────────────────────────────────────────────────────────────


class TestRuntimeKernel:
    def test_boot_returns_passport(self):
        from runtime.kernel import RuntimeKernel, RuntimePassport

        kernel = RuntimeKernel()
        passport = kernel.boot()
        assert isinstance(passport, RuntimePassport)

    def test_passport_has_platform(self):
        from runtime.kernel import RuntimeKernel

        passport = RuntimeKernel().boot()
        assert passport.platform in ("termux", "android", "docker", "linux", "macos", "windows")

    def test_passport_capabilities_list(self):
        from runtime.kernel import RuntimeKernel

        passport = RuntimeKernel().boot()
        assert isinstance(passport.capabilities, list)

    def test_passport_written_to_disk(self):
        from runtime.kernel import RuntimeKernel

        RuntimeKernel().boot()
        runtime_json = Path.home() / ".flowcore" / "flowcore.runtime.json"
        assert runtime_json.exists()
        data = json.loads(runtime_json.read_text())
        assert "platform_type" in data
        assert "generated_at" in data

    def test_unwritable_runtime_json_does_not_abort_boot(self, monkeypatch, tmp_path):
        """A storage failure while persisting flowcore.runtime.json (read-only
        home, permissions, disk full) must not discard an otherwise-successful
        boot -- same reasoning as runtime/core.py's equivalent Doctor-history
        test. Reproduced against the pre-fix code before this test was added
        (PermissionError escaping boot())."""
        if sys.platform == "win32" or (hasattr(os, "geteuid") and os.geteuid() == 0):
            pytest.skip("POSIX file-permission semantics required, and root bypasses them")

        from runtime.kernel import RuntimeKernel

        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        flowcore_dir = tmp_path / ".flowcore"
        flowcore_dir.mkdir(parents=True)
        flowcore_dir.chmod(0o500)
        try:
            passport = RuntimeKernel().boot()  # must not raise
        finally:
            flowcore_dir.chmod(0o700)

        assert passport.platform in ("termux", "android", "docker", "linux", "macos", "windows")
        assert not (flowcore_dir / "flowcore.runtime.json").exists()

    def test_boot_twice_is_idempotent(self):
        from runtime.kernel import RuntimeKernel

        p1 = RuntimeKernel().boot()
        p2 = RuntimeKernel().boot()
        assert p1.platform == p2.platform
        assert set(p1.capabilities) == set(p2.capabilities)
