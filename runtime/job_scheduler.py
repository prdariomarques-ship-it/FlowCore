"""FlowCore — Job Scheduler.

Schedules recurring tasks via crontab (Linux/Termux) or
termux-job-scheduler (Android). All job definitions are persisted to
~/.flowcore/jobs.json so they survive restarts.

Usage::

    sched = JobScheduler()
    sched.add_job("nightly_sync", "/data/data/com.termux/files/home/sync.py",
                  "0 2 * * *")   # every night at 02:00
    sched.list_jobs()
    sched.run_now("nightly_sync")
    sched.remove_job("nightly_sync")
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

from loguru import logger
from runtime.shell import is_available, run, which


_JOBS_FILE = Path.home() / ".flowcore" / "jobs.json"

_NAME_SAFE = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
)


class Job:
    def __init__(self, name: str, script: str, schedule: str,
                 *, enabled: bool = True, created_at: float | None = None) -> None:
        self.name = name
        self.script = script
        self.schedule = schedule
        self.enabled = enabled
        self.created_at = created_at or time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "script": self.script,
            "schedule": self.schedule,
            "enabled": self.enabled,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Job":
        return cls(
            name=d["name"],
            script=d["script"],
            schedule=d["schedule"],
            enabled=d.get("enabled", True),
            created_at=d.get("created_at"),
        )


class JobScheduler:
    """Manages recurring jobs backed by crontab or termux-job-scheduler."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._load()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self) -> None:
        if _JOBS_FILE.exists():
            try:
                self._jobs = {
                    d["name"]: Job.from_dict(d)
                    for d in json.loads(_JOBS_FILE.read_text())
                }
            except Exception:
                self._jobs = {}

    def _save(self) -> None:
        _JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _JOBS_FILE.write_text(
            json.dumps([j.to_dict() for j in self._jobs.values()], indent=2)
        )

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def add_job(self, name: str, script: str, schedule: str) -> bool:
        """Add job and register with system scheduler. Returns True on success."""
        if not all(c in _NAME_SAFE for c in name):
            raise ValueError(f"Invalid job name {name!r} — only letters, digits, _ and - allowed")
        if not Path(script).exists():
            raise FileNotFoundError(f"Script not found: {script}")
        job = Job(name, script, schedule)
        self._jobs[name] = job
        self._save()
        ok = self._register(job)
        logger.info("JobScheduler: added '{}' schedule={} registered={}", name, schedule, ok)
        return ok

    def remove_job(self, name: str) -> bool:
        """Remove job from registry and system scheduler."""
        if name not in self._jobs:
            return False
        job = self._jobs.pop(name)
        self._save()
        self._unregister(job)
        logger.info("JobScheduler: removed '{}'", name)
        return True

    def list_jobs(self) -> list[dict[str, Any]]:
        return [j.to_dict() for j in self._jobs.values()]

    def run_now(self, name: str) -> dict[str, Any]:
        """Execute job immediately, synchronously."""
        if name not in self._jobs:
            raise KeyError(f"Job not found: {name!r}")
        job = self._jobs[name]
        python = which("python3") or "python3"
        result = run([python, job.script], timeout=120)
        return {
            "name": name,
            "success": result.success,
            "output": result.stdout,
            "error": result.stderr,
            "returncode": result.returncode,
        }

    # ── System scheduler integration ──────────────────────────────────────────

    def _register(self, job: Job) -> bool:
        if is_available("crontab"):
            return self._register_cron(job)
        if is_available("termux-job-scheduler"):
            return self._register_termux(job)
        logger.warning("JobScheduler: no system scheduler available (crontab / termux-job-scheduler)")
        return False

    def _unregister(self, job: Job) -> None:
        if is_available("crontab"):
            self._unregister_cron(job)

    def _register_cron(self, job: Job) -> bool:
        python = which("python3") or "python3"
        tag = f"# flowcore:{job.name}"
        cron_line = f"{job.schedule} {python} {job.script}  {tag}"
        result = run(["crontab", "-l"], timeout=5)
        existing = result.stdout if result.success else ""
        lines = [l for l in existing.splitlines() if tag not in l]
        lines.append(cron_line)
        new_crontab = "\n".join(lines) + "\n"
        proc = subprocess.Popen(
            ["crontab", "-"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        _, err = proc.communicate(new_crontab.encode())
        if proc.returncode != 0:
            logger.error("crontab write failed: {}", err.decode())
            return False
        return True

    def _unregister_cron(self, job: Job) -> None:
        result = run(["crontab", "-l"], timeout=5)
        if not result.success:
            return
        tag = f"# flowcore:{job.name}"
        lines = [l for l in result.stdout.splitlines() if tag not in l]
        new_crontab = "\n".join(lines) + "\n"
        proc = subprocess.Popen(
            ["crontab", "-"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        proc.communicate(new_crontab.encode())

    def _register_termux(self, job: Job) -> bool:
        result = run(
            ["termux-job-scheduler", "--script", job.script, "--period-ms", "3600000"],
            timeout=10,
        )
        return result.success
