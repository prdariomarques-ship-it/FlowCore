"""FlowCore — Passport validator."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from passport.schema import Passport


@dataclass
class ValidationResult:
    valid: bool
    reason: str = ""

    def __bool__(self) -> bool:
        return self.valid


class PassportValidator:
    """Validates passports before allowing agent execution."""

    def validate(self, passport: Passport) -> ValidationResult:
        """Run all validation checks. Returns first failure or OK."""
        checks = [
            self._check_not_expired,
            self._check_hash_integrity,
            self._check_has_agent,
            self._check_has_capabilities,
        ]
        for check in checks:
            result = check(passport)
            if not result.valid:
                return result
        return ValidationResult(valid=True, reason="ok")

    def require_capability(self, passport: Passport, capability: str) -> ValidationResult:
        """Check passport is valid AND grants a specific capability."""
        result = self.validate(passport)
        if not result:
            return result
        if capability not in passport.capabilities:
            return ValidationResult(
                valid=False,
                reason=f"capability '{capability}' not granted in passport",
            )
        return ValidationResult(valid=True, reason="ok")

    def require_permission(self, passport: Passport, permission: str) -> ValidationResult:
        """Check passport is valid AND grants a specific permission."""
        result = self.validate(passport)
        if not result:
            return result
        if permission not in passport.permissions:
            return ValidationResult(
                valid=False,
                reason=f"permission '{permission}' not granted in passport",
            )
        return ValidationResult(valid=True, reason="ok")

    # ── Individual checks ─────────────────────────────────────────────────────

    def _check_not_expired(self, passport: Passport) -> ValidationResult:
        if passport.is_expired():
            return ValidationResult(valid=False, reason="passport expired")
        return ValidationResult(valid=True)

    def _check_hash_integrity(self, passport: Passport) -> ValidationResult:
        expected = self._recompute_hash(passport)
        if passport.hash != expected:
            return ValidationResult(valid=False, reason="passport hash mismatch — tampering detected")
        return ValidationResult(valid=True)

    def _check_has_agent(self, passport: Passport) -> ValidationResult:
        if not passport.agent or not passport.agent.name:
            return ValidationResult(valid=False, reason="passport missing agent identity")
        return ValidationResult(valid=True)

    def _check_has_capabilities(self, passport: Passport) -> ValidationResult:
        if passport.capabilities is None:
            return ValidationResult(valid=False, reason="passport capabilities field missing")
        return ValidationResult(valid=True)

    # ── Hash helper ───────────────────────────────────────────────────────────

    @staticmethod
    def _recompute_hash(passport: Passport) -> str:
        payload = json.dumps(
            {
                "agent": passport.agent.to_dict(),
                "issued_at": passport.issued_at,
                "expires_at": passport.expires_at,
                "capabilities": sorted(passport.capabilities),
                "permissions": sorted(passport.permissions),
                "health_status": passport.health_status,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode()).hexdigest()
