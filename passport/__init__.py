"""FlowCore — Passport system.

Every agent receives a Passport before it executes.
Without a valid Passport, no execution proceeds.
"""

from passport.schema import Passport, AgentIdentity, RuntimeInfo
from passport.generator import PassportGenerator
from passport.validator import PassportValidator, ValidationResult

__all__ = [
    "Passport",
    "AgentIdentity",
    "RuntimeInfo",
    "PassportGenerator",
    "PassportValidator",
    "ValidationResult",
]
