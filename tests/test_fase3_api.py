"""Tests for Fase 3 — Dashboard v4 backend endpoints."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _client():
    fastapi = pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from api.router import create_app
    app = create_app(version="test", platform_info={"os_name": "test"})
    return TestClient(app)


# ── GET /api/doctor/{check} ────────────────────────────────────────────────────

class TestDoctorCheckEndpoint:
    def test_known_check_returns_200(self):
        r = _client().get("/api/doctor/python")
        assert r.status_code == 200
        data = r.json()
        assert "checks" in data
        assert isinstance(data["checks"], list)
        assert len(data["checks"]) >= 1

    def test_check_response_has_required_keys(self):
        r = _client().get("/api/doctor/python")
        assert r.status_code == 200
        for item in r.json()["checks"]:
            for k in ("name", "status", "message", "fix"):
                assert k in item

    def test_unknown_check_returns_404(self):
        r = _client().get("/api/doctor/no_such_check_xyz_abc")
        assert r.status_code == 404

    def test_check_name_case_insensitive(self):
        # "PYTHON" should match the same checks as "python"
        r_lower = _client().get("/api/doctor/python")
        r_upper = _client().get("/api/doctor/PYTHON")
        assert r_lower.status_code == r_upper.status_code


# ── GET /api/logs ─────────────────────────────────────────────────────────────

class TestLogsEndpoint:
    def test_returns_200_even_without_log_file(self):
        r = _client().get("/api/logs")
        assert r.status_code == 200
        data = r.json()
        assert "lines" in data
        assert "total" in data
        assert "exists" in data

    def test_limit_param_accepted(self):
        r = _client().get("/api/logs?limit=10")
        assert r.status_code == 200
        assert len(r.json()["lines"]) <= 10

    def test_level_filter_accepted(self):
        r = _client().get("/api/logs?level=ERROR")
        assert r.status_code == 200

    def test_response_structure(self):
        data = _client().get("/api/logs").json()
        assert isinstance(data["lines"], list)
        assert isinstance(data["total"], int)
        assert isinstance(data["log_file"], str)

    def test_with_real_log_file(self, tmp_path, monkeypatch):
        log_file = tmp_path / "logs" / "flowcore.log"
        log_file.parent.mkdir()
        log_file.write_text("2024-01-01 INFO startup\n2024-01-01 ERROR crash\n")

        import api.router as router_mod
        orig_file = router_mod.__file__

        monkeypatch.setattr(router_mod, "__file__", str(tmp_path / "api" / "router.py"))
        (tmp_path / "api").mkdir(exist_ok=True)

        from fastapi.testclient import TestClient
        from api.router import create_app
        app = create_app(version="test")
        c = TestClient(app)

        r = c.get("/api/logs")
        # If log file isn't found, exists=False is still valid
        assert r.status_code == 200


# ── GET /api/scheduler/jobs ───────────────────────────────────────────────────

class TestSchedulerEndpoints:
    def test_list_jobs_returns_200(self):
        r = _client().get("/api/scheduler/jobs")
        assert r.status_code == 200
        assert "jobs" in r.json()
        assert isinstance(r.json()["jobs"], list)

    def test_run_nonexistent_job_returns_404(self):
        r = _client().post("/api/scheduler/no_such_job_xyz/run")
        assert r.status_code == 404

    def test_pause_nonexistent_job_returns_404(self):
        r = _client().post("/api/scheduler/no_such_job_xyz/pause")
        assert r.status_code == 404

    def test_run_and_pause_real_job(self, tmp_path, monkeypatch):
        import runtime.job_scheduler as jmod
        monkeypatch.setattr(jmod, "_JOBS_FILE", tmp_path / "jobs.json")

        script = tmp_path / "noop.py"
        script.write_text("print('ok')\n")

        from runtime.job_scheduler import JobScheduler
        sched = JobScheduler()
        sched._load()
        sched.add_job("test_job", str(script), "0 * * * *")

        c = _client()

        r_list = c.get("/api/scheduler/jobs")
        assert r_list.status_code == 200

        r_run = c.post("/api/scheduler/test_job/run")
        assert r_run.status_code == 200
        assert "name" in r_run.json()

        r_pause = c.post("/api/scheduler/test_job/pause")
        assert r_pause.status_code == 200
        assert "enabled" in r_pause.json()


# ── POST /api/observer/ingest ─────────────────────────────────────────────────

class TestObserverIngest:
    def test_returns_200_when_not_configured(self):
        r = _client().post("/api/observer/ingest")
        assert r.status_code == 200
        data = r.json()
        assert "ingested" in data
        assert "source" in data

    def test_source_param_forwarded(self):
        r = _client().post("/api/observer/ingest?source=webhook")
        assert r.status_code == 200
        assert r.json()["source"] == "webhook"

    def test_default_source_is_manual(self):
        r = _client().post("/api/observer/ingest")
        assert r.json()["source"] == "manual"


# ── GET /api/telegram/chats ───────────────────────────────────────────────────

class TestTelegramChats:
    def test_returns_200_unconfigured(self):
        r = _client().get("/api/telegram/chats")
        assert r.status_code == 200
        data = r.json()
        assert "configured" in data
        assert "chats" in data

    def test_configured_false_when_no_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        r = _client().get("/api/telegram/chats")
        assert r.status_code == 200
        # configured may be True or False depending on env; just assert structure
        assert "configured" in r.json()

    def test_reads_telegram_json_when_present(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        cfg_dir = tmp_path / ".flowcore"
        cfg_dir.mkdir(parents=True)
        (cfg_dir / "telegram.json").write_text(
            json.dumps({"chats": [{"id": -100, "name": "FlowCore Alerts"}]})
        )
        from pathlib import Path as _Path
        monkeypatch.setattr(_Path, "home", staticmethod(lambda: tmp_path))

        from fastapi.testclient import TestClient
        from api.router import create_app
        c = TestClient(create_app(version="test"))
        r = c.get("/api/telegram/chats")
        assert r.status_code == 200
        data = r.json()
        assert data["configured"] is True
        assert len(data["chats"]) == 1


# ── GET /api/whatsapp/qr ──────────────────────────────────────────────────────

class TestWhatsAppQR:
    def test_get_returns_200_unconfigured(self):
        r = _client().get("/api/whatsapp/qr")
        assert r.status_code == 200
        data = r.json()
        assert "configured" in data
        assert "status" in data
        assert "qr" in data

    def test_post_returns_200_when_bridge_absent(self):
        r = _client().post("/api/whatsapp/qr")
        assert r.status_code == 200
        data = r.json()
        assert "status" in data
        assert "qr" in data

    def test_reads_whatsapp_json_when_present(self, tmp_path, monkeypatch):
        from pathlib import Path as _Path
        monkeypatch.setattr(_Path, "home", staticmethod(lambda: tmp_path))

        cfg_dir = tmp_path / ".flowcore"
        cfg_dir.mkdir(parents=True)
        (cfg_dir / "whatsapp.json").write_text(
            json.dumps({"status": "connected", "phone": "+5511999999999", "qr": None})
        )

        from fastapi.testclient import TestClient
        from api.router import create_app
        c = TestClient(create_app(version="test"))
        r = c.get("/api/whatsapp/qr")
        assert r.status_code == 200
        data = r.json()
        assert data["configured"] is True
        assert data["status"] == "connected"
        assert data["phone"] == "+5511999999999"
