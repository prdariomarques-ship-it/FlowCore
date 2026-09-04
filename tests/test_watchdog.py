"""Tests for runtime.watchdog — Self-Healing Watchdog."""

from __future__ import annotations

import json
import sys
import time
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch, tmp_path):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    import runtime.watchdog as _wd
    monkeypatch.setattr(_wd, "_STATE_FILE", tmp_path / "watchdog.state.json")
    monkeypatch.setattr(_wd, "_BOTS_DIR", tmp_path / "bots")


class TestWatchResult:
    def test_ok_property(self):
        from runtime.watchdog import WatchResult, WatchStatus

        r = WatchResult("svc", WatchStatus.OK, "fine")
        assert r.ok is True
        assert r.failed is False

    def test_fail_property(self):
        from runtime.watchdog import WatchResult, WatchStatus

        r = WatchResult("svc", WatchStatus.FAIL, "down")
        assert r.ok is False
        assert r.failed is True


class TestWatchdogReport:
    def test_healthy_when_all_ok(self):
        from runtime.watchdog import WatchResult, WatchStatus, WatchdogReport

        report = WatchdogReport(results=[WatchResult("a", WatchStatus.OK, "fine")])
        assert report.healthy is True

    def test_unhealthy_on_fail(self):
        from runtime.watchdog import WatchResult, WatchStatus, WatchdogReport

        report = WatchdogReport(results=[WatchResult("a", WatchStatus.FAIL, "down")])
        assert report.healthy is False

    def test_to_dict_shape(self):
        from runtime.watchdog import WatchResult, WatchStatus, WatchdogReport

        report = WatchdogReport(results=[WatchResult("a", WatchStatus.OK, "fine")])
        d = report.to_dict()
        assert "healthy" in d
        assert "results" in d
        assert d["results"][0]["name"] == "a"


class TestFlowcoreApiCheck:
    def _svc(self):
        from runtime.watchdog import WatchdogService

        return WatchdogService(api_url="http://127.0.0.1:19999/api/health")

    def test_ok_when_api_responds(self):
        from runtime.watchdog import WatchStatus

        mock_resp = MagicMock()
        mock_resp.__enter__.return_value.read.return_value = json.dumps({"status": "ok", "uptime_seconds": 42}).encode()
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = self._svc()._check_flowcore_api()
        assert result.status == WatchStatus.OK

    def test_fail_when_connection_refused(self):
        from runtime.watchdog import WatchStatus

        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
            result = self._svc()._check_flowcore_api()
        assert result.status == WatchStatus.FAIL
        assert result.fix  # has a fix suggestion

    def test_warn_when_status_not_ok(self):
        from runtime.watchdog import WatchStatus

        mock_resp = MagicMock()
        mock_resp.__enter__.return_value.read.return_value = json.dumps({"status": "degraded"}).encode()
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = self._svc()._check_flowcore_api()
        assert result.status == WatchStatus.WARN


class TestCloudflaredCheck:
    def _svc(self):
        from runtime.watchdog import WatchdogService

        return WatchdogService()

    def test_ok_when_running(self):
        from runtime.watchdog import WatchStatus

        with patch("runtime.watchdog.WatchdogService._process_running", return_value=True):
            result = self._svc()._check_cloudflared()
        assert result.status == WatchStatus.OK

    def test_fail_when_not_running(self):
        from runtime.watchdog import WatchStatus

        with patch("runtime.watchdog.WatchdogService._process_running", return_value=False):
            result = self._svc()._check_cloudflared()
        assert result.status == WatchStatus.FAIL
        assert result.fix


