"""FlowCore Runtime Discovery — detects the real environment.

RuntimeDiscovery interrogates the host system and produces a complete picture:
- Platform type (android/termux/linux/macos/docker/windows)
- Environment variables critical to the runtime
- Installed tool availability and versions
- Android/Termux-specific state
- Network reachability

This output feeds directly into flowcore.runtime.json.
"""
from __future__ import annotations

import os
import platform
import socket
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from runtime.shell import is_available, run, version_of, which


# ── Platform detection ────────────────────────────────────────────────────────

def _is_termux() -> bool:
    return bool(os.environ.get("PREFIX")) and os.path.exists(
        os.environ.get("PREFIX", "") + "/bin/bash"
    )


def _is_android() -> bool:
    return _is_termux() or os.path.exists("/system/bin/app_process")


def _is_docker() -> bool:
    return os.path.exists("/.dockerenv") or (
        os.path.exists("/proc/1/cgroup")
        and "docker" in Path("/proc/1/cgroup").read_text(errors="ignore")
    )


def _detect_platform_type() -> str:
    if _is_termux():
        return "termux"
    if _is_android():
        return "android"
    if _is_docker():
        return "docker"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform == "win32":
        return "windows"
    return "linux"


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class ToolInfo:
    name: str
    available: bool
    version: str | None = None
    path: str | None = None


@dataclass
class EnvSnapshot:
    prefix: str = ""
    home: str = ""
    tmpdir: str = ""
    ld_library_path: str = ""
    path: str = ""
    pythonhome: str = ""
    pythonpath: str = ""
    shell: str = ""


@dataclass
class AndroidInfo:
    detected: bool = False
    version: str = ""
    sdk: str = ""
    device_model: str = ""
    cpu_abi: str = ""


@dataclass
class TermuxInfo:
    detected: bool = False
    prefix: str = ""
    api_available: bool = False
    pkg_available: bool = False
    storage_available: bool = False


@dataclass
class NetworkInfo:
    internet: bool = False
    dns: bool = False
    hostname: str = ""
    local_ip: str = ""
    oracle_reachable: bool = False
    docker_reachable: bool = False
    mcp_reachable: bool = False


@dataclass
class RuntimeSnapshot:
    platform_type: str = ""
    python_version: str = ""
    python_path: str = ""
    architecture: str = ""
    env: EnvSnapshot = field(default_factory=EnvSnapshot)
    android: AndroidInfo = field(default_factory=AndroidInfo)
    termux: TermuxInfo = field(default_factory=TermuxInfo)
    tools: dict[str, ToolInfo] = field(default_factory=dict)
    network: NetworkInfo = field(default_factory=NetworkInfo)
    capabilities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Convert ToolInfo list to {name: info}
        d["tools"] = {k: v for k, v in d["tools"].items()}
        return d


# ── Discovery engine ──────────────────────────────────────────────────────────

