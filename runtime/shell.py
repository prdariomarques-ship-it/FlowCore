"""FlowCore Runtime Shell — controlled subprocess gateway.

This is the ONLY approved location for running shell commands in FlowCore.
Capability adapters import this; the LLM (agent layer) never calls it directly.

Design rule: arguments are always a list, never a shell string.
This prevents shell injection regardless of input.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence


@dataclass
class ShellResult:
    """Result of a controlled shell execution."""
    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    success: bool = field(init=False)

    def __post_init__(self) -> None:
        self.success = self.returncode == 0


def which(name: str) -> str | None:
    """Return full path of *name* if found on PATH, else None."""
    return shutil.which(name)


def is_available(name: str) -> bool:
    """Return True if *name* is a runnable binary on the current PATH."""
    return which(name) is not None


def run(
    cmd: Sequence[str],
    *,
    timeout: int = 10,
    cwd: Path | None = None,
    env: dict | None = None,
    capture: bool = True,
) -> ShellResult:
    """Run *cmd* (as a list) and return a ShellResult.

    Never raises on non-zero exit; check ShellResult.success instead.
    Timeout raises TimeoutError; everything else is captured in stderr.
    """
    cmd_list = list(cmd)
    try:
        proc = subprocess.Popen(
            cmd_list,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None,
            cwd=str(cwd) if cwd else None,
            env=env,
        )
        try:
            stdout_b, stderr_b = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            raise TimeoutError(f"Command timed out after {timeout}s: {cmd_list}")

        return ShellResult(
            command=cmd_list,
            returncode=proc.returncode,
            stdout=(stdout_b or b"").decode("utf-8", errors="replace").strip(),
            stderr=(stderr_b or b"").decode("utf-8", errors="replace").strip(),
        )
    except FileNotFoundError:
        return ShellResult(
            command=cmd_list,
            returncode=127,
            stdout="",
            stderr=f"Command not found: {cmd_list[0]}",
        )
    except Exception as exc:
        return ShellResult(
            command=cmd_list,
            returncode=1,
            stdout="",
            stderr=str(exc),
        )


def version_of(name: str) -> str | None:
    """Return the version string of a binary, or None if not available."""
    if not is_available(name):
        return None
    result = run([name, "--version"], timeout=5)
    if result.success or result.stdout:
        text = result.stdout or result.stderr
        return text.split("\n")[0].strip()
    return None
