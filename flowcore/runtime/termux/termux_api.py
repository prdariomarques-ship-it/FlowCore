from __future__ import annotations

import json
import shutil
import subprocess
from typing import Dict, Any


class TermuxApiProvider:
    """Real Provider to query system metrics using physical Termux:API binaries via subprocess."""

    def _execute_binary(self, binary_name: str, args: list[str] | None = None) -> Dict[str, Any]:
        """Verify binary presence in PATH and execute sychronously, returning JSON or NOT_IMPLEMENTED."""
        if not shutil.which(binary_name):
            return {
                "status": "NOT_IMPLEMENTED",
                "error": f"Binary '{binary_name}' not found. Termux:API is not installed or not running on Android host.",
                "solution": f"Install via: pkg install termux-api"
            }

        try:
            cmd = [binary_name] + (args or [])
            # Run safely with 5 seconds timeout
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                return {
                    "status": "FAILED",
                    "error": f"Binary '{binary_name}' exited with status {result.returncode}.",
                    "stderr": result.stderr.strip()
                }

            output = result.stdout.strip()
            if not output:
                return {"status": "SUCCESS", "data": ""}

            try:
                # Most Termux-API commands return JSON
                return json.loads(output)
            except json.JSONDecodeError:
                return {"status": "SUCCESS", "data": output}

        except Exception as e:
            return {
                "status": "FAILED",
                "error": f"Failed to execute '{binary_name}': {e}"
            }

    def get_battery(self) -> Dict[str, Any]:
        """Fetch battery status via termux-battery-status."""
        return self._execute_binary("termux-battery-status")

    def get_wifi(self) -> Dict[str, Any]:
        """Fetch Wi-Fi info via termux-wifi-connectioninfo."""
        return self._execute_binary("termux-wifi-connectioninfo")

    def get_location(self) -> Dict[str, Any]:
        """Fetch GPS location via termux-location."""
        return self._execute_binary("termux-location")

    def get_camera_info(self) -> Dict[str, Any]:
        """Fetch camera specifications via termux-camera-info."""
        return self._execute_binary("termux-camera-info")

    def get_clipboard(self) -> Dict[str, Any]:
        """Fetch clipboard text via termux-clipboard-get."""
        return self._execute_binary("termux-clipboard-get")

    def get_storage(self) -> Dict[str, Any]:
        """Fetch storage details via termux-storage-get (or fallback list)."""
        # If termux-storage-get is not found, try df / list files as standard fallback
        return self._execute_binary("termux-storage-get")

    def get_telephony_deviceinfo(self) -> Dict[str, Any]:
        """Fetch cellular device specs via termux-telephony-deviceinfo."""
        return self._execute_binary("termux-telephony-deviceinfo")

    def get_sensor(self) -> Dict[str, Any]:
        """Fetch sensor readings via termux-sensor."""
        # Querying sensors typically requires args, pass a list command to avoid hanging
        return self._execute_binary("termux-sensor", ["-l"])

    def get_notification(self, title: str = "FlowCore", content: str = "Service Active") -> Dict[str, Any]:
        """Create a notification via termux-notification."""
        return self._execute_binary("termux-notification", ["-t", title, "-c", content])
