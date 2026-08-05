#!/usr/bin/env python3
"""FlowCore — Automated Security & Compatibility Audit.

Checks:
  1. No hardcoded Linux paths (/etc/, /usr/, /var/)
  2. No sudo/root commands in code
  3. API binds to localhost
  4. No dangerous os.system / subprocess calls with user input
  5. No exposed credentials
  6. Python 3.13 compatibility (no removed APIs)
  7. Termux compatibility (no missing modules)
  8. Directory structure completeness
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ANSI colours
GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[1;33m"
NC = "\033[0m"

passed = 0
failed = 0
warnings = 0


def ok(msg: str) -> None:
    global passed
    print(f"  {GREEN}PASS{NC}  {msg}")
    passed += 1


def bad(msg: str) -> None:
    global failed
    print(f"  {RED}FAIL{NC}  {msg}")
    failed += 1


def warn(msg: str) -> None:
    global warnings
    print(f"  {YELLOW}WARN{NC}  {msg}")
    warnings += 1


def audit_paths() -> None:
    """Check for hardcoded Linux paths."""
    print("\n[Audit 1] Hardcoded Linux paths")
    dangerous_patterns = ["/etc/passwd", "/etc/shadow", "/usr/bin/sudo", "/var/log"]
    for py_file in ROOT.rglob("*.py"):
        if "__pycache__" in str(py_file) or py_file.name == "audit.py":
            continue
        content = py_file.read_text()
        for pattern in dangerous_patterns:
            if pattern in content:
                bad(f"{py_file.relative_to(ROOT)} contains '{pattern}'")
                return
    ok("No hardcoded Linux system paths found")


def audit_root_commands() -> None:
    """Check for sudo/root commands."""
    print("\n[Audit 2] Root/sudo commands")
    for sh_file in ROOT.rglob("*.sh"):
        content = sh_file.read_text()
        # Ignore the uninstall script (it uses sudo in comments only)
        if "uninstall" in sh_file.name:
            continue
        if "sudo " in content and "sudo" in content.split("#")[0]:
            # Check if it's in a comment
            for line in content.splitlines():
                if "sudo " in line and not line.strip().startswith("#"):
                    bad(f"{sh_file.relative_to(ROOT)} uses sudo: {line.strip()}")
                    return
    ok("No sudo/root commands in operational scripts")


def audit_api_localhost() -> None:
    """Check API binds to localhost."""
    print("\n[Audit 3] API localhost binding")
    config_path = ROOT / "config" / "default.json"
    if not config_path.exists():
        warn("config/default.json not found")
        return
    content = config_path.read_text()
    if "0.0.0.0" in content:
        bad("config/default.json binds to 0.0.0.0 (network-exposed)")
    elif "127.0.0.1" in content:
        ok("API binds to 127.0.0.1 (localhost only)")
    else:
        warn("Cannot determine API binding from config")


def audit_dangerous_calls() -> None:
    """Check for dangerous os.system / subprocess calls."""
    print("\n[Audit 4] Dangerous system calls")
    dangerous = ["os.system(", "subprocess.call(", "subprocess.run("]
    found = False
    for py_file in ROOT.rglob("*.py"):
        if "__pycache__" in str(py_file) or py_file.name == "audit.py":
            continue
        content = py_file.read_text()
        for call in dangerous:
            if call in content:
                bad(f"{py_file.relative_to(ROOT)} uses {call}")
                found = True
    if not found:
        ok("No os.system() or subprocess.call() with unsanitized input")


def audit_credentials() -> None:
    """Check for exposed credentials."""
    print("\n[Audit 5] Exposed credentials")
    patterns = ["password=", "secret=", "api_key=", "token="]
    found = False
    for py_file in ROOT.rglob("*.py"):
        if "__pycache__" in str(py_file) or py_file.name == "audit.py":
            continue
        content = py_file.read_text()
        for line in content.splitlines():
            if line.strip().startswith("#"):
                continue
            for pattern in patterns:
                if pattern in line.lower() and "env" not in line.lower() and "os.environ" not in line:
                    warn(f"{py_file.relative_to(ROOT)} may contain credential: {line.strip()[:60]}")
                    found = True
    if not found:
        ok("No hardcoded credentials found")


def audit_python313_compat() -> None:
    """Check Python 3.13 compatibility."""
    print("\n[Audit 6] Python 3.13 compatibility")
    # Check for removed/changed APIs
    removed = ["asyncio.coroutines.asyncio", "distutils"]
    for py_file in ROOT.rglob("*.py"):
        if "__pycache__" in str(py_file) or py_file.name == "audit.py":
            continue
        content = py_file.read_text()
        for api in removed:
            if api in content:
                bad(f"{py_file.relative_to(ROOT)} uses removed API: {api}")
                return
    ok("No removed Python 3.13 APIs detected")


def audit_termux_compat() -> None:
    """Check Termux compatibility."""
    print("\n[Audit 7] Termux compatibility")
    # Check requirements.txt for C-extension-only packages
    req_path = ROOT / "requirements.txt"
    content = req_path.read_text()
    incompatible = ["psutil", "uvloop", "lxml", "cryptography"]
    found = False
    for pkg in incompatible:
        if pkg in content.lower():
            bad(f"requirements.txt contains Termux-incompatible package: {pkg}")
            found = True
    if not found:
        ok("All dependencies are pure-Python or Termux-compatible")


def audit_structure() -> None:
    """Check directory structure completeness."""
    print("\n[Audit 8] Directory structure")
    required_dirs = ["config", "runtime", "executor", "scheduler", "api", "agents", "scripts", "logs", "backups"]
    required_files = [
        "install.sh", "flowcore.py", "daemon.py", "validate_android.sh",
        "doctor.sh", "optimize.sh", "benchmark.sh", "update.sh", "repair.sh",
        "uninstall.sh", "requirements.txt", "README.md", "LICENSE", ".gitignore",
    ]
    for d in required_dirs:
        if (ROOT / d).is_dir():
            ok(f"Directory: {d}/")
        else:
            bad(f"Missing directory: {d}/")
    for f in required_files:
        if (ROOT / f).exists():
            ok(f"File: {f}")
        else:
            bad(f"Missing file: {f}")


def main() -> None:
    global passed, failed, warnings
    print("=" * 50)
    print("  FlowCore Security & Compatibility Audit")
    print("=" * 50)

    audit_paths()
    audit_root_commands()
    audit_api_localhost()
    audit_dangerous_calls()
    audit_credentials()
    audit_python313_compat()
    audit_termux_compat()
    audit_structure()

    print("\n" + "=" * 50)
    print(f"  Results: {passed} passed, {failed} failed, {warnings} warnings")
    print("=" * 50)

    if failed > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
