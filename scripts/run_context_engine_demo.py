#!/usr/bin/env python3
"""
FlowCore Context Engine Sprint 2 (v3.0) — Demo & Execution walkthrough.
Demonstrates the Triple Contract generation, abstract Capability Registry, and FlowCore Passport builder.
"""
import sys
import json
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from flowcore.intelligence.context import (
    ContextEngine,
    TripleContractManager,
    CapabilityRegistry,
    PassportBuilder,
    SchemaValidator,
)


def main():
    print("================================================================")
    print("  FlowCore Context Engine & Platform Bootloader — Sprint 2 Demo")
    print("================================================================")

    # 1. Pipeline Execution
    engine = ContextEngine(project_root)
    print(f"[*] Platform Boot Workspace: {engine.workspace_path}")
    print("[*] Running Context Validation Pipeline...")
    try:
        frame = engine.validate()
        print("[+] Success! Context Frame Status transitioned to READY.")
    except Exception as e:
        print(f"[-] Boot Pipeline Failed: {e}")
        sys.exit(1)

    print(f"\n[*] Executing Triple Contract Manager for {project_root.name}...")
    manager = TripleContractManager(project_root)
    paths = manager.generate_all_contracts(frame)
    print("[+] Generated official versioned JSON contracts:")
    print(f"    - flowcore.capabilities.json -> {paths['capabilities'].name}")
    print(f"    - flowcore.runtime.json      -> {paths['runtime'].name}")
    print(f"    - flowcore.context.json      -> {paths['context'].name}")

    # 2. Schema Validation checks
    print("\n[*] Running zero-dependency contract validation check...")
    with open(paths['context'], "r") as f:
        context_data = json.load(f)
    with open(paths['runtime'], "r") as f:
        runtime_data = json.load(f)
    with open(paths['capabilities'], "r") as f:
        capabilities_data = json.load(f)

    v1 = SchemaValidator.validate_context(context_data)
    v2 = SchemaValidator.validate_runtime(runtime_data)
    v3 = SchemaValidator.validate_capabilities(capabilities_data)

    if v1 and v2 and v3:
        print("[+] All contracts structure validated perfectly against versioned schemas!")
    else:
        print("[-] Contract structural validation failed.")

    # 3. Capability Resolution
    print("\n[*] Resolving platform capability intentions (No direct CLI execution):")
    registry = CapabilityRegistry(project_root)
    for cap in ["battery", "install_python_package", "list_files"]:
        resolved = registry.resolve(cap)
        print(f"    - Capability '{cap}': {resolved['description']}")
        print(f"      Resolution Paths: Android API: {resolved.get('android_api')}, Termux API: {resolved.get('termux_api')}, Shell: {resolved.get('shell')}")

    # 4. Passport Generation
    print("\n[*] Constructing the secure FlowCore Passport transit card...")
    passport_builder = PassportBuilder()
    passport = passport_builder.build_passport(frame)
    passport_dict = passport.to_dict()

    print("[+] FlowCore Passport assembled:")
    print(f"    - Active Agent:        {passport_dict['agent']['active_agent']}")
    print(f"    - Platform/Runtime:    {passport_dict['runtime']['platform']} ({passport_dict['runtime']['engine']})")
    print(f"    - Health Status:       {passport_dict['health']['status']}")
    print(f"    - Secure Context Hash: {passport_dict['context_hash']}")
    print(f"    - Secure Runtime Hash: {passport_dict['runtime_hash']}")
    print("================================================================")
    print("  Bootloader Complete - Ready for external Agents execution.")
    print("================================================================")


if __name__ == "__main__":
    main()
