"""Tests for doctor.service.DoctorService."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestDoctorService:
    def _doctor(self):
        from doctor.service import DoctorService

        return DoctorService()

    def test_run_returns_report(self):
        from doctor.service import DoctorReport

        report = self._doctor().run()
        assert isinstance(report, DoctorReport)

    def test_report_has_checks(self):
        report = self._doctor().run()
        assert len(report.checks) > 0

    def test_passed_plus_failed_plus_warned_plus_skip_equals_total(self):
        from doctor.service import CheckStatus

        report = self._doctor().run()
        total = (
            report.passed
            + report.warned
            + report.failed
            + sum(1 for c in report.checks if c.status == CheckStatus.SKIP)
        )
        assert total == len(report.checks)

    def test_healthy_is_bool(self):
        report = self._doctor().run()
        assert isinstance(report.healthy, bool)

    def test_to_dict_serialisable(self):
        import json

        report = self._doctor().run()
        d = report.to_dict()
        json.dumps(d)

    def test_to_dict_keys(self):
        d = self._doctor().run().to_dict()
        assert "passed" in d
        assert "failed" in d
        assert "healthy" in d
        assert "checks" in d

    def test_check_result_ok_property(self):
        from doctor.service import CheckResult, CheckStatus

        c = CheckResult("x", CheckStatus.OK, "good")
        assert c.ok is True
        assert c.failed is False

    def test_check_result_failed_property(self):
        from doctor.service import CheckResult, CheckStatus

        c = CheckResult("x", CheckStatus.FAIL, "bad")
        assert c.failed is True
        assert c.ok is False

    def test_exception_in_check_does_not_crash(self):
        doc = self._doctor()
        original_checks = doc._checks

        def _bad_check():
            raise RuntimeError("unexpected!")

        doc._checks = [_bad_check]
        report = doc.run()
        assert len(report.checks) == 1
        assert report.checks[0].failed is True
        doc._checks = original_checks

    def test_python3_check_passes(self):
        report = self._doctor().run()
        python_check = next((c for c in report.checks if c.name == "python3"), None)
        assert python_check is not None
        assert python_check.ok, f"Expected python3 OK, got: {python_check.message}"

    def test_android_checks_skip_on_non_termux(self):
        from doctor.service import CheckStatus

        if os.environ.get("PREFIX"):
            pytest.skip("Running in Termux — Android checks are not skipped")
        report = self._doctor().run()
        android_checks = [
            c
            for c in report.checks
            if c.name
            in (
                "termux_detected",
                "termux_api",
                "termux_storage",
                "termux_pkg",
                "wakelock",
                "camera",
                "microphone",
                "location",
                "bluetooth",
                "vibrate",
                "torch",
                "share",
            )
        ]
        for check in android_checks:
            assert check.status == CheckStatus.SKIP, (
                f"Expected {check.name} to SKIP outside Termux, got {check.status}: {check.message}"
            )

    def test_runtime_json_check_present(self):
        report = self._doctor().run()
        rj = next((c for c in report.checks if c.name == "runtime_json"), None)
        assert rj is not None

    def test_flowcore_config_check_present(self):
        report = self._doctor().run()
        cfg = next((c for c in report.checks if c.name == "flowcore_config"), None)
        assert cfg is not None


class TestDoctorServiceMode:
    """Tests for the background service mode."""

    def test_start_stop_service(self):
        from doctor.service import DoctorService

        doc = DoctorService()
        assert not doc.is_running
        doc.start_service(interval=1)
        assert doc.is_running
        time.sleep(0.2)
        doc.stop_service()
        assert not doc.is_running

    def test_start_twice_is_safe(self):
        from doctor.service import DoctorService

        doc = DoctorService()
        doc.start_service(interval=60)
        doc.start_service(interval=60)  # second call should be a no-op
        assert doc.is_running
        doc.stop_service()

    def test_stop_without_start_is_safe(self):
        from doctor.service import DoctorService

        doc = DoctorService()
        doc.stop_service()  # should not raise
        assert not doc.is_running
