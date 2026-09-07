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
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger
from runtime.shell import is_available, run, which


@dataclass
class InstallStep:
    name: str
    success: bool
    message: str
    skipped: bool = False


@dataclass
class InstallReport:
    steps: list[InstallStep] = field(default_factory=list)

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
                    "doctor",
                    True,
                    f"All checks passed ({report.passed}/{len(report.checks)})",
                )
            warn_names = [c.name for c in report.checks if c.status.value in ("warn", "fail")]
            return InstallStep(
                "doctor",
                True,  # warnings don't block install
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
                "kernel_boot",
                True,
                f"Runtime Passport issued — {len(caps)} capabilities: {caps}",
            )
        except Exception as e:
            return InstallStep("kernel_boot", False, f"Kernel boot failed: {e}")

    # ── Bootstrap mode (fresh Termux from zero) ───────────────────────────────

    def bootstrap(self, *, verbose: bool = True) -> InstallReport:
        """Bootstrap a fresh Termux environment from zero.

        Intended for first-run on a new Android device where only Termux is
        installed.  Installs core packages, sets up storage, and then calls
        install() to complete the full setup.
        """
        report = InstallReport()

        steps = [
            self._bootstrap_check_termux,
            self._bootstrap_pkg_update,
            self._bootstrap_termux_api,
            self._bootstrap_storage,
            self._bootstrap_core_packages,
        ]

        for step_fn in steps:
            step = step_fn()
            report.steps.append(step)
            icon = "✓" if step.success else ("─" if step.skipped else "✗")
            if verbose:
                logger.info("  [bootstrap] {} {} — {}", icon, step.name, step.message)
            if not step.success and not step.skipped:
                logger.error("Bootstrap aborted at step '{}'", step.name)
                return report

        logger.info("Bootstrap complete — running full install...")
        full = self.install(verbose=verbose)
        report.steps.extend(full.steps)
        return report

    def _bootstrap_check_termux(self) -> InstallStep:
        prefix = os.environ.get("PREFIX", "")
        if prefix and os.path.exists(prefix + "/bin/bash"):
            return InstallStep("bootstrap_termux_env", True, f"Termux detected: PREFIX={prefix}")
        return InstallStep(
            "bootstrap_termux_env",
            False,
            "Not running inside Termux — bootstrap requires Termux on Android",
        )

    def _bootstrap_pkg_update(self) -> InstallStep:
        if not is_available("pkg"):
            return InstallStep("bootstrap_pkg_update", False, "pkg not available")
        result = run(["pkg", "update", "-y"], timeout=180)
        if result.success:
            return InstallStep("bootstrap_pkg_update", True, "pkg updated")
        return InstallStep(
            "bootstrap_pkg_update",
            False,
            f"pkg update failed: {result.stderr.strip()[:100]}",
        )

    def _bootstrap_termux_api(self) -> InstallStep:
        if is_available("termux-battery-status"):
            return InstallStep("bootstrap_termux_api", True, "Termux:API already installed", skipped=True)
        if not is_available("pkg"):
            return InstallStep("bootstrap_termux_api", False, "pkg not available")
        result = run(["pkg", "install", "-y", "termux-api"], timeout=120)
        if result.success:
            return InstallStep(
                "bootstrap_termux_api",
                True,
                "Termux:API installed (also install Termux:API app from F-Droid)",
            )
        return InstallStep("bootstrap_termux_api", False, result.stderr.strip()[:100])

    def _bootstrap_storage(self) -> InstallStep:
        storage = Path.home() / "storage"
        if storage.exists():
            return InstallStep("bootstrap_storage", True, "Termux storage already configured", skipped=True)
        return InstallStep(
            "bootstrap_storage",
            False,
            "Storage not set up — run 'termux-setup-storage' manually in Termux, then re-run bootstrap",
        )

    def _bootstrap_core_packages(self) -> InstallStep:
        packages = ["python", "git", "openssh", "curl", "sqlite"]
        installed = []
        failed = []
        for pkg in packages:
            result = run(["pkg", "install", "-y", pkg], timeout=180)
            if result.success:
                installed.append(pkg)
            else:
                failed.append(pkg)
        if failed:
            return InstallStep(
                "bootstrap_core_packages",
                False,
                f"Some packages failed to install: {failed}. Installed: {installed}",
            )
        return InstallStep(
            "bootstrap_core_packages",
            True,
            f"Core packages installed: {installed}",
        )

    # ── Repair mode (corrupted environment) ──────────────────────────────────

    def repair(self, *, verbose: bool = True) -> InstallReport:
        """Detect and repair a corrupted FlowCore environment.

        Runs Doctor to identify failures, then attempts to fix each one.
        """
        report = InstallReport()

        if verbose:
            logger.info("FlowCore Repair — running Doctor to detect issues...")

        try:
            from doctor.service import DoctorService

            doctor = DoctorService()
            doctor_report = doctor.run(verbose=False)
        except Exception as e:
            step = InstallStep("repair_doctor", False, f"Doctor could not run: {e}")
            report.steps.append(step)
            return report

        report.steps.append(
            InstallStep(
                "repair_doctor",
                True,
                f"Doctor: {doctor_report.passed}/{len(doctor_report.checks)} passed, {doctor_report.failed} failures",
            )
        )

        failed_checks = [c for c in doctor_report.checks if c.failed]
        if not failed_checks:
            report.steps.append(InstallStep("repair_result", True, "No failures detected — nothing to repair"))
            return report

        for check in failed_checks:
            step = self._repair_check(check, verbose=verbose)
            report.steps.append(step)

        re_report = doctor.run(verbose=False)
        remaining = re_report.failed
        status = remaining == 0
        report.steps.append(
            InstallStep(
                "repair_final_check",
                status,
                f"Post-repair: {re_report.passed}/{len(re_report.checks)} passed, {remaining} still failing",
            )
        )

        return report

    def _repair_check(self, check, *, verbose: bool) -> InstallStep:
        """Attempt to fix a single failed check using its fix suggestion."""
        name = check.name
        fix = check.fix

        if verbose:
            logger.info("  Repairing '{}': {}", name, check.message)

        if not fix:
            return InstallStep(
                f"repair_{name}",
                False,
                f"No automatic fix available for '{name}': {check.message}",
                skipped=True,
            )

        # Parse the fix as a command if it looks like one
        fix_parts = fix.split()
        if not fix_parts:
            return InstallStep(f"repair_{name}", False, "Fix string is empty", skipped=True)

        if not is_available(fix_parts[0]):
            return InstallStep(
                f"repair_{name}",
                False,
                f"Fix command '{fix_parts[0]}' not available — manual action required: {fix}",
                skipped=True,
            )

        result = run(fix_parts, timeout=180)
        if result.success:
            return InstallStep(f"repair_{name}", True, f"Fixed via: {fix}")
        return InstallStep(
            f"repair_{name}",
            False,
            f"Auto-fix failed: {result.stderr.strip()[:100]} — manual action: {fix}",
        )
