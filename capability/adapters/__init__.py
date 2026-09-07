"""Capability adapter implementations — Android, Termux, and Linux runtimes."""

from capability.adapters.base import CapabilityAdapter, CapabilityResult

from capability.adapters.android import (
    AndroidBatteryAdapter,
    AndroidClipboardAdapter,
    AndroidNotificationAdapter,
    AndroidWifiAdapter,
    AndroidBluetoothAdapter,
    AndroidLocationAdapter,
    AndroidCameraAdapter,
    AndroidMicrophoneAdapter,
    AndroidWakeLockAdapter,
    AndroidIntentAdapter,
    AndroidPermissionAdapter,
    AndroidInfoAdapter,
    AndroidStorageAdapter,
    AndroidAdapter,
    ANDROID_ADAPTERS,
)
from capability.adapters.termux import (
    TermuxPythonAdapter,
    TermuxGitAdapter,
    TermuxSSHAdapter,
    TermuxSQLiteAdapter,
    TermuxFilesystemAdapter,
    TermuxPackageAdapter,
    TermuxHTTPAdapter,
    TermuxShellAdapter,
    TermuxServiceAdapter,
    TermuxBatteryAdapter,
    TermuxAPIAdapter,
    TermuxAdapter,
    TERMUX_ADAPTERS,
)
from capability.adapters.linux import LinuxAdapter

__all__ = [
    "CapabilityAdapter",
    "CapabilityResult",
    # Android
    "AndroidBatteryAdapter",
    "AndroidClipboardAdapter",
    "AndroidNotificationAdapter",
    "AndroidWifiAdapter",
    "AndroidBluetoothAdapter",
    "AndroidLocationAdapter",
    "AndroidCameraAdapter",
    "AndroidMicrophoneAdapter",
    "AndroidWakeLockAdapter",
    "AndroidIntentAdapter",
    "AndroidPermissionAdapter",
    "AndroidInfoAdapter",
    "AndroidStorageAdapter",
    "AndroidAdapter",
    "ANDROID_ADAPTERS",
    # Termux
    "TermuxPythonAdapter",
    "TermuxGitAdapter",
    "TermuxSSHAdapter",
    "TermuxSQLiteAdapter",
    "TermuxFilesystemAdapter",
    "TermuxPackageAdapter",
    "TermuxHTTPAdapter",
    "TermuxShellAdapter",
    "TermuxServiceAdapter",
    "TermuxBatteryAdapter",
    "TermuxAPIAdapter",
    "TermuxAdapter",
    "TERMUX_ADAPTERS",
    # Linux
    "LinuxAdapter",
]
