from __future__ import annotations

import json
import os
import platform as platform_module
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from loguru import logger

from config.loader import get_config, get_config_path
from runtime.core import detect_platform

_PROCESS_START = time.monotonic()


class CapabilityStatus(str, Enum):
    REAL = "REAL"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    FAILED = "FAILED"
    MOCK = "MOCK"


@dataclass
class CapabilityResult:
    name: str
    status: CapabilityStatus
    provider: str
    data: Any = None
    error: str | None = None
    duration_ms: float = 0.0
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["status"] = self.status.value
        return result


TERMUX_API_BINARIES = {
    "battery": "termux-battery-status",
    "wifi": "termux-wifi-connectioninfo",
    "location": "termux-location",
    "camera_info": "termux-camera-info",
    "storage_get": "termux-storage-get",
    "notification": "termux-notification",
    "clipboard_get": "termux-clipboard-get",
}
CAPABILITY_TERMUX_BINARIES = {
    key: TERMUX_API_BINARIES[key] for key in ("battery", "wifi")
}


def _result(name: str, status: CapabilityStatus, provider: str,
            data: Any = None, error: str | None = None) -> CapabilityResult:
    return CapabilityResult(
        name=name,
        status=status,
        provider=provider,
        data=data,
        error=error,
        timestamp=datetime.now().astimezone().isoformat(),
    )


def _termux_result(name: str, binary: str, fields: list[str]) -> CapabilityResult:
    if not detect_platform()["android"]:
        return _result(
            name,
            CapabilityStatus.NOT_IMPLEMENTED,
            binary,
            error=f"{binary} is only available on Android/Termux",
        )
    executable = shutil.which(binary)
    if executable is None:
        return _result(
            name,
            CapabilityStatus.NOT_IMPLEMENTED,
            binary,
            error=(
                f"Termux:API binary '{binary}' not found in PATH; "
                "the termux-api package is not installed (pkg install termux-api)"
            ),
        )
    try:
        completed = subprocess.run(
            [executable], capture_output=True, text=True, timeout=10, check=False
        )
    except subprocess.TimeoutExpired:
        return _result(
            name,
            CapabilityStatus.FAILED,
            binary,
            error=(
                f"'{binary}' timed out after 10 seconds; Termux:API APK may "
                "not be installed or may not have the required permission"
            ),
        )
    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    if completed.returncode != 0:
        return _result(
            name,
            CapabilityStatus.FAILED,
            binary,
            error=stderr or stdout or f"exit code {completed.returncode}",
        )
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return _result(
            name,
            CapabilityStatus.FAILED,
            binary,
            error=f"Invalid JSON from {binary}: {stdout or str(exc)}",
        )
    data = {key: payload.get(key) for key in fields}
    if name == "wifi" and (
        not data.get("SSID") or data.get("SSID") == "<unknown ssid>"
    ):
        ssid_reason = (
            "SSID is <unknown ssid>"
            if data.get("SSID") == "<unknown ssid>"
            else "SSID is empty or unavailable"
        )
        return _result(
            name,
            CapabilityStatus.FAILED,
            binary,
            data=data,
            error=(
                f"{ssid_reason}. On Android 8.1+, grant location permission "
                "to Termux:API and enable GPS"
            ),
        )
    return _result(name, CapabilityStatus.REAL, binary, data=data)


def battery() -> CapabilityResult:
    return _termux_result(
        "battery", CAPABILITY_TERMUX_BINARIES["battery"],
        ["percentage", "status", "health", "temperature", "plugged"],
    )


def wifi() -> CapabilityResult:
    return _termux_result(
        "wifi", CAPABILITY_TERMUX_BINARIES["wifi"],
        ["SSID", "BSSID", "ip", "link_speed_mbps", "frequency_mhz", "rssi"],
    )


def storage() -> CapabilityResult:
    internal_path = Path.home()
    try:
        usage = shutil.disk_usage(internal_path)
        data: dict[str, Any] = {
            "internal": {
                "path": str(internal_path),
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
            }
        }
        shared = Path("/storage/emulated/0")
        try:
            shared_usage = shutil.disk_usage(shared)
            data["shared_android"] = {
                "path": str(shared),
                "total": shared_usage.total,
                "used": shared_usage.used,
                "free": shared_usage.free,
            }
        except OSError as exc:
            data["shared_android"] = {"path": str(shared), "available": False,
                                       "error": str(exc)}
        return _result("storage", CapabilityStatus.REAL, "shutil.disk_usage", data=data)
    except Exception as exc:
        return _result("storage", CapabilityStatus.FAILED, "shutil.disk_usage",
                       error=str(exc))


