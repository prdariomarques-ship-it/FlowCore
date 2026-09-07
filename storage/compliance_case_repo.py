"""FlowCore Compliance Case Entity & Repository.
Manages persistent state, HITL approvals, and lifecycle status for non-compliance cases.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid


class CaseStatus:
    OPEN = "OPEN"
    UNDER_REVIEW = "UNDER_REVIEW"
    ACTION_PROPOSED = "ACTION_PROPOSED"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    RESOLVED = "RESOLVED"


@dataclass
class ComplianceCase:
    id: str
    client_id: str
    portfolio_id: str
    type: str
    severity: str
    current_value: float
    limit_value: float
    difference: float
    policy_id: str
    reason: str
    suggested_action: str
    status: str = CaseStatus.OPEN
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    resolved_at: Optional[str] = None
    resolved_by: Optional[str] = None
    proposed_rebalancing: Optional[Dict[str, Any]] = None
    ai_explanation: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "client_id": self.client_id,
            "portfolio_id": self.portfolio_id,
            "type": self.type,
            "severity": self.severity,
            "current_value": self.current_value,
            "limit_value": self.limit_value,
            "difference": self.difference,
            "policy_id": self.policy_id,
            "reason": self.reason,
            "suggested_action": self.suggested_action,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "resolved_at": self.resolved_at,
            "resolved_by": self.resolved_by,
            "proposed_rebalancing": self.proposed_rebalancing,
            "ai_explanation": self.ai_explanation,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ComplianceCase":
        return cls(**data)


class ComplianceCaseRepository:
    def __init__(self, storage_path: Optional[Path] = None):
        if storage_path is None:
            storage_path = Path(__file__).parent.parent / "data" / "compliance_cases.json"
        self.storage_path = storage_path
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.storage_path.exists():
            self._save_cases({})

    def _load_cases(self) -> Dict[str, Dict[str, Any]]:
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_cases(self, cases: Dict[str, Dict[str, Any]]):
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(cases, f, indent=2, ensure_ascii=False)

    def save(self, case: ComplianceCase) -> ComplianceCase:
        case.updated_at = datetime.now(timezone.utc).isoformat()
        cases = self._load_cases()
        cases[case.id] = case.to_dict()
        self._save_cases(cases)
        return case

    def get_by_id(self, case_id: str) -> Optional[ComplianceCase]:
        cases = self._load_cases()
        data = cases.get(case_id)
        return ComplianceCase.from_dict(data) if data else None

    def list_cases(self, status: Optional[str] = None, client_id: Optional[str] = None) -> List[ComplianceCase]:
        cases = self._load_cases()
        result = []
        for c in cases.values():
            item = ComplianceCase.from_dict(c)
            if status and item.status != status:
                continue
            if client_id and item.client_id != client_id:
                continue
            result.append(item)
        return result


compliance_case_repo = ComplianceCaseRepository()
