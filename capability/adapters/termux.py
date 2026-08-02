"""FlowCore Termux Adapter — wraps Linux/Termux runtime capabilities.

Responsibilities:
- Python execution (python3)
- Git operations
- SSH / SCP / rsync
- Package management (pkg)
- SQLite queries
- File system operations
- Cron / background processes

This adapter runs inside Termux (Linux on Android) or any standard Linux.
It uses only standard Linux tools — no Android-specific APIs.
"""
from __future__ import annotations

import os
import shlex
from pathlib import Path

from capability.adapters.base import CapabilityAdapter, CapabilityResult
from runtime.shell import is_available, run, which


class TermuxAdapter(CapabilityAdapter):
    """Adapter for Termux/Linux runtime capabilities."""

    name = "termux"
    priority = 80  # Second priority after AndroidAdapter

    def is_available(self) -> bool:
        """True if running in Termux or any Linux environment with python3."""
        return is_available("python3") or is_available("python")

    # ── Python ────────────────────────────────────────────────────────────────

    def run_python(self, script: str, args: list[str] | None = None) -> CapabilityResult:
        """Execute a Python script file. *script* must be a file path."""
        python = which("python3") or which("python")
        if not python:
            return CapabilityResult.fail("python3 not found", self.name)

        script_path = Path(script)
        if not script_path.exists():
            return CapabilityResult.fail(f"Script not found: {script}", self.name)

        cmd = [python, str(script_path)] + (args or [])
        result = run(cmd, timeout=60)
        if result.success:
            return CapabilityResult.ok({"output": result.stdout, "stderr": result.stderr}, self.name)
        return CapabilityResult.fail(result.stderr or result.stdout, self.name)

    # ── Git ───────────────────────────────────────────────────────────────────

    def run_git(self, args: list[str]) -> CapabilityResult:
        """Run a git subcommand. args is the list AFTER 'git'."""
        if not is_available("git"):
            return CapabilityResult.fail("git not found", self.name)
        result = run(["git"] + args, timeout=30)
        if result.success:
            return CapabilityResult.ok({"output": result.stdout}, self.name)
        return CapabilityResult.fail(result.stderr, self.name)

    # ── SSH ───────────────────────────────────────────────────────────────────

    def run_ssh(self, host: str, command: str, *, key_path: str | None = None) -> CapabilityResult:
        """Run a command on a remote host via SSH."""
        if not is_available("ssh"):
            return CapabilityResult.fail("ssh not found", self.name)
        # command is split safely — no shell=True
        cmd = ["ssh"]
        if key_path:
            cmd += ["-i", key_path]
        cmd += ["-o", "StrictHostKeyChecking=no", host]
        cmd += shlex.split(command)
        result = run(cmd, timeout=30)
        if result.success:
            return CapabilityResult.ok({"output": result.stdout}, self.name)
        return CapabilityResult.fail(result.stderr, self.name)

    # ── Package management ────────────────────────────────────────────────────

    def install_package(self, package: str) -> CapabilityResult:
        """Install a package using pkg (Termux) or pip (Python)."""
        # Only allow alphanumeric package names plus - _ .
        safe_chars = set("abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-_.")
        if not all(c in safe_chars for c in package):
            return CapabilityResult.fail(f"Invalid package name: {package}", self.name)

        # Try pkg first (Termux system packages)
        if is_available("pkg"):
            result = run(["pkg", "install", "-y", package], timeout=120)
            if result.success:
                return CapabilityResult.ok({"installed": package, "via": "pkg"}, self.name)

        # Fallback to pip
        python = which("python3") or which("python")
        if python:
            result = run([python, "-m", "pip", "install", "--quiet", package], timeout=120)
            if result.success:
                return CapabilityResult.ok({"installed": package, "via": "pip"}, self.name)

        return CapabilityResult.fail(f"Could not install {package}", self.name)

    # ── HTTP ──────────────────────────────────────────────────────────────────

    def http_get(self, url: str, *, timeout: int = 10) -> CapabilityResult:
        """Perform an HTTP GET using curl or Python urllib."""
        if is_available("curl"):
            result = run(["curl", "-sS", "--max-time", str(timeout), url], timeout=timeout + 2)
            if result.success:
                return CapabilityResult.ok({"body": result.stdout, "via": "curl"}, self.name)

        # Fallback: Python urllib
        try:
            import urllib.request
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                return CapabilityResult.ok({"body": body, "via": "urllib"}, self.name)
        except Exception as e:
            return CapabilityResult.fail(str(e), self.name)

    # ── File system ───────────────────────────────────────────────────────────

    def read_file(self, path: str) -> CapabilityResult:
        try:
            content = Path(path).read_text(encoding="utf-8")
            return CapabilityResult.ok({"content": content, "path": path}, self.name)
        except Exception as e:
            return CapabilityResult.fail(str(e), self.name)

    def write_file(self, path: str, content: str) -> CapabilityResult:
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return CapabilityResult.ok({"written": True, "path": path}, self.name)
        except Exception as e:
            return CapabilityResult.fail(str(e), self.name)

    def list_directory(self, path: str) -> CapabilityResult:
        try:
            entries = sorted(str(p) for p in Path(path).iterdir())
            return CapabilityResult.ok({"entries": entries}, self.name)
        except Exception as e:
            return CapabilityResult.fail(str(e), self.name)

    def get_battery(self) -> CapabilityResult:
        """Termux fallback: read battery via /sys filesystem."""
        try:
            base = Path("/sys/class/power_supply")
            for battery in ["BAT0", "BAT1", "battery"]:
                bp = base / battery
                if bp.exists():
                    capacity = (bp / "capacity").read_text().strip()
                    status = (bp / "status").read_text().strip() if (bp / "status").exists() else "unknown"
                    return CapabilityResult.ok(
                        {"level": int(capacity), "status": status.lower()}, self.name
                    )
            return CapabilityResult.fail("No battery info in /sys", self.name)
        except Exception as e:
            return CapabilityResult.fail(str(e), self.name)
