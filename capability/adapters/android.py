"""FlowCore Android Runtime Adapters.

Each class handles ONE capability domain, wrapping a specific termux-* command.
Priority 100 — highest preference on Android/Termux.

Availability: every adapter checks (a) running in Termux (PREFIX set) and
(b) the specific termux-* binary is on PATH.  If Termux:API is not installed,
is_available() returns False and the Registry falls back automatically.

The agent layer never sees any termux-* command name.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from capability.adapters.base import CapabilityAdapter, CapabilityResult
from runtime.shell import is_available, run


def _in_termux() -> bool:
    prefix = os.environ.get("PREFIX", "")
    return bool(prefix) and os.path.exists(prefix + "/bin/bash")


# ── Battery ───────────────────────────────────────────────────────────────────


class AndroidBatteryAdapter(CapabilityAdapter):
    name = "android.battery"
    priority = 100

    def is_available(self) -> bool:
        return _in_termux() and is_available("termux-battery-status")

    def get_battery(self) -> CapabilityResult:
        result = run(["termux-battery-status"], timeout=5)
        if not result.success:
            return CapabilityResult.fail(
                result.stderr or "termux-battery-status failed",
                self.name,
                reason="termux-battery-status returned non-zero exit code",
                diagnosis=result.stderr,
                corrective_action="pkg install termux-api && allow battery permission in Termux:API app",
                fallback_provider="termux.battery",
            )
        try:
            data = json.loads(result.stdout)
            return CapabilityResult.ok(
                {
                    "level": data.get("percentage", -1),
                    "status": data.get("status", "unknown").lower(),
                    "health": data.get("health", "unknown").lower(),
                    "temperature": data.get("temperature", -1),
                    "plugged": data.get("plugged", "unknown"),
                },
                self.name,
            )
        except json.JSONDecodeError as e:
            return CapabilityResult.fail(
                f"JSON parse error: {e}",
                self.name,
                reason="termux-battery-status returned invalid JSON",
                diagnosis=result.stdout[:200],
                corrective_action="Reinstall Termux:API: pkg reinstall termux-api",
            )


# ── Clipboard ─────────────────────────────────────────────────────────────────


class AndroidClipboardAdapter(CapabilityAdapter):
    name = "android.clipboard"
    priority = 100

    def is_available(self) -> bool:
        return _in_termux() and is_available("termux-clipboard-get")

    def get_clipboard(self) -> CapabilityResult:
        result = run(["termux-clipboard-get"], timeout=5)
        if result.success:
            return CapabilityResult.ok({"text": result.stdout}, self.name)
        return CapabilityResult.fail(
            result.stderr,
            self.name,
            reason="Could not read clipboard",
            corrective_action="Grant clipboard permission in Termux:API settings",
        )

    def set_clipboard(self, text: str) -> CapabilityResult:
        result = run(["termux-clipboard-set", text], timeout=5)
        if result.success:
            return CapabilityResult.ok({"set": True}, self.name)
        return CapabilityResult.fail(
            result.stderr,
            self.name,
            reason="Could not write to clipboard",
            corrective_action="Grant clipboard permission in Termux:API settings",
        )


# ── Notifications ─────────────────────────────────────────────────────────────


class AndroidNotificationAdapter(CapabilityAdapter):
    name = "android.notification"
    priority = 100

    def is_available(self) -> bool:
        return _in_termux() and is_available("termux-notification")

    def send_notification(self, title: str, message: str) -> CapabilityResult:
        result = run(["termux-notification", "--title", title, "--content", message], timeout=5)
        if result.success:
            return CapabilityResult.ok({"sent": True}, self.name)
        return CapabilityResult.fail(
            result.stderr,
            self.name,
            reason="Could not send notification",
            corrective_action="Enable: Settings → Apps → Termux → Notifications → Allow",
        )


# ── WiFi ──────────────────────────────────────────────────────────────────────


class AndroidWifiAdapter(CapabilityAdapter):
    name = "android.wifi"
    priority = 100

    def is_available(self) -> bool:
        return _in_termux() and is_available("termux-wifi-connectioninfo")

    def get_network_info(self) -> CapabilityResult:
        result = run(["termux-wifi-connectioninfo"], timeout=5)
        if not result.success:
            return CapabilityResult.fail(
                result.stderr,
                self.name,
                reason="termux-wifi-connectioninfo failed",
                corrective_action="pkg install termux-api && grant ACCESS_WIFI_STATE permission",
            )
        try:
            data = json.loads(result.stdout)
            return CapabilityResult.ok(
                {
                    "ssid": data.get("ssid", ""),
                    "bssid": data.get("bssid", ""),
                    "rssi": data.get("rssi", 0),
                    "link_speed": data.get("link_speed_mbps", 0),
                    "ip": data.get("ip", ""),
                },
                self.name,
            )
        except json.JSONDecodeError as e:
            return CapabilityResult.fail(f"JSON parse error: {e}", self.name)

    def get_wifi_scan(self) -> CapabilityResult:
        if not is_available("termux-wifi-scaninfo"):
            return CapabilityResult.fail(
                "termux-wifi-scaninfo not found", self.name, corrective_action="pkg install termux-api"
            )
        result = run(["termux-wifi-scaninfo"], timeout=10)
        if not result.success:
            return CapabilityResult.fail(result.stderr, self.name)
        try:
            networks = json.loads(result.stdout)
            return CapabilityResult.ok({"networks": networks, "count": len(networks)}, self.name)
        except json.JSONDecodeError as e:
            return CapabilityResult.fail(f"JSON parse error: {e}", self.name)


# ── Bluetooth ─────────────────────────────────────────────────────────────────


class AndroidBluetoothAdapter(CapabilityAdapter):
    name = "android.bluetooth"
    priority = 100

    def is_available(self) -> bool:
        return _in_termux() and is_available("termux-bluetooth-get-adapters")

    def get_bluetooth_state(self) -> CapabilityResult:
        result = run(["termux-bluetooth-get-adapters"], timeout=5)
        if not result.success:
            return CapabilityResult.fail(
                result.stderr,
                self.name,
                reason="Cannot read Bluetooth adapters",
                corrective_action="pkg install termux-api && grant Bluetooth permission",
            )
        try:
            data = json.loads(result.stdout)
            return CapabilityResult.ok({"adapters": data}, self.name)
        except json.JSONDecodeError as e:
            return CapabilityResult.fail(f"JSON parse error: {e}", self.name)


# ── Location ──────────────────────────────────────────────────────────────────


class AndroidLocationAdapter(CapabilityAdapter):
    name = "android.location"
    priority = 100

    def is_available(self) -> bool:
        return _in_termux() and is_available("termux-location")

    def get_location(self, *, provider: str = "gps", timeout: int = 30) -> CapabilityResult:
        result = run(["termux-location", "-p", provider, "-r", "once"], timeout=timeout + 5)
        if not result.success:
            return CapabilityResult.fail(
                result.stderr,
                self.name,
                reason="Could not get location",
                diagnosis="GPS may be disabled or permission denied",
                corrective_action="Enable location in Settings and grant ACCESS_FINE_LOCATION",
            )
        try:
            data = json.loads(result.stdout)
            return CapabilityResult.ok(
                {
                    "latitude": data.get("latitude"),
                    "longitude": data.get("longitude"),
                    "altitude": data.get("altitude"),
                    "accuracy": data.get("accuracy"),
                    "provider": provider,
                },
                self.name,
            )
        except json.JSONDecodeError as e:
            return CapabilityResult.fail(f"JSON parse error: {e}", self.name)


# ── Camera ────────────────────────────────────────────────────────────────────


class AndroidCameraAdapter(CapabilityAdapter):
    name = "android.camera"
    priority = 100

    def is_available(self) -> bool:
        return _in_termux() and is_available("termux-camera-photo")

    def take_photo(self, output_path: str, *, camera_id: int = 0) -> CapabilityResult:
        result = run(["termux-camera-photo", "-c", str(camera_id), output_path], timeout=15)
        if result.success and Path(output_path).exists():
            size = Path(output_path).stat().st_size
            return CapabilityResult.ok({"path": output_path, "size_bytes": size}, self.name)
        return CapabilityResult.fail(
            result.stderr or "Photo not created",
            self.name,
            reason="Camera capture failed",
            corrective_action="Grant CAMERA permission: Settings → Apps → Termux → Permissions → Camera",
        )


# ── Microphone ────────────────────────────────────────────────────────────────


class AndroidMicrophoneAdapter(CapabilityAdapter):
    name = "android.microphone"
    priority = 100

    def is_available(self) -> bool:
        return _in_termux() and is_available("termux-microphone-record")

    def record_audio(self, output_path: str, *, duration: int = 10) -> CapabilityResult:
        result = run(["termux-microphone-record", "-d", str(duration), "-f", output_path], timeout=duration + 5)
        if result.success:
            return CapabilityResult.ok({"path": output_path, "duration": duration}, self.name)
        return CapabilityResult.fail(
            result.stderr,
            self.name,
            reason="Audio recording failed",
            corrective_action="Grant RECORD_AUDIO: Settings → Apps → Termux → Permissions → Microphone",
        )


# ── WakeLock ──────────────────────────────────────────────────────────────────


class AndroidWakeLockAdapter(CapabilityAdapter):
    name = "android.wakelock"
    priority = 100

    def is_available(self) -> bool:
        return _in_termux() and is_available("termux-wake-lock")

    def acquire_wakelock(self) -> CapabilityResult:
        result = run(["termux-wake-lock"], timeout=5)
        if result.success:
            return CapabilityResult.ok({"acquired": True}, self.name)
        return CapabilityResult.fail(
            result.stderr,
            self.name,
            reason="Could not acquire WakeLock",
            diagnosis="Battery optimization may be blocking WakeLock",
            corrective_action="Settings → Battery → Termux → Unrestricted",
        )

    def release_wakelock(self) -> CapabilityResult:
        result = run(["termux-wake-unlock"], timeout=5)
        if result.success:
            return CapabilityResult.ok({"released": True}, self.name)
        return CapabilityResult.fail(result.stderr, self.name)


# ── Intent ────────────────────────────────────────────────────────────────────


class AndroidIntentAdapter(CapabilityAdapter):
    name = "android.intent"
    priority = 100

    def is_available(self) -> bool:
        return _in_termux() and is_available("termux-open-url")

    def open_url(self, url: str) -> CapabilityResult:
        result = run(["termux-open-url", url], timeout=5)
        if result.success:
            return CapabilityResult.ok({"opened": url}, self.name)
        return CapabilityResult.fail(
            result.stderr, self.name, reason=f"Could not open URL: {url}", corrective_action="pkg install termux-api"
        )

    def share_file(self, path: str, *, mime_type: str = "*/*") -> CapabilityResult:
        if not is_available("termux-share"):
            return CapabilityResult.fail(
                "termux-share not found", self.name, corrective_action="pkg install termux-api"
            )
        result = run(["termux-share", "-m", mime_type, path], timeout=10)
        if result.success:
            return CapabilityResult.ok({"shared": path}, self.name)
        return CapabilityResult.fail(result.stderr, self.name)

    def vibrate(self, duration_ms: int = 500) -> CapabilityResult:
        if not is_available("termux-vibrate"):
            return CapabilityResult.fail(
                "termux-vibrate not found", self.name, corrective_action="pkg install termux-api"
            )
        result = run(["termux-vibrate", "-d", str(duration_ms)], timeout=5)
        if result.success:
            return CapabilityResult.ok({"vibrated": True, "duration_ms": duration_ms}, self.name)
        return CapabilityResult.fail(result.stderr, self.name)

    def torch(self, *, on: bool = True) -> CapabilityResult:
        if not is_available("termux-torch"):
            return CapabilityResult.fail(
                "termux-torch not found", self.name, corrective_action="pkg install termux-api"
            )
        result = run(["termux-torch", "on" if on else "off"], timeout=5)
        if result.success:
            return CapabilityResult.ok({"torch": "on" if on else "off"}, self.name)
        return CapabilityResult.fail(result.stderr, self.name)


# ── Permissions ───────────────────────────────────────────────────────────────


class AndroidPermissionAdapter(CapabilityAdapter):
    name = "android.permission"
    priority = 100

    _PERMISSION_PROBE: dict[str, str] = {
        "CAMERA": "termux-camera-photo",
        "RECORD_AUDIO": "termux-microphone-record",
        "ACCESS_FINE_LOCATION": "termux-location",
        "READ_EXTERNAL_STORAGE": "termux-storage-get",
        "POST_NOTIFICATIONS": "termux-notification",
        "BLUETOOTH": "termux-bluetooth-get-adapters",
    }

    def is_available(self) -> bool:
        return _in_termux() and is_available("termux-info")

    def check_permission(self, permission: str) -> CapabilityResult:
        probe = self._PERMISSION_PROBE.get(permission.upper())
        if probe:
            granted = is_available(probe)
            return CapabilityResult.ok({"permission": permission, "granted": granted, "probe": probe}, self.name)
        return CapabilityResult.ok(
            {"permission": permission, "granted": None, "note": "Cannot probe this permission from shell"}, self.name
        )

    def list_permissions(self) -> CapabilityResult:
        permissions = list(self._PERMISSION_PROBE.keys()) + [
            "REQUEST_IGNORE_BATTERY_OPTIMIZATIONS",
            "RECEIVE_BOOT_COMPLETED",
        ]
        return CapabilityResult.ok({"permissions": permissions}, self.name)


# ── Android system info ───────────────────────────────────────────────────────


class AndroidInfoAdapter(CapabilityAdapter):
    name = "android.info"
    priority = 100

    def is_available(self) -> bool:
        return _in_termux() and is_available("getprop")

    def get_android_info(self) -> CapabilityResult:
        props: dict[str, str] = {}
        for key in [
            "ro.build.version.release",
            "ro.build.version.sdk",
            "ro.product.model",
            "ro.product.manufacturer",
            "ro.product.cpu.abi",
        ]:
            result = run(["getprop", key], timeout=3)
            if result.success:
                props[key.split(".")[-1]] = result.stdout.strip()
        return CapabilityResult.ok(props, self.name)


# ── Shared Android storage ────────────────────────────────────────────────────


class AndroidStorageAdapter(CapabilityAdapter):
    name = "android.storage"
    priority = 90  # below Termux filesystem adapter for most file ops

    def is_available(self) -> bool:
        return _in_termux() and (Path.home() / "storage").exists()

    def read_file(self, path: str) -> CapabilityResult:
        try:
            content = Path(path).read_text(encoding="utf-8")
            return CapabilityResult.ok({"content": content, "path": path}, self.name)
        except Exception as e:
            return CapabilityResult.fail(
                str(e),
                self.name,
                reason=f"Cannot read {path}",
                corrective_action="Run termux-setup-storage to enable shared storage access",
            )

    def write_file(self, path: str, content: str) -> CapabilityResult:
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return CapabilityResult.ok({"written": True, "path": path}, self.name)
        except Exception as e:
            return CapabilityResult.fail(
                str(e), self.name, corrective_action="Run termux-setup-storage to enable shared storage access"
            )

    def list_directory(self, path: str) -> CapabilityResult:
        try:
            entries = sorted(str(p) for p in Path(path).iterdir())
            return CapabilityResult.ok({"entries": entries}, self.name)
        except Exception as e:
            return CapabilityResult.fail(str(e), self.name)


# ── Disk usage ──────────────────────────────────────────────────────────────
# Separate from AndroidStorageAdapter above (which is about shared-storage
# file access via ~/storage) — `df` works regardless of whether the shared
# storage symlink exists, so it needs its own availability check.


class AndroidDiskUsageAdapter(CapabilityAdapter):
    name = "android.disk_usage"
    priority = 100

    def is_available(self) -> bool:
        return _in_termux() and is_available("df")

    def get_disk_usage(self, path: str = "/data") -> CapabilityResult:
        result = run(["df", "-h", path], timeout=5)
        if not result.success or not result.stdout:
            return CapabilityResult.fail(
                result.stderr or "df failed", self.name, reason=f"Cannot read disk usage for {path}"
            )
        lines = result.stdout.strip().splitlines()
        if len(lines) < 2:
            return CapabilityResult.fail("Unexpected df output", self.name)
        parts = lines[1].split()
        if len(parts) < 4:
            return CapabilityResult.fail("Unexpected df output", self.name)
        return CapabilityResult.ok({"total": parts[1], "used": parts[2], "avail": parts[3]}, self.name)


# ── Installed apps ────────────────────────────────────────────────────────────
# Uses Android's `pm` (package manager) binary, reachable from a plain Termux
# shell without termux-api. Note: Android's package-visibility filtering may
# restrict what a non-privileged app like Termux can see without the
# QUERY_ALL_PACKAGES permission (which Termux doesn't request) — this surfaces
# whatever the device actually returns rather than assuming completeness.


class AndroidAppsAdapter(CapabilityAdapter):
    name = "android.apps"
    priority = 100

    def is_available(self) -> bool:
        return _in_termux() and is_available("pm")

    def list_installed_apps(self) -> CapabilityResult:
        result = run(["pm", "list", "packages"], timeout=10)
        if not result.success:
            return CapabilityResult.fail(
                result.stderr or "pm list packages failed",
                self.name,
                corrective_action="pm requires a real Android/Termux environment",
            )
        packages = sorted(
            line.split(":", 1)[1] for line in result.stdout.strip().splitlines() if line.startswith("package:")
        )
        return CapabilityResult.ok({"count": len(packages), "packages": packages}, self.name)


# ── All Android adapters (for registry auto-registration) ─────────────────────

ANDROID_ADAPTERS: list[type[CapabilityAdapter]] = [
    AndroidBatteryAdapter,
    AndroidClipboardAdapter,
    AndroidNotificationAdapter,
    AndroidWifiAdapter,
    AndroidBluetoothAdapter,
    AndroidLocationAdapter,
    AndroidCameraAdapter,
    AndroidMicrophoneAdapter,
    AndroidWakeLockAdapter,
    AndroidDiskUsageAdapter,
    AndroidAppsAdapter,
    AndroidIntentAdapter,
    AndroidPermissionAdapter,
    AndroidInfoAdapter,
    AndroidStorageAdapter,
]

# Backward-compatible alias
AndroidAdapter = AndroidBatteryAdapter
