"""Capability adapter implementations."""
from capability.adapters.base import CapabilityAdapter, CapabilityResult
from capability.adapters.android import AndroidAdapter
from capability.adapters.termux import TermuxAdapter
from capability.adapters.linux import LinuxAdapter

__all__ = [
    "CapabilityAdapter",
    "CapabilityResult",
    "AndroidAdapter",
    "TermuxAdapter",
    "LinuxAdapter",
]
