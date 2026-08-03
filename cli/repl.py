from __future__ import annotations

import json

from capabilities.registry import (
    CAPABILITIES,
    CapabilityResult,
    CapabilityStatus,
    capability,
)

try:
    import readline  # noqa: F401
except ImportError:
    readline = None


def _print_result(result: CapabilityResult) -> None:
    print(f"\n{result.name}: {result.status.value}")
    if result.status == CapabilityStatus.REAL:
        if isinstance(result.data, dict):
            for key, value in result.data.items():
                rendered = (
                    json.dumps(value, ensure_ascii=False)
                    if isinstance(value, (dict, list))
                    else value
                )
                print(f"  {key}: {rendered}")
        else:
            print(f"  {result.data}")
    elif result.status == CapabilityStatus.NOT_IMPLEMENTED:
        print("  Status: NOT AVAILABLE")
        print(f"  Reason: {result.error}")
    else:
        print(f"  Status: {result.status.value}")
        print(f"  Reason: {result.error}")
        if result.data is not None:
            print(f"  Data: {json.dumps(result.data, ensure_ascii=False)}")
    print(f"  Provider: {result.provider}")


def run() -> None:
    print("╔══════════════════════════════╗")
    print("        FLOWCORE")
    print("╚══════════════════════════════╝")
    print()
    while True:
        try:
            command = input("FlowCore > ").strip().lower()
        except EOFError:
            print()
            return
        except KeyboardInterrupt:
            print()
            continue
        if command in {"exit", "quit"}:
            print("Bye.")
            return
        if not command:
            continue
        if command == "help":
            print("Commands: " + ", ".join(CAPABILITIES) + ", help, exit")
            continue
        if command not in CAPABILITIES:
            print(f"Unknown command: {command}. Type 'help' for available commands.")
            continue
        _print_result(capability(command))
