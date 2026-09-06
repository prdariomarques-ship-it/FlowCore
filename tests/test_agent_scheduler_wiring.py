"""Tests for api/router.py's autonomous-agent scheduler wiring --
create_app() starting/stopping a real background SchedulerService running
agents/observer_loop.py, independent of any browser/HTTP request.

Kept in its own file (not tests/test_api.py) because, unlike every other
create_app() test in this suite, these deliberately use a NON-"test"
version string to exercise the wiring itself -- see api/router.py's
comment on why version=="test" is the universal sentinel every other
test relies on to skip this.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("apscheduler")

from fastapi.testclient import TestClient  # noqa: E402

from api.router import create_app  # noqa: E402


class TestSchedulerNeverRunsForTestApps:
    def test_version_test_has_no_agent_scheduler_attribute(self):
        app = create_app(version="test")
        assert not hasattr(app.state, "agent_scheduler")

    def test_flowcore_autonomous_agents_env_var_disables_it(self, monkeypatch):
        monkeypatch.setenv("FLOWCORE_AUTONOMOUS_AGENTS", "0")
        app = create_app(version="0.0.1-disabled")
        assert not hasattr(app.state, "agent_scheduler")


class TestSchedulerWiringForRealApps:
    def test_starts_and_registers_the_observer_job(self, monkeypatch):
        monkeypatch.delenv("FLOWCORE_AUTONOMOUS_AGENTS", raising=False)
        app = create_app(version="0.0.1-real")
        assert app.state.agent_scheduler is not None

        with patch("agents.observer_loop.observe_and_dispatch", return_value={"offices_checked": 0}):
            with TestClient(app):
                assert app.state.agent_scheduler.is_running is True
                jobs = app.state.agent_scheduler.list_tasks()
                assert any(j["id"] == "agent_observer_loop" for j in jobs)
        assert app.state.agent_scheduler.is_running is False

    def test_interval_is_configurable_via_env_var(self, monkeypatch):
        monkeypatch.setenv("FLOWCORE_AGENT_OBSERVE_INTERVAL_SECONDS", "17")
        app = create_app(version="0.0.1-real-interval")
        with patch("agents.observer_loop.observe_and_dispatch", return_value={"offices_checked": 0}):
            with TestClient(app):
                job = app.state.agent_scheduler._jobs["agent_observer_loop"]
                assert job.trigger.interval.total_seconds() == 17

    def test_missing_apscheduler_degrades_instead_of_crashing_app_creation(self, monkeypatch):
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name.startswith("apscheduler") or name == "scheduler.service":
                raise ImportError("simulated missing apscheduler")
            return real_import(name, *args, **kwargs)

        import sys as _sys
        for mod in list(_sys.modules):
            if mod.startswith("scheduler"):
                monkeypatch.delitem(_sys.modules, mod, raising=False)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        app = create_app(version="0.0.1-no-apscheduler")
        assert app.state.agent_scheduler is None
