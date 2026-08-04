"""FlowCore Termux Runtime Adapters.

Each class handles ONE capability domain using standard Linux tools
available inside Termux (or any Linux environment).

Priority 80 — second preference, after Android-specific adapters.

The agent layer never sees: python3, git, ssh, sqlite3, pkg, ls, curl.
"""
from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

from capability.adapters.base import CapabilityAdapter, CapabilityResult
from runtime.shell import is_available, run, which


# ── Python ────────────────────────────────────────────────────────────────────

class TermuxPythonAdapter(CapabilityAdapter):
    name = "termux.python"
    priority = 80

    def is_available(self) -> bool:
        return is_available("python3") or is_available("python")

    def run_python(self, script: str, args: list[str] | None = None) -> CapabilityResult:
        python = which("python3") or which("python")
        if not python:
            return CapabilityResult.fail("python3 not found", self.name,
                corrective_action="pkg install python")
        script_path = Path(script)
        if not script_path.exists():
            return CapabilityResult.fail(f"Script not found: {script}", self.name,
                reason=f"File does not exist: {script}")
        result = run([python, str(script_path)] + (args or []), timeout=60)
        if result.success:
            return CapabilityResult.ok({"output": result.stdout, "stderr": result.stderr}, self.name)
        return CapabilityResult.fail(result.stderr or result.stdout, self.name,
            reason=f"Python script exited with code {result.returncode}",
            diagnosis=(result.stderr or result.stdout)[:500])


# ── Git ───────────────────────────────────────────────────────────────────────

class TermuxGitAdapter(CapabilityAdapter):
    name = "termux.git"
    priority = 80

    def is_available(self) -> bool:
        return is_available("git")

    def run_git(self, args: list[str]) -> CapabilityResult:
        result = run(["git"] + args, timeout=30)
        if result.success:
            return CapabilityResult.ok({"output": result.stdout}, self.name)
        return CapabilityResult.fail(result.stderr, self.name,
            reason=f"git {' '.join(args[:2])} failed",
            diagnosis=result.stderr[:500],
            corrective_action="pkg install git")


# ── SSH ───────────────────────────────────────────────────────────────────────

class TermuxSSHAdapter(CapabilityAdapter):
    name = "termux.ssh"
    priority = 80

    def is_available(self) -> bool:
        return is_available("ssh")

    def run_ssh(self, host: str, command: str, *, key_path: str | None = None) -> CapabilityResult:
        cmd = ["ssh"]
        if key_path:
            cmd += ["-i", key_path]
        cmd += ["-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=10", host]
        cmd += shlex.split(command)
        result = run(cmd, timeout=30)
        if result.success:
            return CapabilityResult.ok({"output": result.stdout}, self.name)
        return CapabilityResult.fail(result.stderr, self.name,
            reason=f"SSH to {host} failed",
            diagnosis=result.stderr[:500],
            corrective_action="pkg install openssh && check host/key configuration")


# ── SQLite ────────────────────────────────────────────────────────────────────

class TermuxSQLiteAdapter(CapabilityAdapter):
    name = "termux.sqlite"
    priority = 80

    def is_available(self) -> bool:
        return is_available("sqlite3")

    def run_sqlite(self, db_path: str, query: str) -> CapabilityResult:
        result = run(["sqlite3", "-json", db_path, query], timeout=10)
        if result.success:
            import json as _json
            try:
                rows = _json.loads(result.stdout) if result.stdout.strip() else []
                return CapabilityResult.ok({"rows": rows, "count": len(rows)}, self.name)
            except _json.JSONDecodeError:
                return CapabilityResult.ok({"output": result.stdout}, self.name)
        return CapabilityResult.fail(result.stderr, self.name,
            reason="SQLite query failed",
            diagnosis=result.stderr[:500],
            corrective_action="pkg install sqlite")


# ── Filesystem ────────────────────────────────────────────────────────────────

class TermuxFilesystemAdapter(CapabilityAdapter):
    name = "termux.filesystem"
    priority = 80

    def is_available(self) -> bool:
        import sys
        return sys.platform != "win32"

    def read_file(self, path: str) -> CapabilityResult:
        try:
            content = Path(path).read_text(encoding="utf-8")
            return CapabilityResult.ok({"content": content, "path": path}, self.name)
        except PermissionError as e:
            return CapabilityResult.fail(str(e), self.name,
                reason=f"Permission denied reading {path}",
                corrective_action="Check file permissions or run termux-setup-storage")
        except FileNotFoundError:
            return CapabilityResult.fail(f"File not found: {path}", self.name,
                reason=f"Path does not exist: {path}")
        except Exception as e:
            return CapabilityResult.fail(str(e), self.name)

    def write_file(self, path: str, content: str) -> CapabilityResult:
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return CapabilityResult.ok({"written": True, "path": path,
                                        "bytes": len(content.encode())}, self.name)
        except PermissionError as e:
            return CapabilityResult.fail(str(e), self.name,
                reason=f"Permission denied writing {path}",
                corrective_action="Check directory permissions")
        except Exception as e:
            return CapabilityResult.fail(str(e), self.name)

    def list_directory(self, path: str) -> CapabilityResult:
        try:
            entries = sorted(str(p) for p in Path(path).iterdir())
            return CapabilityResult.ok({"entries": entries, "count": len(entries)}, self.name)
        except FileNotFoundError:
            return CapabilityResult.fail(f"Directory not found: {path}", self.name)
        except PermissionError:
            return CapabilityResult.fail(f"Permission denied: {path}", self.name)
        except Exception as e:
            return CapabilityResult.fail(str(e), self.name)


