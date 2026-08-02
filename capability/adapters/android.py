"""FlowCore Android Adapter — wraps Android APIs via Termux API.

Responsibilities:
- BatteryManager (battery level, status, health)
- ClipboardManager (get/set clipboard)
- NotificationManager (send notifications)
- WifiManager (network info)
- Android system info (version, SDK, model)

All Android API calls go through `termux-*` commands provided by Termux:API.
The agent layer never knows these commands exist.
"""
from __future__ import annotations

import json
import os

from capability.adapters.base import CapabilityAdapter, CapabilityResult
from runtime.shell import is_available, run


class AndroidAdapter(CapabilityAdapter):
    """Adapter for Android system capabilities via Termux:API."""

    name = "android"
    priority = 100  # Highest priority — preferred on Android

    def is_available(self) -> bool:
        """True if running in Termux with Termux:API installed."""
        termux_prefix = os.environ.get("PREFIX", "")
        in_termux = bool(termux_prefix)
        api_present = is_available("termux-battery-status")
        return in_termux and api_present

    # ── Battery ───────────────────────────────────────────────────────────────

    def get_battery(self) -> CapabilityResult:
        result = run(["termux-battery-status"], timeout=5)
        if not result.success:
            return CapabilityResult.fail(result.stderr, self.name)
        try:
            data = json.loads(result.stdout)
            return CapabilityResult.ok({
                "level": data.get("percentage", -1),
                "status": data.get("status", "unknown"),
                "health": data.get("health", "unknown"),
                "temperature": data.get("temperature", -1),
                "plugged": data.get("plugged", "unknown"),
            }, self.name)
        except json.JSONDecodeError as e:
            return CapabilityResult.fail(f"JSON parse error: {e}", self.name)

    # ── Clipboard ─────────────────────────────────────────────────────────────

    def get_clipboard(self) -> CapabilityResult:
        result = run(["termux-clipboard-get"], timeout=5)
        if result.success:
            return CapabilityResult.ok({"text": result.stdout}, self.name)
        return CapabilityResult.fail(result.stderr, self.name)

    def set_clipboard(self, text: str) -> CapabilityResult:
        result = run(["termux-clipboard-set", text], timeout=5)
        if result.success:
            return CapabilityResult.ok({"set": True}, self.name)
        return CapabilityResult.fail(result.stderr, self.name)

    # ── Notifications ─────────────────────────────────────────────────────────

    def send_notification(self, title: str, message: str) -> CapabilityResult:
        result = run(
            ["termux-notification", "--title", title, "--content", message],
            timeout=5,
        )
        if result.success:
            return CapabilityResult.ok({"sent": True}, self.name)
        return CapabilityResult.fail(result.stderr, self.name)

    # ── Network ───────────────────────────────────────────────────────────────

    def get_network_info(self) -> CapabilityResult:
        result = run(["termux-wifi-connectioninfo"], timeout=5)
        if not result.success:
            return CapabilityResult.fail(result.stderr, self.name)
        try:
            data = json.loads(result.stdout)
            return CapabilityResult.ok({
                "ssid": data.get("ssid", ""),
                "bssid": data.get("bssid", ""),
                "rssi": data.get("rssi", 0),
                "link_speed": data.get("link_speed_mbps", 0),
                "ip": data.get("ip", ""),
            }, self.name)
        except json.JSONDecodeError as e:
            return CapabilityResult.fail(f"JSON parse error: {e}", self.name)

    # ── System info ───────────────────────────────────────────────────────────

    def get_android_info(self) -> CapabilityResult:
        """Return Android system properties."""
        props = {}
        for key in [
            "ro.build.version.release",
            "ro.build.version.sdk",
            "ro.product.model",
            "ro.product.manufacturer",
            "ro.product.cpu.abi",
        ]:
            result = run(["getprop", key], timeout=3)
            if result.success:
                short_key = key.split(".")[-1]
                props[short_key] = result.stdout
        return CapabilityResult.ok(props, self.name)

    # ── Storage ───────────────────────────────────────────────────────────────

    def read_file(self, path: str) -> CapabilityResult:
        try:
            content = open(path, "r", encoding="utf-8").read()
            return CapabilityResult.ok({"content": content, "path": path}, self.name)
        except Exception as e:
            return CapabilityResult.fail(str(e), self.name)

    def write_file(self, path: str, content: str) -> CapabilityResult:
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return CapabilityResult.ok({"written": True, "path": path}, self.name)
        except Exception as e:
            return CapabilityResult.fail(str(e), self.name)

    def list_directory(self, path: str) -> CapabilityResult:
        try:
            from pathlib import Path
            entries = [str(p) for p in Path(path).iterdir()]
            return CapabilityResult.ok({"entries": sorted(entries)}, self.name)
        except Exception as e:
            return CapabilityResult.fail(str(e), self.name)
