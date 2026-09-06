"""Human-in-the-Loop Approval Manager for high-risk actions."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

STORAGE_DIR = Path(__file__).resolve().parent.parent.parent / "storage"
APPROVALS_FILE = STORAGE_DIR / "approvals.json"


class ApprovalManager:
    def __init__(self, storage_file: Path = APPROVALS_FILE) -> None:
        self.storage_file = storage_file
        self.storage_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.storage_file.exists():
            self._save_approvals([])

    def _load_approvals(self) -> List[Dict[str, Any]]:
        try:
            with open(self.storage_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save_approvals(self, approvals: List[Dict[str, Any]]) -> None:
        with open(self.storage_file, "w", encoding="utf-8") as f:
            json.dump(approvals, f, indent=2, ensure_ascii=False)

    def request_approval(
        self,
        agent_id: str,
        title: str,
        description: str,
        action_type: str,
        payload: Dict[str, Any],
        risk_level: str = "HIGH",
    ) -> Dict[str, Any]:
        approvals = self._load_approvals()
        approval_id = f"appr_{uuid.uuid4().hex[:8]}"

        item = {
            "id": approval_id,
            "agent_id": agent_id,
            "title": title,
            "description": description,
            "action_type": action_type,
            "payload": payload,
            "risk_level": risk_level,
            "status": "PENDING",  # PENDING, APPROVED, REJECTED
            "created_at": time.time(),
            "updated_at": time.time(),
            "reviewed_by": None,
        }
        approvals.append(item)
        self._save_approvals(approvals)
        return item

    def list_pending_approvals(self) -> List[Dict[str, Any]]:
        approvals = self._load_approvals()
        return [a for a in approvals if a.get("status") == "PENDING"]

    def list_all_approvals(self, limit: int = 50) -> List[Dict[str, Any]]:
        approvals = self._load_approvals()
        return approvals[-limit:]

    def resolve_approval(self, approval_id: str, approved: bool, user: str = "advisor") -> Dict[str, Any]:
        approvals = self._load_approvals()
        for a in approvals:
            if a.get("id") == approval_id:
                a["status"] = "APPROVED" if approved else "REJECTED"
                a["updated_at"] = time.time()
                a["reviewed_by"] = user
                self._save_approvals(approvals)
                return a
        raise KeyError(f"Approval request '{approval_id}' not found.")


_approval_instance = ApprovalManager()

def get_approval_manager() -> ApprovalManager:
    return _approval_instance
