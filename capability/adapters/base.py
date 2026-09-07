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
    """Standard return type for all capability operations.

    Every failure carries a human-readable reason, diagnosis, and
    corrective action — never a raw traceback exposed upward.
    """

    success: bool
    data: Any = None
    error: str | None = None
    bridge: str = ""
    # Diagnostic fields (populated on failure)
    reason: str = ""  # WHY it failed (one sentence)
    diagnosis: str = ""  # additional technical context
    corrective_action: str = ""  # what the user / system should do
    provider_used: str = ""  # adapter that handled this call
    fallback_provider: str = ""  # next adapter in the chain (if known)

    @classmethod
    def ok(cls, data: Any, bridge: str = "") -> "CapabilityResult":
        return cls(success=True, data=data, bridge=bridge, provider_used=bridge)

    @classmethod
    def fail(
        cls,
        error: str,
        bridge: str = "",
        *,
        reason: str = "",
        diagnosis: str = "",
        corrective_action: str = "",
        fallback_provider: str = "",
    ) -> "CapabilityResult":
        return cls(
            success=False,
            error=error,
            bridge=bridge,
            reason=reason or error,
            diagnosis=diagnosis,
            corrective_action=corrective_action,
            provider_used=bridge,
            fallback_provider=fallback_provider,
        )

    def to_dict(self) -> dict[str, Any]:
        if self.success:
            return {"success": True, "data": self.data, "bridge": self.bridge}
        return {
            "success": False,
            "error": self.error,
            "reason": self.reason,
            "diagnosis": self.diagnosis,
            "corrective_action": self.corrective_action,
            "provider_used": self.provider_used,
            "fallback_provider": self.fallback_provider,
        }


class CapabilityAdapter(ABC):
    """Abstract base for all platform adapters."""

    name: str = "base"
    priority: int = 0  # higher = preferred

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this adapter can operate on the current host."""
        ...

    # ── Android APIs ──────────────────────────────────────────────────────────

    def get_battery(self) -> CapabilityResult:
        return CapabilityResult.fail("getBattery not supported", self.name, corrective_action="pkg install termux-api")

    def get_clipboard(self) -> CapabilityResult:
        return CapabilityResult.fail(
            "getClipboard not supported", self.name, corrective_action="pkg install termux-api"
        )

    def set_clipboard(self, text: str) -> CapabilityResult:
        return CapabilityResult.fail(
            "setClipboard not supported", self.name, corrective_action="pkg install termux-api"
        )

    def send_notification(self, title: str, message: str) -> CapabilityResult:
        return CapabilityResult.fail(
            "sendNotification not supported", self.name, corrective_action="pkg install termux-api"
        )

    def get_network_info(self) -> CapabilityResult:
        return CapabilityResult.fail("getNetworkInfo not supported", self.name)

    def get_wifi_scan(self) -> CapabilityResult:
        return CapabilityResult.fail("getWifiScan not supported", self.name, corrective_action="pkg install termux-api")

    def get_bluetooth_state(self) -> CapabilityResult:
        return CapabilityResult.fail(
            "getBluetoothState not supported", self.name, corrective_action="pkg install termux-api"
        )

    def get_location(self, *, provider: str = "gps", timeout: int = 30) -> CapabilityResult:
        return CapabilityResult.fail("getLocation not supported", self.name, corrective_action="pkg install termux-api")

    def take_photo(self, output_path: str, *, camera_id: int = 0) -> CapabilityResult:
        return CapabilityResult.fail("takePhoto not supported", self.name, corrective_action="pkg install termux-api")

    def record_audio(self, output_path: str, *, duration: int = 10) -> CapabilityResult:
        return CapabilityResult.fail("recordAudio not supported", self.name, corrective_action="pkg install termux-api")

    def vibrate(self, duration_ms: int = 500) -> CapabilityResult:
        return CapabilityResult.fail("vibrate not supported", self.name, corrective_action="pkg install termux-api")

    def torch(self, *, on: bool = True) -> CapabilityResult:
        return CapabilityResult.fail("torch not supported", self.name, corrective_action="pkg install termux-api")

    def open_url(self, url: str) -> CapabilityResult:
        return CapabilityResult.fail("openUrl not supported", self.name, corrective_action="pkg install termux-api")

    def share_file(self, path: str, *, mime_type: str = "*/*") -> CapabilityResult:
        return CapabilityResult.fail("shareFile not supported", self.name, corrective_action="pkg install termux-api")

    def check_permission(self, permission: str) -> CapabilityResult:
        return CapabilityResult.fail(
            "checkPermission not supported", self.name, corrective_action="pkg install termux-api"
        )

    def list_permissions(self) -> CapabilityResult:
        return CapabilityResult.fail(
            "listPermissions not supported", self.name, corrective_action="pkg install termux-api"
        )

    def acquire_wakelock(self) -> CapabilityResult:
        return CapabilityResult.fail(
            "acquireWakeLock not supported", self.name, corrective_action="pkg install termux-api"
        )

    def release_wakelock(self) -> CapabilityResult:
        return CapabilityResult.fail(
            "releaseWakeLock not supported", self.name, corrective_action="pkg install termux-api"
        )

    def get_android_info(self) -> CapabilityResult:
        return CapabilityResult.fail("getAndroidInfo not supported", self.name)

    # ── Termux / Linux ────────────────────────────────────────────────────────

    def run_python(self, script: str, args: list[str] | None = None) -> CapabilityResult:
        return CapabilityResult.fail("runPython not supported", self.name, corrective_action="pkg install python")

    def run_git(self, args: list[str]) -> CapabilityResult:
        return CapabilityResult.fail("runGit not supported", self.name, corrective_action="pkg install git")

    def run_ssh(self, host: str, command: str, *, key_path: str | None = None) -> CapabilityResult:
        return CapabilityResult.fail("runSSH not supported", self.name, corrective_action="pkg install openssh")

    def run_sqlite(self, db_path: str, query: str) -> CapabilityResult:
        return CapabilityResult.fail("runSQLite not supported", self.name, corrective_action="pkg install sqlite")

    def run_shell(self, args: list[str], *, timeout: int = 30) -> CapabilityResult:
        return CapabilityResult.fail("runShell not supported", self.name)

    def install_package(self, package: str) -> CapabilityResult:
        return CapabilityResult.fail("installPackage not supported", self.name)

    def read_file(self, path: str) -> CapabilityResult:
        return CapabilityResult.fail("readFile not supported", self.name)

    def write_file(self, path: str, content: str) -> CapabilityResult:
        return CapabilityResult.fail("writeFile not supported", self.name)

    def list_directory(self, path: str) -> CapabilityResult:
        return CapabilityResult.fail("listDirectory not supported", self.name)

    def http_get(self, url: str, *, timeout: int = 10) -> CapabilityResult:
        return CapabilityResult.fail("httpRequest not supported", self.name, corrective_action="pkg install curl")

    def start_service(self, name: str, script: str) -> CapabilityResult:
        return CapabilityResult.fail("startService not supported", self.name)

    def stop_service(self, name: str) -> CapabilityResult:
        return CapabilityResult.fail("stopService not supported", self.name)

    def list_services(self) -> CapabilityResult:
        return CapabilityResult.fail("listServices not supported", self.name)

    def schedule_job(self, script: str, schedule: str) -> CapabilityResult:
        return CapabilityResult.fail("scheduleJob not supported", self.name)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name} available={self.is_available()}>"
