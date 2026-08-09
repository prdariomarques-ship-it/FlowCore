"""Tests for runtime.core.FlowCoreRuntime — the Doctor Flow vertical slice
(Sprint 25): USER -> CLI -> Runtime -> Capability Registry -> Doctor
Capability -> Execution -> real result -> Observability -> History.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestDetectPlatform:
    def test_returns_expected_keys(self):
        from runtime.core import detect_platform

        info = detect_platform()
        for key in ("termux", "android", "python_version", "os_name", "prefix"):
            assert key in info


class TestRunDoctor:
    def _runtime(self):
        from runtime.core import FlowCoreRuntime

        return FlowCoreRuntime()

    def test_returns_expected_shape(self):
        report = self._runtime().run_doctor()
        for key in ("generated_at", "environment", "cpu", "memory", "disk", "components"):
            assert key in report

    def test_cpu_and_memory_are_capability_results(self):
        report = self._runtime().run_doctor()
        assert "success" in report["cpu"]
        assert "success" in report["memory"]
        assert "success" in report["disk"]

    def test_disk_resolved_for_runtime_root(self, monkeypatch):
        from runtime.core import FlowCoreRuntime

        calls = []

        class _StubResolver:
            def resolve(self, capability, *args, **kwargs):
                calls.append((capability, args))
                from capability.adapters.base import CapabilityResult

                return CapabilityResult.ok({"stub": True}, "stub")

        monkeypatch.setattr("capability.resolver.ProviderResolver", _StubResolver)
        runtime = FlowCoreRuntime()
        report = runtime.run_doctor()

        disk_call = next(c for c in calls if c[0] == "getDiskUsage")
        assert disk_call[1] == (str(runtime.root),)
        assert report["disk"]["data"] == {"stub": True}

    def test_components_come_from_doctor_service(self):
        report = self._runtime().run_doctor()
        components = report["components"]
        assert "checks" in components and len(components["checks"]) > 0
        assert "healthy" in components

    def test_result_is_json_serialisable(self):
        report = self._runtime().run_doctor()
        json.dumps(report)  # must not raise

    def test_persists_history_file(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        report = self._runtime().run_doctor()

        history_path = tmp_path / ".flowcore" / "flowcore.doctor.json"
        assert history_path.exists()
        persisted = json.loads(history_path.read_text())
        assert persisted["generated_at"] == report["generated_at"]
        assert persisted["environment"] == report["environment"]
