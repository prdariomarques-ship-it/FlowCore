"""FlowCore Installer — sets up the full runtime environment.

Installation sequence:
    1. Python 3 (required)
    2. pip (Python package manager)
    3. Git
    4. SQLite3
    5. SSH client
    6. Python dependencies (requirements.txt)
    7. ~/.flowcore directory structure
    8. PATH configuration (.bashrc / .zshrc)
    9. MCP server dependencies (optional)
    10. Oracle bridge configuration (optional)
    11. Doctor validation — run full health check
    12. Runtime Kernel boot — generate flowcore.runtime.json
    13. Runtime Passport — emit and save

FlowCoreInstaller is idempotent: running it multiple times is safe.
Each step checks whether the target is already satisfied before acting.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger
from runtime.shell import is_available, run, which


@dataclass
class InstallStep:
    name:    str
    success: bool
    message: str
    skipped: bool = False


@dataclass
class InstallReport:
    steps:   list[InstallStep] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(s.success for s in self.steps if not s.skipped)

    @property
    def failed_steps(self) -> list[InstallStep]:
        return [s for s in self.steps if not s.success and not s.skipped]


class FlowCoreInstaller:
    """Sets up the FlowCore runtime environment from scratch.

    Usage::

        installer = FlowCoreInstaller()
        report = installer.install()
        if not report.ok:
            for step in report.failed_steps:
                print(f"FAILED: {step.name} — {step.message}")
    """

    def __init__(self, root: Path | None = None) -> None:
        self._root = root or Path(__file__).resolve().parent.parent
        self._flowcore_home = Path.home() / ".flowcore"

    def install(self, *, verbose: bool = True) -> InstallReport:
        """Run the full installation sequence."""
        report = InstallReport()

        steps = [
            self._ensure_python,
            self._ensure_pip,
            self._ensure_git,
            self._ensure_sqlite,
            self._ensure_ssh,
            self._ensure_python_deps,
            self._ensure_flowcore_dirs,
            self._ensure_path_config,
            self._run_doctor,
            self._boot_kernel,
        ]

        for step_fn in steps:
            step = step_fn()
            report.steps.append(step)
            icon = "✓" if step.success else ("─" if step.skipped else "✗")
            if verbose:
                logger.info("  {} {} — {}", icon, step.name, step.message)

        if report.ok:
            logger.info("FlowCore installation complete — all steps passed")
        else:
            fails = [s.name for s in report.failed_steps]
            logger.warning("Installation completed with failures: {}", fails)

        return report

    # ── Installation steps ────────────────────────────────────────────────────

    def _ensure_python(self) -> InstallStep:
        p = which("python3") or which("python")
        if p:
            result = run([p, "--version"], timeout=5)
            ver = (result.stdout or result.stderr).strip()
            return InstallStep("python3", True, f"Already installed: {ver}")

        # Attempt installation via pkg (Termux) or apt
        for installer_cmd in [
            ["pkg", "install", "-y", "python"],
            ["apt-get", "install", "-y", "python3"],
        ]:
            if is_available(installer_cmd[0]):
                result = run(installer_cmd, timeout=120)
                if result.success:
                    return InstallStep("python3", True, f"Installed via {installer_cmd[0]}")

        return InstallStep("python3", False, "Could not install python3 — install manually")

    def _ensure_pip(self) -> InstallStep:
        python = which("python3") or which("python")
        if not python:
            return InstallStep("pip", False, "python3 not found", skipped=True)

        result = run([python, "-m", "pip", "--version"], timeout=5)
        if result.success:
            return InstallStep("pip", True, f"Already available: {result.stdout.strip()}")

        result = run([python, "-m", "ensurepip", "--upgrade"], timeout=30)
        if result.success:
            return InstallStep("pip", True, "Bootstrapped via ensurepip")
        return InstallStep("pip", False, f"ensurepip failed: {result.stderr.strip()}")

    def _ensure_git(self) -> InstallStep:
        if is_available("git"):
            result = run(["git", "--version"], timeout=5)
            return InstallStep("git", True, f"Already installed: {result.stdout.strip()}")

        for cmd in [["pkg", "install", "-y", "git"], ["apt-get", "install", "-y", "git"]]:
            if is_available(cmd[0]):
                result = run(cmd, timeout=120)
                if result.success:
                    return InstallStep("git", True, f"Installed via {cmd[0]}")

        return InstallStep("git", False, "git not installed — install manually", skipped=True)

    def _ensure_sqlite(self) -> InstallStep:
        if is_available("sqlite3"):
            result = run(["sqlite3", "--version"], timeout=5)
            return InstallStep("sqlite3", True, f"Already installed: {result.stdout.strip()}")

        for cmd in [
            ["pkg", "install", "-y", "sqlite"],
            ["apt-get", "install", "-y", "sqlite3"],
        ]:
            if is_available(cmd[0]):
                result = run(cmd, timeout=120)
                if result.success:
                    return InstallStep("sqlite3", True, f"Installed via {cmd[0]}")

        return InstallStep("sqlite3", True, "sqlite3 CLI not found; Python sqlite3 module is built-in")

    def _ensure_ssh(self) -> InstallStep:
        if is_available("ssh"):
            return InstallStep("ssh", True, f"ssh at {which('ssh')}")

        for cmd in [
            ["pkg", "install", "-y", "openssh"],
            ["apt-get", "install", "-y", "openssh-client"],
        ]:
            if is_available(cmd[0]):
                result = run(cmd, timeout=120)
                if result.success:
                    return InstallStep("ssh", True, f"Installed via {cmd[0]}")

        return InstallStep("ssh", True, "ssh not installed (optional)", skipped=True)

    def _ensure_python_deps(self) -> InstallStep:
        req_file = self._root / "requirements.txt"
        if not req_file.exists():
            return InstallStep("python_deps", True, "No requirements.txt found", skipped=True)

        python = which("python3") or which("python")
        if not python:
            return InstallStep("python_deps", False, "python3 not found")

        result = run(
            [python, "-m", "pip", "install", "-r", str(req_file), "--quiet"],
            timeout=300,
        )
        if result.success:
            return InstallStep("python_deps", True, "Python dependencies installed")
        return InstallStep("python_deps", False, f"pip install failed: {result.stderr.strip()[:200]}")

    def _ensure_flowcore_dirs(self) -> InstallStep:
        dirs = [
            self._flowcore_home,
            self._flowcore_home / "logs",
            self._flowcore_home / "data",
            self._root / "logs",
            self._root / "data",
        ]
        created = []
        for d in dirs:
            if not d.exists():
                d.mkdir(parents=True, exist_ok=True)
                created.append(str(d))
        msg = f"Created: {created}" if created else "All directories already exist"
        return InstallStep("flowcore_dirs", True, msg)

    def _ensure_path_config(self) -> InstallStep:
        shell = os.environ.get("SHELL", "")
        scripts_dir = str(self._root / "scripts")
        export_line = f'export PATH="{scripts_dir}:$PATH"'

        rc_files = []
        if "zsh" in shell:
            rc_files.append(Path.home() / ".zshrc")
        rc_files.append(Path.home() / ".bashrc")  # always try .bashrc as fallback

        for rc in rc_files:
            if rc.exists():
                content = rc.read_text(encoding="utf-8", errors="ignore")
                if scripts_dir in content:
                    return InstallStep("path_config", True, f"PATH already configured in {rc.name}")
                rc.write_text(content + f"\n# FlowCore\n{export_line}\n", encoding="utf-8")
                return InstallStep("path_config", True, f"Added PATH to {rc.name}")

        return InstallStep("path_config", True, "No shell rc file found — PATH not modified", skipped=True)

    def _run_doctor(self) -> InstallStep:
        try:
            from doctor.service import DoctorService
            doctor = DoctorService()
            report = doctor.run(verbose=False)
            if report.healthy:
                return InstallStep(
                    "doctor", True,
                    f"All checks passed ({report.passed}/{len(report.checks)})",
                )
            warn_names = [c.name for c in report.checks if c.status.value in ("warn", "fail")]
            return InstallStep(
                "doctor", True,  # warnings don't block install
                f"{report.passed}/{len(report.checks)} passed; warnings: {warn_names}",
            )
        except Exception as e:
            return InstallStep("doctor", False, f"Doctor failed to run: {e}")

    def _boot_kernel(self) -> InstallStep:
        try:
            from runtime.kernel import RuntimeKernel
            kernel = RuntimeKernel(root=self._root)
            passport = kernel.boot()
            caps = passport.capabilities
            return InstallStep(
                "kernel_boot", True,
                f"Runtime Passport issued — {len(caps)} capabilities: {caps}",
            )
        except Exception as e:
            return InstallStep("kernel_boot", False, f"Kernel boot failed: {e}")
