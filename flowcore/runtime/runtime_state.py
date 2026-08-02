from enum import Enum


class RuntimeState(str, Enum):
    """Possible operational states for the FlowCore platform runtime environment."""
    NOT_READY = "NOT_READY"
    BOOTING = "BOOTING"
    LOADING_PROVIDERS = "LOADING_PROVIDERS"
    VALIDATING_PERMISSIONS = "VALIDATING_PERMISSIONS"
    HEALTH_CHECK = "HEALTHY"
    READY = "READY"
    FAILED = "FAILED"
