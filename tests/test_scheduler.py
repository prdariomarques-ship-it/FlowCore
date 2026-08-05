"""Tests for runtime.job_scheduler — Job and JobScheduler."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _make_scheduler(tmp_path: Path):
    """Return a JobScheduler backed by a temp jobs file."""
    import runtime.job_scheduler as _mod

    jobs_file = tmp_path / "jobs.json"
    with patch.object(_mod, "_JOBS_FILE", jobs_file):
        from runtime.job_scheduler import JobScheduler

        sched = JobScheduler()
        sched._jobs_file_ref = jobs_file
        return sched, jobs_file


class TestJob:
    def test_to_dict_round_trip(self):
        from runtime.job_scheduler import Job

        j = Job("sync", "/tmp/sync.py", "0 2 * * *")
        d = j.to_dict()
        j2 = Job.from_dict(d)
        assert j2.name == "sync"
        assert j2.script == "/tmp/sync.py"
        assert j2.schedule == "0 2 * * *"
        assert j2.enabled is True

    def test_created_at_defaults_to_now(self):
        from runtime.job_scheduler import Job

        before = time.time()
        j = Job("x", "/tmp/x.py", "* * * * *")
        after = time.time()
        assert before <= j.created_at <= after

    def test_from_dict_preserves_enabled_false(self):
        from runtime.job_scheduler import Job

        j = Job.from_dict(
            {
                "name": "j",
                "script": "/s.py",
                "schedule": "* * * * *",
                "enabled": False,
            }
        )
        assert j.enabled is False


class TestJobScheduler:
    def _fake_script(self, tmp_path: Path, name: str = "dummy.py") -> Path:
        p = tmp_path / name
        p.write_text("print('ok')")
        return p

    def test_list_empty_initially(self, tmp_path):
        import runtime.job_scheduler as _mod

        with patch.object(_mod, "_JOBS_FILE", tmp_path / "jobs.json"):
            from runtime.job_scheduler import JobScheduler

            sched = JobScheduler()
            assert sched.list_jobs() == []

    def test_add_job_persists(self, tmp_path):
        script = self._fake_script(tmp_path)
        import runtime.job_scheduler as _mod

        jobs_file = tmp_path / "jobs.json"
        with (
            patch.object(_mod, "_JOBS_FILE", jobs_file),
            patch.object(_mod, "is_available", return_value=False),
        ):
            from runtime.job_scheduler import JobScheduler

            sched = JobScheduler()
            sched.add_job("nightly", str(script), "0 2 * * *")

        data = json.loads(jobs_file.read_text())
        assert any(j["name"] == "nightly" for j in data)

    def test_add_job_invalid_name_raises(self, tmp_path):
        script = self._fake_script(tmp_path)
        import runtime.job_scheduler as _mod

        with (
            patch.object(_mod, "_JOBS_FILE", tmp_path / "jobs.json"),
            patch.object(_mod, "is_available", return_value=False),
        ):
            from runtime.job_scheduler import JobScheduler

            sched = JobScheduler()
            with pytest.raises(ValueError, match="Invalid job name"):
                sched.add_job("bad name!", str(script), "* * * * *")

    def test_add_job_missing_script_raises(self, tmp_path):
        import runtime.job_scheduler as _mod

        with (
            patch.object(_mod, "_JOBS_FILE", tmp_path / "jobs.json"),
            patch.object(_mod, "is_available", return_value=False),
        ):
            from runtime.job_scheduler import JobScheduler

            sched = JobScheduler()
            with pytest.raises(FileNotFoundError):
                sched.add_job("ok_name", "/nonexistent/path.py", "* * * * *")

    def test_remove_existing_job(self, tmp_path):
        script = self._fake_script(tmp_path)
        import runtime.job_scheduler as _mod

        with (
            patch.object(_mod, "_JOBS_FILE", tmp_path / "jobs.json"),
            patch.object(_mod, "is_available", return_value=False),
        ):
            from runtime.job_scheduler import JobScheduler

            sched = JobScheduler()
            sched.add_job("to_remove", str(script), "* * * * *")
            assert sched.remove_job("to_remove") is True
            assert not any(j["name"] == "to_remove" for j in sched.list_jobs())

    def test_remove_nonexistent_job_returns_false(self, tmp_path):
        import runtime.job_scheduler as _mod

        with patch.object(_mod, "_JOBS_FILE", tmp_path / "jobs.json"):
            from runtime.job_scheduler import JobScheduler

            sched = JobScheduler()
            assert sched.remove_job("ghost") is False

    def test_list_jobs_after_add(self, tmp_path):
        script = self._fake_script(tmp_path)
        import runtime.job_scheduler as _mod

        with (
            patch.object(_mod, "_JOBS_FILE", tmp_path / "jobs.json"),
            patch.object(_mod, "is_available", return_value=False),
        ):
            from runtime.job_scheduler import JobScheduler

            sched = JobScheduler()
            sched.add_job("job_a", str(script), "0 1 * * *")
            sched.add_job("job_b", str(script), "0 3 * * *")
            jobs = sched.list_jobs()
        assert len(jobs) == 2
        names = {j["name"] for j in jobs}
        assert names == {"job_a", "job_b"}

    def test_run_now_unknown_job_raises(self, tmp_path):
        import runtime.job_scheduler as _mod

        with patch.object(_mod, "_JOBS_FILE", tmp_path / "jobs.json"):
            from runtime.job_scheduler import JobScheduler

            sched = JobScheduler()
            with pytest.raises(KeyError):
                sched.run_now("no_such_job")

    def test_run_now_executes_script(self, tmp_path):
        script = self._fake_script(tmp_path, "hello.py")
        script.write_text("print('hello world')")
        import runtime.job_scheduler as _mod

        with (
            patch.object(_mod, "_JOBS_FILE", tmp_path / "jobs.json"),
            patch.object(_mod, "is_available", return_value=False),
        ):
            from runtime.job_scheduler import JobScheduler

            sched = JobScheduler()
            sched.add_job("hello", str(script), "* * * * *")
            result = sched.run_now("hello")
        assert result["success"] is True
        assert "hello world" in result["output"]

    def test_jobs_survive_reload(self, tmp_path):
        """Jobs persisted to disk are loaded by a fresh JobScheduler instance."""
        script = self._fake_script(tmp_path)
        jobs_file = tmp_path / "persist.json"
        import runtime.job_scheduler as _mod

        with (
            patch.object(_mod, "_JOBS_FILE", jobs_file),
            patch.object(_mod, "is_available", return_value=False),
        ):
            from runtime.job_scheduler import JobScheduler

            s1 = JobScheduler()
            s1.add_job("persistent", str(script), "0 0 * * *")

        with (
            patch.object(_mod, "_JOBS_FILE", jobs_file),
            patch.object(_mod, "is_available", return_value=False),
        ):
            from runtime.job_scheduler import JobScheduler as JS2

            s2 = JS2()
            assert any(j["name"] == "persistent" for j in s2.list_jobs())
