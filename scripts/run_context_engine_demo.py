#!/usr/bin/env python3
"""
FlowCore Context Engine Phase 1 - Demo & Usage Example.
This script demonstrates how to instantiate and execute the Context Engine.
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from flowcore.intelligence.context import ContextEngine


def main():
    print("===============================================")
    print("  FlowCore Context Engine — Phase 1 Demo")
    print("===============================================")

    # Instantiate the engine targeting the project root
    engine = ContextEngine(project_root)

    print(f"[*] Target Workspace: {engine.workspace_path}")
    print("[*] Current State Before Scan:", engine.frame.status)

    print("\n[*] Running Context Validation Pipeline...")
    try:
        frame = engine.validate()
        print("[+] Success!")
    except Exception as e:
        print(f"[-] Validation Failed: {e}")
        sys.exit(1)

    print("\n===============================================")
    print("  Scan Results (flowcore.context.json)")
    print("===============================================")
    print(f"Project Name: {frame.project}")
    print(f"Language:     {frame.language}")
    print(f"Runtime:      {frame.runtime}")
    print(f"Project Type: {frame.type}")
    print(f"Status:       {frame.status}")
    print(f"Validated:    {frame.validated}")
    print(f"Timestamp:    {frame.timestamp}")
    print("\nDetected Key Artifacts:")
    for artifact in frame.artifacts:
        print(f"  - {artifact}")
    print("===============================================")


if __name__ == "__main__":
    main()
