from enum import Enum


class Status(str, Enum):
    """Official FlowCore status enums representing the stages of the Context Engine validation."""
    UNKNOWN = "UNKNOWN"
    NOT_READY = "NOT_READY"
    DISCOVERING = "DISCOVERING"
    SCANNING = "SCANNING"
    CLASSIFYING = "CLASSIFYING"
    VALIDATING = "VALIDATING"
    ANALYZING = "ANALYZING"
    READY = "READY"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
