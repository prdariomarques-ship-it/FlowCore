"""FlowCore Doctor Agent — runs the doctor service and returns a health report."""
from __future__ import annotations

from typing import Any

from agents.base import BaseAgent


class DoctorAgent(BaseAgent):
    name = "doctor"
    description = "Runs all FlowCore health checks and returns a structured report"
    version = "0.1.0"

    async def run(self, context: dict | None = None) -> dict[str, Any]:
        try:
            from doctor.service import DoctorService
            report = DoctorService().run(verbose=False)
            checks = [
                {
                    "name": c.name,
                    "status": c.status.value,
                    "message": c.message,
                    "fix": c.fix,
                }
                for c in report.checks
            ]
            passed = sum(1 for c in report.checks if c.status.value == "pass")
            failed = sum(1 for c in report.checks if c.status.value == "fail")
            warned = sum(1 for c in report.checks if c.status.value == "warn")
            overall = "ok" if failed == 0 else "degraded"
            return {
                "status": overall,
                "data": {
                    "summary": {
                        "total": len(checks),
                        "passed": passed,
                        "failed": failed,
                        "warnings": warned,
                    },
                    "checks": checks,
                },
            }
        except Exception as exc:
            return {"status": "error", "data": {"error": str(exc)}}
