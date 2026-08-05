"""FlowCore Linux Adapter — wraps standard Linux/desktop/server capabilities.

Responsibilities:
- Python execution
- Git operations
- SSH / SCP / rsync
- HTTP via curl or urllib
- File system operations
- Battery via /sys (laptops/desktops)
- Network info via ip/ifconfig

This adapter is the lowest-priority fallback: it works on any POSIX system
that has python3 — including macOS, WSL, CI runners, and cloud VMs.
"""

from __future__ import annotations

import shlex
from pathlib import Path

from capability.adapters.base import CapabilityAdapter, CapabilityResult
from runtime.shell import is_available, run, which


class LinuxAdapter(CapabilityAdapter):
    """Adapter for plain Linux/macOS/WSL environments (no Termux required)."""

    name = "linux"
    priority = 50  # Lowest priority — final fallback

    def is_available(self) -> bool:
        """True on any POSIX system with python3 or python."""
        import sys

        return sys.platform != "win32"

    # ── Python ────────────────────────────────────────────────────────────────

    def run_python(self, script: str, args: list[str] | None = None) -> CapabilityResult:
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
        if not is_available("git"):
            return CapabilityResult.fail("git not found", self.name)
        result = run(["git"] + args, timeout=30)
        if result.success:
            return CapabilityResult.ok({"output": result.stdout}, self.name)
        return CapabilityResult.fail(result.stderr, self.name)

    # ── SSH ───────────────────────────────────────────────────────────────────

    def run_ssh(self, host: str, command: str, *, key_path: str | None = None) -> CapabilityResult:
        if not is_available("ssh"):
            return CapabilityResult.fail("ssh not found", self.name)
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
        safe_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
        if not all(c in safe_chars for c in package):
            return CapabilityResult.fail(f"Invalid package name: {package}", self.name)

        python = which("python3") or which("python")
        if python:
            result = run([python, "-m", "pip", "install", "--quiet", package], timeout=120)
            if result.success:
                return CapabilityResult.ok({"installed": package, "via": "pip"}, self.name)

        # apt fallback (Debian/Ubuntu)
        if is_available("apt-get"):
            result = run(["apt-get", "install", "-y", package], timeout=120)
            if result.success:
                return CapabilityResult.ok({"installed": package, "via": "apt-get"}, self.name)

        # brew fallback (macOS)
        if is_available("brew"):
            result = run(["brew", "install", package], timeout=120)
            if result.success:
                return CapabilityResult.ok({"installed": package, "via": "brew"}, self.name)

        return CapabilityResult.fail(f"Could not install {package}", self.name)

    # ── HTTP ──────────────────────────────────────────────────────────────────

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

    # ── Battery ───────────────────────────────────────────────────────────────

    def get_battery(self) -> CapabilityResult:
        """Read battery via /sys filesystem (works on laptops with kernel support)."""
        try:
            base = Path("/sys/class/power_supply")
            for name in ["BAT0", "BAT1", "battery"]:
                bp = base / name
                if bp.exists():
                    capacity = (bp / "capacity").read_text().strip()
                    status_file = bp / "status"
                    status = status_file.read_text().strip().lower() if status_file.exists() else "unknown"
                    return CapabilityResult.ok({"level": int(capacity), "status": status}, self.name)
            return CapabilityResult.fail("No battery found in /sys/class/power_supply", self.name)
        except Exception as e:
            return CapabilityResult.fail(str(e), self.name)

    # ── Network ───────────────────────────────────────────────────────────────

    def get_network_info(self) -> CapabilityResult:
        """Return basic IP info via `ip addr` or `ifconfig`."""
        if is_available("ip"):
            result = run(["ip", "-4", "addr", "show"], timeout=5)
            if result.success:
                return CapabilityResult.ok({"output": result.stdout, "via": "ip"}, self.name)

        if is_available("ifconfig"):
            result = run(["ifconfig"], timeout=5)
            if result.success:
                return CapabilityResult.ok({"output": result.stdout, "via": "ifconfig"}, self.name)

        return CapabilityResult.fail("Neither ip nor ifconfig found", self.name)

    # ── Disk usage ────────────────────────────────────────────────────────────

    def get_disk_usage(self, path: str = "/") -> CapabilityResult:
        if not is_available("df"):
            return CapabilityResult.fail("df not found", self.name)
        result = run(["df", "-h", path], timeout=5)
        if not result.success or not result.stdout:
            return CapabilityResult.fail(result.stderr or "df failed", self.name, reason=f"Cannot read {path}")
        lines = result.stdout.strip().splitlines()
        if len(lines) < 2:
            return CapabilityResult.fail("Unexpected df output", self.name)
        parts = lines[1].split()
        if len(parts) < 4:
            return CapabilityResult.fail("Unexpected df output", self.name)
        return CapabilityResult.ok({"total": parts[1], "used": parts[2], "avail": parts[3]}, self.name)