def context() -> CapabilityResult:
    platform = detect_platform()
    binaries = {
        name: {"path": shutil.which(binary), "available": bool(shutil.which(binary))}
        for name, binary in TERMUX_API_BINARIES.items()
    }
    return _result(
        "context", CapabilityStatus.REAL, "python-stdlib",
        data={
            "platform": platform,
            "termux": platform["termux"],
            "android": platform["android"],
            "cwd": str(Path.cwd()),
            "home": str(Path.home()),
            "prefix": os.environ.get("PREFIX"),
            "local_time": datetime.now().astimezone().isoformat(),
            "user": os.environ.get("USER") or os.environ.get("USERNAME"),
            "termux_api_binaries": binaries,
        },
    )


def _database_path() -> Path:
    url = get_config().get("database", {}).get("url", "")
    raw = url.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
    path = Path(raw)
    return path if path.is_absolute() else Path.cwd() / path


def runtime() -> CapabilityResult:
    cfg = get_config()
    db_path = _database_path()
    db_check: dict[str, Any] = {"path": str(db_path), "exists": db_path.exists()}
    try:
        import sqlite3
        with sqlite3.connect(db_path) as connection:
            connection.execute("SELECT 1").fetchone()
        db_check["accessible"] = True
    except Exception as exc:
        db_check["accessible"] = False
        db_check["error"] = str(exc)
    return _result(
        "runtime", CapabilityStatus.REAL, "python-stdlib",
        data={
            "version": cfg.get("app", {}).get("version"),
            "python_version": sys.version.split()[0],
            "pid": os.getpid(),
            "process_uptime_seconds": round(time.monotonic() - _PROCESS_START, 3),
            "database": db_check,
            "config_path": str(get_config_path()),
        },
    )


def _install_dir() -> Path:
    configured = os.environ.get("FLOWCORE_DATA_DIR")
    return Path(configured).expanduser() if configured else Path.home() / ".flowcore"


def passport() -> CapabilityResult:
    values: dict[str, Any] = {}
    unavailable: dict[str, str] = {}
    getprop = shutil.which("getprop")
    props = {
        "model": "ro.product.model",
        "manufacturer": "ro.product.manufacturer",
        "android_version": "ro.build.version.release",
    }
    if getprop:
        for field, prop in props.items():
            try:
                output = subprocess.run([getprop, prop], capture_output=True,
                                        text=True, timeout=5, check=False)
                value = output.stdout.strip()
                if value:
                    values[field] = value
                else:
                    values[field] = None
                    unavailable[field] = (
                        output.stderr.strip() or f"{prop} returned no value"
                    )
            except Exception as exc:
                values[field] = None
                unavailable[field] = str(exc)
    else:
        values["model"] = None
        values["manufacturer"] = None
        values["android_version"] = None
        unavailable["model"] = "getprop not found; platform.uname has no device model"
        unavailable["manufacturer"] = (
            "getprop not found; platform.uname has no manufacturer"
        )
        unavailable["android_version"] = (
            "getprop not found; platform.uname has no Android version"
        )
    uname = platform_module.uname()
    values["architecture"] = uname.machine or None
    values["hostname"] = socket.gethostname() or None
    if not values["architecture"]:
        unavailable["architecture"] = "platform.uname returned no architecture"
    if not values["hostname"]:
        unavailable["hostname"] = "hostname unavailable"
    install_path = _install_dir() / "install-id"
    try:
        install_path.parent.mkdir(parents=True, exist_ok=True)
        if install_path.exists():
            install_id = install_path.read_text().strip()
        else:
            install_id = str(uuid.uuid4())
            install_path.write_text(install_id)
        values["install_id"] = install_id or None
    except Exception as exc:
        values["install_id"] = None
        unavailable["install_id"] = str(exc)
    return _result("passport", CapabilityStatus.REAL, "python-stdlib",
                   data={**values, "unavailable": unavailable})