# ── Package management ────────────────────────────────────────────────────────

class TermuxPackageAdapter(CapabilityAdapter):
    name = "termux.package"
    priority = 80

    _SAFE_CHARS = frozenset(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."
    )

    def is_available(self) -> bool:
        return is_available("pkg") or is_available("pip3") or is_available("pip")

    def install_package(self, package: str) -> CapabilityResult:
        if not all(c in self._SAFE_CHARS for c in package):
            return CapabilityResult.fail(f"Invalid package name: {package}", self.name,
                reason="Package name contains unsafe characters")
        if is_available("pkg"):
            result = run(["pkg", "install", "-y", package], timeout=120)
            if result.success:
                return CapabilityResult.ok({"installed": package, "via": "pkg"}, self.name)
        python = which("python3") or which("python")
        if python:
            result = run([python, "-m", "pip", "install", "--quiet", package], timeout=120)
            if result.success:
                return CapabilityResult.ok({"installed": package, "via": "pip"}, self.name)
        return CapabilityResult.fail(f"Could not install {package}", self.name,
            reason="Neither pkg nor pip succeeded",
            corrective_action="pkg install pkg && pkg update")


# ── HTTP ──────────────────────────────────────────────────────────────────────

class TermuxHTTPAdapter(CapabilityAdapter):
    name = "termux.http"
    priority = 80

    def is_available(self) -> bool:
        return True  # urllib always available with Python

    def http_get(self, url: str, *, timeout: int = 10) -> CapabilityResult:
        if is_available("curl"):
            result = run(["curl", "-sS", "--max-time", str(timeout), url], timeout=timeout + 2)
            if result.success:
                return CapabilityResult.ok({"body": result.stdout, "via": "curl"}, self.name)
        try:
            import urllib.request
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                return CapabilityResult.ok({"body": body, "via": "urllib"}, self.name)
        except Exception as e:
            return CapabilityResult.fail(str(e), self.name,
                reason=f"HTTP GET failed for {url}",
                corrective_action="Check network connectivity")


# ── Shell (controlled) ────────────────────────────────────────────────────────

class TermuxShellAdapter(CapabilityAdapter):
    """Execute pre-validated arg lists (no shell=True, no string eval)."""

    name = "termux.shell"
    priority = 75

    def is_available(self) -> bool:
        import sys
        return sys.platform != "win32"

    def run_shell(self, args: list[str], *, timeout: int = 30) -> CapabilityResult:
        if not args:
            return CapabilityResult.fail("No command provided", self.name)
        result = run(args, timeout=timeout)
        if result.success:
            return CapabilityResult.ok({"output": result.stdout,
                                        "returncode": result.returncode}, self.name)
        return CapabilityResult.fail(result.stderr or result.stdout, self.name,
            reason=f"'{args[0]}' exited with code {result.returncode}",
            diagnosis=(result.stderr or result.stdout)[:500])


# ── Services (background processes) ──────────────────────────────────────────