class RuntimeDiscovery:
    """Discovers and returns the complete runtime snapshot of the host device."""

    # Tools to probe — every entry becomes a ToolInfo in the snapshot
    _TOOLS = [
        "python3", "python", "pip3", "pip",
        "git", "ssh", "scp", "rsync",
        "curl", "wget",
        "sqlite3", "jq",
        "pkg",          # Termux package manager
        "getprop",      # Android system properties
        # Termux:API tools
        "termux-info",
        "termux-battery-status",
        "termux-clipboard-get",
        "termux-notification",
        "termux-camera-photo",
        "termux-microphone-record",
        "termux-location",
        "termux-bluetooth-get-adapters",
        "termux-wifi-connectioninfo",
        "termux-wifi-scaninfo",
        "termux-open-url",
        "termux-vibrate",
        "termux-torch",
        "termux-share",
        "termux-wake-lock",
        "termux-wake-unlock",
        "termux-job-scheduler",
        # Scheduling
        "crontab",
        # Other tools
        "node", "npm",
        "docker",
        "adb",
    ]

    def run(self) -> RuntimeSnapshot:
        snap = RuntimeSnapshot()
        snap.platform_type = _detect_platform_type()
        snap.python_version = sys.version.split()[0]
        snap.python_path = sys.executable
        snap.architecture = platform.machine()

        snap.env = self._scan_env()
        snap.android = self._scan_android()
        snap.termux = self._scan_termux(snap.env)
        snap.tools = self._scan_tools()
        snap.network = self._scan_network()
        snap.capabilities = self._derive_capabilities(snap)
        return snap

    # ── Environment ───────────────────────────────────────────────────────────

    def _scan_env(self) -> EnvSnapshot:
        return EnvSnapshot(
            prefix=os.environ.get("PREFIX", ""),
            home=os.environ.get("HOME", str(Path.home())),
            tmpdir=os.environ.get("TMPDIR", "/tmp"),
            ld_library_path=os.environ.get("LD_LIBRARY_PATH", ""),
            path=os.environ.get("PATH", ""),
            pythonhome=os.environ.get("PYTHONHOME", ""),
            pythonpath=os.environ.get("PYTHONPATH", ""),
            shell=os.environ.get("SHELL", ""),
        )

    # ── Android ───────────────────────────────────────────────────────────────

    def _scan_android(self) -> AndroidInfo:
        info = AndroidInfo()
        if not _is_android():
            return info

        info.detected = True

        # Read Android system properties via getprop if available
        if is_available("getprop"):
            info.version = self._getprop("ro.build.version.release")
            info.sdk = self._getprop("ro.build.version.sdk")
            info.device_model = self._getprop("ro.product.model")
            info.cpu_abi = self._getprop("ro.product.cpu.abi")
        else:
            # Termux env often exposes these
            info.version = os.environ.get("ANDROID_VERSION", "unknown")
            info.sdk = os.environ.get("ANDROID_SDK", "unknown")

        return info

    def _getprop(self, key: str) -> str:
        result = run(["getprop", key], timeout=3)
        return result.stdout if result.success else ""

    # ── Termux ────────────────────────────────────────────────────────────────

    def _scan_termux(self, env: EnvSnapshot) -> TermuxInfo:
        info = TermuxInfo()
        if not _is_termux():
            return info

        info.detected = True
        info.prefix = env.prefix or os.environ.get("PREFIX", "")
        info.pkg_available = is_available("pkg")
        info.api_available = is_available("termux-battery-status")

        # Check if storage is set up (Termux storage setup creates ~/storage)
        storage_path = Path.home() / "storage"
        info.storage_available = storage_path.exists()

        return info

    # ── Tools ─────────────────────────────────────────────────────────────────

    def _scan_tools(self) -> dict[str, ToolInfo]:
        tools: dict[str, ToolInfo] = {}
        for name in self._TOOLS:
            path = which(name)
            available = path is not None
            ver = None
            if available:
                ver = version_of(name)
            tools[name] = ToolInfo(name=name, available=available, version=ver, path=path)
        return tools

    # ── Network ───────────────────────────────────────────────────────────────

    def _scan_network(self) -> NetworkInfo:
        net = NetworkInfo()

        try:
            net.hostname = socket.gethostname()
            net.local_ip = socket.gethostbyname(net.hostname)
        except Exception:
            pass

        net.dns = self._check_dns("8.8.8.8")
        net.internet = net.dns and self._check_tcp("google.com", 443, timeout=3)

        # External service reachability — only if internet works
        if net.internet:
            oracle_host = os.environ.get("FLOWCORE_ORACLE_HOST", "")
            if oracle_host:
                net.oracle_reachable = self._check_tcp(oracle_host, 443, timeout=5)

            docker_host = os.environ.get("DOCKER_HOST", "")
            if docker_host:
                try:
                    host = docker_host.replace("tcp://", "").split(":")[0]
                    port = int(docker_host.split(":")[-1]) if ":" in docker_host else 2376
                    net.docker_reachable = self._check_tcp(host, port, timeout=3)
                except Exception:
                    pass

        return net

    def _check_dns(self, host: str) -> bool:
        try:
            socket.getaddrinfo(host, None, socket.AF_INET)
            return True
        except Exception:
            return False

    def _check_tcp(self, host: str, port: int, *, timeout: int = 3) -> bool:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except Exception:
            return False

    # ── Capabilities ──────────────────────────────────────────────────────────

    def _derive_capabilities(self, snap: RuntimeSnapshot) -> list[str]:
        """Derive which named capabilities are available from discovered tools."""
        caps: list[str] = []

        def _has(tool: str) -> bool:
            return snap.tools.get(tool, ToolInfo(tool, False)).available

        # Termux:API capabilities — require termux-api package
        if _has("termux-battery-status"):
            caps.append("getBattery")
        if _has("termux-clipboard-get"):
            caps.extend(["getClipboard", "setClipboard"])
        if _has("termux-notification"):
            caps.append("sendNotification")
        if _has("termux-wifi-connectioninfo"):
            caps.append("getNetworkInfo")
        if _has("termux-wifi-scaninfo"):
            caps.append("getWifiScan")
        if _has("termux-bluetooth-get-adapters"):
            caps.append("getBluetoothState")
        if _has("termux-location"):
            caps.append("getLocation")
        if _has("termux-camera-photo"):
            caps.append("takePhoto")
        if _has("termux-microphone-record"):
            caps.append("recordAudio")
        if _has("termux-vibrate"):
            caps.append("vibrate")
        if _has("termux-torch"):
            caps.append("torch")
        if _has("termux-open-url"):
            caps.append("openUrl")
        if _has("termux-share"):
            caps.append("shareFile")
        if _has("termux-wake-lock"):
            caps.extend(["acquireWakeLock", "releaseWakeLock"])
        if _has("termux-info"):
            caps.extend(["checkPermission", "listPermissions"])
        if _has("getprop"):
            caps.append("getAndroidInfo")

        # Core Termux/Linux capabilities
        if _has("python3") or _has("python"):
            caps.append("runPython")
        if _has("git"):
            caps.append("runGit")
        if _has("ssh"):
            caps.append("runSSH")
        if _has("sqlite3"):
            caps.append("runSQLite")
        if snap.platform_type not in ("windows",):
            caps.extend(["runShell", "readFile", "writeFile", "listDirectory"])
        if snap.platform_type not in ("windows",):
            caps.append("installPackage")
        if _has("curl") or True:  # urllib always available
            caps.append("httpRequest")
        if snap.platform_type not in ("windows",):
            caps.extend(["startService", "stopService", "listServices", "scheduleJob"])

        return caps
