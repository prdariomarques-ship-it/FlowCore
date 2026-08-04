#!/usr/bin/env python3
"""
FlowCore Runtime Sprint 3 (v4.0) — Demo & Execution walkthrough.
Demonstrates the local OS abstraction, structured Boot sequence, and Capability execution via providers.
"""
import sys
import json
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from flowcore.runtime import RuntimeBootloader, RuntimeManager
from flowcore.runtime.runtime_logger import RuntimeLogger


def main():
    print("================================================================")
    print("  FlowCore Runtime & Platform Operating Environment — Sprint 3")
    print("================================================================")

    # 1. Boot sequence
    print("[*] Launching Runtime Bootloader...")
    bootloader = RuntimeBootloader(project_root)
    print(f"[*] Bootloader State before boot: {bootloader.state.value}")

    try:
        context = bootloader.boot()
        print("[+] Success! Runtime booted successfully.")
        print(f"[*] Bootloader State after boot: {bootloader.state.value}")
    except Exception as e:
        print(f"[-] Boot Failed: {e}")
        sys.exit(1)

    passport_path = project_root / "flowcore.runtime.passport.json"
    print(f"[+] Compiled active Runtime Passport: {passport_path.name}")

    # 2. Inspecting passport
    with open(passport_path, "r", encoding="utf-8") as f:
        passport_data = json.load(f)

    print(f"    - Platform:        {passport_data['platform']}")
    print(f"    - Health Status:   {passport_data['health']['status']}")
    print(f"    - Storage:         {passport_data['permissions']['storage']}")
    print(f"    - Capabilities:    {passport_data['capabilities']}")

    # 3. Execution of Capabilities via RuntimeManager (No direct bash CLI executed by Agent)
    print("\n[*] Execution Engine invoking Capabilities...")
    logger = RuntimeLogger()
    manager = bootloader.manager

    # Select Termux
    manager.switch_runtime("termux")
    active_runtime = manager.get_active_runtime()
    print(f"[*] Active Runtime Switched to: {active_runtime.platform}")

    # Invoke getBattery
    battery_res = active_runtime.execute_capability("getBattery")
    log_entry = logger.log_execution("getBattery", battery_res)
    print(f"    - Result (getBattery): {battery_res}")

    # Invoke installPythonPackage
    pip_res = active_runtime.execute_capability("installPythonPackage")
    log_entry = logger.log_execution("installPythonPackage", pip_res)
    print(f"    - Result (installPythonPackage): {pip_res}")

    # Switch to Android
    manager.switch_runtime("android")
    active_runtime = manager.get_active_runtime()
    print(f"\n[*] Active Runtime Switched to: {active_runtime.platform}")

    # Invoke getWifi
    wifi_res = active_runtime.execute_capability("getWifi")
    log_entry = logger.log_execution("getWifi", wifi_res)
    print(f"    - Result (getWifi): {wifi_res}")

    print("\n================================================================")
    print("  Runtime Boot & Capability Execution complete and fully audited.")
    print("================================================================")


if __name__ == "__main__":
    main()
