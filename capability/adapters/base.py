"""FlowCore Capability Adapters — base interface.

A CapabilityAdapter is the ONLY component that knows real system commands.
Agents above call capability names; the adapter translates to OS calls.

The LLM never sees: termux-battery-status, ip addr, pkg, pip, ls
The LLM only sees: getBattery(), getNetworkInfo(), installPackage()
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class CapabilityResult:
    """Standard return type for all capability operations."""
    success: bool
    data: Any = None
    error: str | None = None
    bridge: str = ""

    @classmethod
    def ok(cls, data: Any, bridge: str = "") -> "CapabilityResult":
        return cls(success=True, data=data, bridge=bridge)

    @classmethod
    def fail(cls, error: str, bridge: str = "") -> "CapabilityResult":
        return cls(success=False, error=error, bridge=bridge)


class CapabilityAdapter(ABC):
    """Abstract base for all platform adapters."""

    name: str = "base"
    priority: int = 0  # higher = preferred

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this adapter can operate on the current host."""
        ...

    def get_battery(self) -> CapabilityResult:
        return CapabilityResult.fail("getBattery not supported", self.name)

    def get_network_info(self) -> CapabilityResult:
        return CapabilityResult.fail("getNetworkInfo not supported", self.name)

    def get_clipboard(self) -> CapabilityResult:
        return CapabilityResult.fail("getClipboard not supported", self.name)

    def set_clipboard(self, text: str) -> CapabilityResult:
        return CapabilityResult.fail("setClipboard not supported", self.name)

    def send_notification(self, title: str, message: str) -> CapabilityResult:
        return CapabilityResult.fail("sendNotification not supported", self.name)

    def run_python(self, script: str, args: list[str] | None = None) -> CapabilityResult:
        return CapabilityResult.fail("runPython not supported", self.name)

    def run_git(self, args: list[str]) -> CapabilityResult:
        return CapabilityResult.fail("runGit not supported", self.name)

    def run_ssh(self, host: str, command: str, *, key_path: str | None = None) -> CapabilityResult:
        return CapabilityResult.fail("runSSH not supported", self.name)

    def install_package(self, package: str) -> CapabilityResult:
        return CapabilityResult.fail("installPackage not supported", self.name)

    def read_file(self, path: str) -> CapabilityResult:
        return CapabilityResult.fail("readFile not supported", self.name)

    def write_file(self, path: str, content: str) -> CapabilityResult:
        return CapabilityResult.fail("writeFile not supported", self.name)

    def list_directory(self, path: str) -> CapabilityResult:
        return CapabilityResult.fail("listDirectory not supported", self.name)

    def http_get(self, url: str, *, timeout: int = 10) -> CapabilityResult:
        return CapabilityResult.fail("httpRequest not supported", self.name)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} available={self.is_available()}>"
