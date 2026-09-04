"""FlowCore Health Agent — reports system health.

This is the only built-in agent.  It checks:
- CPU usage
- Memory usage
- Disk space
- Python version

Designed for Termux / Android environments.
"""
from __future__ import annotations

import os
import shutil
import sys
from typing import Any

from agents.base import BaseAgent


class HealthAgent(BaseAgent):
    name = "health"
    description = "Reports system health metrics (CPU, memory, disk)"
    version = "0.1.0"

    async def run(self, context: dict | None = None) -> dict[str, Any]:
        return {
            "status": "ok",
            "data": {
                "python_version": sys.version.split()[0],
                "platform": sys.platform,
                "termux": bool(os.environ.get("PREFIX")),
                "memory": self._get_memory(),
                "disk": self._get_disk(),
                "uptime": self._get_uptime(),
            },
        }

    async def health_check(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": "ok",
            "version": self.version,
        }

    @staticmethod
    def _get_memory() -> dict[str, Any]:
        """Get memory info — works on Linux/Termux."""
        try:
            with open("/proc/meminfo") as f:
                info = {}
                for line in f:
                    parts = line.split(":")
                    if len(parts) == 2:
                        key = parts[0].strip()
                        val = parts[1].strip().split()[0]
                        info[key] = int(val)
            return {
                "total_kb": info.get("MemTotal", 0),
                "free_kb": info.get("MemFree", 0),
                "available_kb": info.get("MemAvailable", 0),
            }
        except Exception:
            return {"error": "Cannot read /proc/meminfo"}

    @staticmethod
    def _get_disk() -> dict[str, Any]:
        """Get disk usage for the project directory."""
        try:
            usage = shutil.disk_usage("/")
            return {
                "total_gb": round(usage.total / 1024**3, 2),
                "used_gb": round(usage.used / 1024**3, 2),
                "free_gb": round(usage.free / 1024**3, 2),
            }
        except Exception:
            return {"error": "Cannot read disk usage"}

    @staticmethod
    def _get_uptime() -> dict[str, Any]:
        """Get system uptime."""
        try:
            with open("/proc/uptime") as f:
                uptime_sec = float(f.read().split()[0])
            return {
                "uptime_seconds": uptime_sec,
                "uptime_hours": round(uptime_sec / 3600, 2),
            }
        except Exception:
            return {"error": "Cannot read uptime"}