def doctor() -> CapabilityResult:
    checks: dict[str, dict[str, Any]] = {}
    try:
        checks["python"] = {"status": "PASS", "version": sys.version.split()[0]}
    except Exception as exc:
        checks["python"] = {"status": "FAIL", "error": str(exc)}
    try:
        import aiosqlite
        checks["sqlite"] = {"status": "PASS", "provider": "aiosqlite"}
    except Exception as exc:
        checks["sqlite"] = {"status": "FAIL", "error": str(exc)}
    db = _database_path()
    try:
        import sqlite3
        with sqlite3.connect(db) as connection:
            connection.execute("SELECT 1").fetchone()
        checks["database"] = {"status": "PASS", "path": str(db)}
    except Exception as exc:
        checks["database"] = {"status": "FAIL", "error": str(exc), "path": str(db)}
    try:
        json.dumps({"check": True})
        checks["json"] = {"status": "PASS"}
    except Exception as exc:
        checks["json"] = {"status": "FAIL", "error": str(exc)}
    try:
        cfg = get_config()
        checks["config"] = {
            "status": "PASS", "name": cfg["app"]["name"],
            "path": str(get_config_path()),
        }
    except Exception as exc:
        checks["config"] = {"status": "FAIL", "error": str(exc)}
    from flowcore import _get_ollama_url

    ollama_url = _get_ollama_url("tags")
    try:
        urllib.request.urlopen(ollama_url, timeout=5)
        checks["ollama"] = {"status": "PASS", "url": ollama_url}
    except Exception as exc:
        checks["ollama"] = {"status": "WARN", "error": str(exc), "url": ollama_url}
    for name, module in (("api", "fastapi"), ("scheduler", "apscheduler")):
        try:
            __import__(module)
            checks[name] = {"status": "PASS"}
        except Exception as exc:
            checks[name] = {"status": "WARN", "error": str(exc)}
    return _result(
        "doctor", CapabilityStatus.REAL, "python-stdlib", data={"checks": checks}
    )


def status() -> CapabilityResult:
    platform = detect_platform()
    binaries = {}
    for name, binary in TERMUX_API_BINARIES.items():
        binaries[name] = {
            "provider": binary,
            "path": shutil.which(binary),
            "available": bool(shutil.which(binary)),
        }
    availability = {
        name: item for name, item in binaries.items()
        if name in CAPABILITY_TERMUX_BINARIES
    }
    summaries = {
        name: {"provider": provider_name, "available": provider_available(name)}
        for name, provider_name in (
            ("storage", "shutil.disk_usage"), ("context", "python-stdlib"),
            ("runtime", "python-stdlib"), ("passport", "python-stdlib"),
            ("doctor", "python-stdlib"),
        )
    }
    summaries.update(availability)
    return _result("status", CapabilityStatus.REAL, "python-stdlib",
                   data={"platform": platform, "termux_available": platform["termux"],
                         "termux_api_binaries": binaries,
                         "capabilities": summaries})


CAPABILITIES: dict[str, Callable[[], CapabilityResult]] = {
    "status": status, "doctor": doctor, "battery": battery, "wifi": wifi,
    "storage": storage, "context": context, "runtime": runtime,
    "passport": passport,
}


def provider_available(name: str) -> bool:
    if name in TERMUX_API_BINARIES:
        return bool(
            detect_platform()["android"] and shutil.which(TERMUX_API_BINARIES[name])
        )
    if name == "storage":
        try:
            Path.home().stat()
            return True
        except OSError:
            return False
    if name == "context":
        return True
    if name == "runtime":
        try:
            get_config_path().stat()
            return True
        except OSError:
            return False
    if name == "passport":
        try:
            _install_dir().mkdir(parents=True, exist_ok=True)
            return True
        except OSError:
            return False
    return name == "doctor" and name in CAPABILITIES


def capability(name: str) -> CapabilityResult:
    started = time.perf_counter()
    provider = TERMUX_API_BINARIES.get(name, "python-stdlib")
    try:
        result = CAPABILITIES[name]()
    except Exception as exc:
        result = _result(name, CapabilityStatus.FAILED, provider, error=str(exc))
    result.duration_ms = round((time.perf_counter() - started) * 1000, 2)
    logger.info(
        "capability={} provider={} duration_ms={} result={} error={}",
        result.name, result.provider, result.duration_ms, result.status.value,
        result.error or "",
    )
    return result