class TermuxServiceAdapter(CapabilityAdapter):
    """Manage long-running background processes with PID tracking."""

    name = "termux.service"
    priority = 75

    _PID_DIR = Path.home() / ".flowcore" / "services"

    def is_available(self) -> bool:
        import sys
        return sys.platform != "win32"

    def start_service(self, name: str, script: str) -> CapabilityResult:
        safe = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")
        if not all(c in safe for c in name):
            return CapabilityResult.fail(f"Invalid service name: {name}", self.name)
        script_path = Path(script)
        if not script_path.exists():
            return CapabilityResult.fail(f"Script not found: {script}", self.name)
        self._PID_DIR.mkdir(parents=True, exist_ok=True)
        pid_file = self._PID_DIR / f"{name}.pid"
        log_file = self._PID_DIR / f"{name}.log"
        python = which("python3") or which("python")
        if not python:
            return CapabilityResult.fail("python3 not found", self.name)
        try:
            with open(log_file, "a") as log:
                proc = subprocess.Popen([python, str(script_path)],
                                        stdout=log, stderr=log, close_fds=True)
            pid_file.write_text(str(proc.pid))
            return CapabilityResult.ok({"name": name, "pid": proc.pid,
                                        "log": str(log_file)}, self.name)
        except Exception as e:
            return CapabilityResult.fail(str(e), self.name)

    def stop_service(self, name: str) -> CapabilityResult:
        pid_file = self._PID_DIR / f"{name}.pid"
        if not pid_file.exists():
            return CapabilityResult.fail(f"Service not running: {name}", self.name,
                corrective_action=f"Start service first")
        try:
            pid = int(pid_file.read_text().strip())
            import signal
            os.kill(pid, signal.SIGTERM)
            pid_file.unlink(missing_ok=True)
            return CapabilityResult.ok({"name": name, "pid": pid, "stopped": True}, self.name)
        except ProcessLookupError:
            pid_file.unlink(missing_ok=True)
            return CapabilityResult.ok({"name": name, "stopped": True,
                                         "note": "Process was already gone"}, self.name)
        except Exception as e:
            return CapabilityResult.fail(str(e), self.name)

    def list_services(self) -> CapabilityResult:
        if not self._PID_DIR.exists():
            return CapabilityResult.ok({"services": []}, self.name)
        services = []
        for pid_file in self._PID_DIR.glob("*.pid"):
            sname = pid_file.stem
            try:
                pid = int(pid_file.read_text().strip())
                try:
                    os.kill(pid, 0)
                    running = True
                except ProcessLookupError:
                    running = False
                services.append({"name": sname, "pid": pid, "running": running})
            except Exception:
                services.append({"name": sname, "pid": None, "running": False})
        return CapabilityResult.ok({"services": services, "count": len(services)}, self.name)

    def schedule_job(self, script: str, schedule: str) -> CapabilityResult:
        if is_available("crontab"):
            python = which("python3") or "python3"
            cron_line = f"{schedule} {python} {script}"
            result = run(["crontab", "-l"], timeout=5)
            existing = result.stdout if result.success else ""
            if cron_line not in existing:
                new_crontab = existing.rstrip("\n") + f"\n{cron_line}\n"
                proc = subprocess.Popen(["crontab", "-"], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                _, stderr = proc.communicate(new_crontab.encode())
                if proc.returncode == 0:
                    return CapabilityResult.ok({"scheduled": cron_line, "via": "crontab"}, self.name)
                return CapabilityResult.fail(stderr.decode(), self.name)
            return CapabilityResult.ok({"note": "already scheduled", "scheduled": cron_line}, self.name)

        if is_available("termux-job-scheduler"):
            result = run(["termux-job-scheduler", "--script", script,
                          "--period-ms", "3600000"], timeout=10)
            if result.success:
                return CapabilityResult.ok({"scheduled": script,
                                            "via": "termux-job-scheduler"}, self.name)

        return CapabilityResult.fail("No scheduler available", self.name,
            corrective_action="pkg install cronie || pkg install termux-api")


# ── Battery fallback (/sys) ───────────────────────────────────────────────────

class TermuxBatteryAdapter(CapabilityAdapter):
    name = "termux.battery"
    priority = 70

    def is_available(self) -> bool:
        return Path("/sys/class/power_supply").exists()

    def get_battery(self) -> CapabilityResult:
        base = Path("/sys/class/power_supply")
        for bname in ["BAT0", "BAT1", "battery"]:
            bp = base / bname
            if not bp.exists():
                continue
            try:
                level = int((bp / "capacity").read_text().strip())
                sf = bp / "status"
                status = sf.read_text().strip().lower() if sf.exists() else "unknown"
                return CapabilityResult.ok({"level": level, "status": status,
                                            "source": "sys"}, self.name)
            except Exception:
                continue
        return CapabilityResult.fail("No battery found in /sys/class/power_supply", self.name,
            corrective_action="pkg install termux-api for full battery data")


# ── Termux:API generic ────────────────────────────────────────────────────────

class TermuxAPIAdapter(CapabilityAdapter):
    name = "termux.api"
    priority = 75

    def is_available(self) -> bool:
        return is_available("termux-info")

    def get_android_info(self) -> CapabilityResult:
        result = run(["termux-info"], timeout=5)
        if result.success:
            return CapabilityResult.ok({"raw": result.stdout}, self.name)
        return CapabilityResult.fail(result.stderr, self.name)


# ── All Termux adapters (for registry auto-registration) ──────────────────────

TERMUX_ADAPTERS: list[type[CapabilityAdapter]] = [
    TermuxPythonAdapter,
    TermuxGitAdapter,
    TermuxSSHAdapter,
    TermuxSQLiteAdapter,
    TermuxFilesystemAdapter,
    TermuxPackageAdapter,
    TermuxHTTPAdapter,
    TermuxShellAdapter,
    TermuxServiceAdapter,
    TermuxBatteryAdapter,
    TermuxAPIAdapter,
]

# Backward-compatible alias
TermuxAdapter = TermuxPythonAdapter