class TestBotChecks:
    def _svc(self, tmp_path):
        from runtime.watchdog import WatchdogService

        svc = WatchdogService()
        return svc

    def test_skip_when_no_bots_dir(self):
        from runtime.watchdog import WatchdogService

        svc = WatchdogService()
        results = svc._check_bots()
        # All bots skip when dir doesn't exist
        statuses = {r.status.value for r in results}
        assert statuses <= {"skip"}

    def test_ok_when_bot_running(self, tmp_path):
        from runtime.watchdog import WatchdogService

        bots_dir = tmp_path / "bots"
        bots_dir.mkdir()
        (bots_dir / "signal-engine.sh").write_text("#!/bin/bash\n")

        with patch("runtime.watchdog._BOTS_DIR", bots_dir), \
             patch("runtime.watchdog.WatchdogService._process_running", return_value=True):
            svc = WatchdogService()
            results = svc._check_bots()

        signal_result = next((r for r in results if "signal-engine" in r.name), None)
        assert signal_result is not None
        assert signal_result.status.value == "ok"

    def test_fail_when_bot_not_running_and_restart_fails(self, tmp_path):
        from runtime.watchdog import WatchdogService, WatchStatus

        bots_dir = tmp_path / "bots"
        bots_dir.mkdir()
        (bots_dir / "signal-engine.sh").write_text("#!/bin/bash\n")

        with patch("runtime.watchdog._BOTS_DIR", bots_dir), \
             patch("runtime.watchdog.WatchdogService._process_running", return_value=False), \
             patch("runtime.watchdog.WatchdogService._try_restart", return_value=True):
            svc = WatchdogService()
            results = svc._check_bots()

        signal_result = next((r for r in results if "signal-engine" in r.name), None)
        assert signal_result is not None
        assert signal_result.status == WatchStatus.FAIL
        assert signal_result.restart_attempted is True


class TestAlertDeduplication:
    def _svc(self, tmp_path):
        from runtime.watchdog import WatchdogService

        return WatchdogService()

    def test_alert_fires_on_first_failure(self, tmp_path):
        from runtime.watchdog import WatchResult, WatchStatus, WatchdogReport, WatchdogService

        svc = WatchdogService()
        report = WatchdogReport(results=[WatchResult("flowcore_api", WatchStatus.FAIL, "down")])

        with patch("runtime.watchdog.WatchdogService._send_telegram", return_value=True) as mock_tg:
            svc._process_alerts(report)

        mock_tg.assert_called_once()
        assert "flowcore_api" in report.alerts_sent

    def test_no_duplicate_alert_for_same_failure(self, tmp_path):
        from runtime.watchdog import WatchResult, WatchStatus, WatchdogReport, WatchdogService

        svc = WatchdogService()
        # Simulate prior state: already known to be failing
        svc._state = {"service_status": {"flowcore_api": "fail"}, "last_run": time.time()}
        report = WatchdogReport(results=[WatchResult("flowcore_api", WatchStatus.FAIL, "still down")])

        with patch("runtime.watchdog.WatchdogService._send_telegram", return_value=True) as mock_tg:
            svc._process_alerts(report)

        mock_tg.assert_not_called()

    def test_recovery_alert_when_service_comes_back(self, tmp_path):
        from runtime.watchdog import WatchResult, WatchStatus, WatchdogReport, WatchdogService

        svc = WatchdogService()
        svc._state = {"service_status": {"flowcore_api": "fail"}, "last_run": time.time()}
        report = WatchdogReport(results=[WatchResult("flowcore_api", WatchStatus.OK, "back up")])

        with patch("runtime.watchdog.WatchdogService._send_telegram", return_value=True) as mock_tg:
            svc._process_alerts(report)

        mock_tg.assert_called_once()
        assert "flowcore_api" in report.recoveries_sent


class TestStatePersistence:
    def test_state_saved_and_loaded(self, tmp_path):
        from runtime.watchdog import WatchResult, WatchStatus, WatchdogReport, WatchdogService

        svc = WatchdogService()
        results = [WatchResult("flowcore_api", WatchStatus.OK, "ok")]
        report = WatchdogReport(results=results)
        svc._save_state(results, report)

        loaded = svc._load_state()
        assert loaded["service_status"]["flowcore_api"] == "ok"

    def test_load_returns_empty_if_no_file(self, tmp_path):
        from runtime.watchdog import WatchdogService

        svc = WatchdogService()
        state = svc._load_state()
        assert state["service_status"] == {}


class TestFullRun:
    def test_run_returns_report(self):
        from runtime.watchdog import WatchdogService

        svc = WatchdogService()
        with patch.object(svc, "_collect", return_value=[]):
            report = svc.run(alert=False)

        assert report is not None
        assert hasattr(report, "healthy")

    def test_run_no_telegram_when_alert_false(self):
        from runtime.watchdog import WatchResult, WatchStatus, WatchdogService

        svc = WatchdogService()
        with patch.object(svc, "_collect", return_value=[WatchResult("flowcore_api", WatchStatus.FAIL, "down")]), \
             patch.object(svc, "_send_telegram") as mock_tg:
            svc.run(alert=False)

        mock_tg.assert_not_called()
