"""FlowCore Compliance Policy Entity & Repository.
Defines asset allocation boundaries per profile and office.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class CompliancePolicy:
    policy_id: str
    office_id: str
    profile: str
    asset_class: str
    max_percentage: float
    warning_threshold: float
    critical_threshold: float
    effective_from: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    effective_until: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "office_id": self.office_id,
            "profile": self.profile,
            "asset_class": self.asset_class,
            "max_percentage": self.max_percentage,
            "warning_threshold": self.warning_threshold,
            "critical_threshold": self.critical_threshold,
            "effective_from": self.effective_from,
            "effective_until": self.effective_until,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CompliancePolicy":
        return cls(**data)


DEFAULT_POLICIES = [
    CompliancePolicy(
        policy_id="pol_rv_moderado",
        office_id="office_default",
        profile="Moderado",
        asset_class="Renda Variável",
        max_percentage=30.0,
        warning_threshold=0.0,
        critical_threshold=5.0,
    ),
    CompliancePolicy(
        policy_id="pol_rf_moderado",
        office_id="office_default",
        profile="Moderado",
        asset_class="Renda Fixa",
        max_percentage=80.0,
        warning_threshold=0.0,
        critical_threshold=5.0,
    ),
    CompliancePolicy(
        policy_id="pol_intl_moderado",
        office_id="office_default",
        profile="Moderado",
        asset_class="Internacional",
        max_percentage=20.0,
        warning_threshold=0.0,
        critical_threshold=5.0,
    ),
]


class CompliancePolicyRepository:
    def __init__(self, storage_path: Optional[Path] = None):
        if storage_path is None:
            storage_path = Path(__file__).parent.parent / "data" / "compliance_policies.json"
        self.storage_path = storage_path
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.storage_path.exists():
            self._save_policies({p.policy_id: p.to_dict() for p in DEFAULT_POLICIES})

    def _load_policies(self) -> Dict[str, Dict[str, Any]]:
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_policies(self, policies: Dict[str, Dict[str, Any]]):
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(policies, f, indent=2, ensure_ascii=False)

    def get_policy(
        self, profile: str, asset_class: str, office_id: str = "office_default"
    ) -> Optional[CompliancePolicy]:
        policies = self._load_policies()
        for p in policies.values():
            item = CompliancePolicy.from_dict(p)
            if (
                item.office_id == office_id
                and item.profile.lower() == profile.lower()
                and item.asset_class.lower() == asset_class.lower()
            ):
                return item
        for p in policies.values():
            item = CompliancePolicy.from_dict(p)
            if item.asset_class.lower() == asset_class.lower():
                return item
        return None

    def list_policies(self) -> List[CompliancePolicy]:
        return [CompliancePolicy.from_dict(p) for p in self._load_policies().values()]


compliance_policy_repo = CompliancePolicyRepository()
