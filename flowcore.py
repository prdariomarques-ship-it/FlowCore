#!/usr/bin/env python3
"""FlowCore — Main entry point.

Usage:
    python3 flowcore.py serve        Start the API server
    python3 flowcore.py run          Start the full application (API + scheduler + agents)
    python3 flowcore.py health       Quick health check
    python3 flowcore.py version      Print version
    python3 flowcore.py selftest     Validate the entire installation
    python3 flowcore.py chat         Interactive chat session
    python3 flowcore.py remember "<text>"    Save a memory
    python3 flowcore.py recall "<topic>"     Recall memories by topic
    python3 flowcore.py memories     List all memories
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Add project root to Python path so imports work regardless of CWD.
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.loader import get_config
from runtime.core import FlowCoreRuntime, detect_platform
from loguru import logger

# Colours
RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"
BOLD = "\033[1m"
NC = "\033[0m"


def selftest_check(name: str, fn, detail: str = "", skip: bool = False) -> str:
    """Run a single self-test check and return 'PASS', 'SKIPPED', or 'FAIL'."""
    if skip:
        print(f"  {YELLOW}SKIP{NC}  {name}")
        if detail:
            print(f"         {detail}")
        return "SKIPPED"
    try:
        fn()
        print(f"  {GREEN}PASS{NC}  {name}")
        if detail:
            print(f"         {detail}")
        return "PASS"
    except Exception as e:
        print(f"  {RED}FAIL{NC}  {name}")
        print(f"         {str(e)[:80]}")
        return "FAIL"

def cmd_selftest() -> None:
    """Validate the core FlowCore installation."""
    passed = 0
    skipped = 0
    failed = 0
    results = []

    print("")
    print(f"{BOLD}{CYAN}╔══════════════════════════════════════════════════╗{NC}")
    print(f"{BOLD}{CYAN}║         FlowCore Self-Test                      ║{NC}")
    print(f"{BOLD}{CYAN}╚══════════════════════════════════════════════════╝{NC}")
    print("")

    # ── CORE ONLY ────────────────────────────────────────────────────────
    print(f"{BOLD}CORE{NC}")

    # Config
    def _load_config():
        from config.loader import get_config
        cfg = get_config()
        assert cfg["app"]["name"] == "FlowCore"
        assert "api" in cfg
        assert cfg["api"]["host"] == "127.0.0.1"
    
    result = selftest_check("CONFIG", _load_config, "JSON loaded")
    results.append(result)
    if result == "PASS": passed += 1
    elif result == "FAIL": failed += 1

    # Executor
    def _executor_test():
        from executor.engine import ExecutorEngine
        executor = ExecutorEngine()
        assert executor is not None
    
    result = selftest_check("EXECUTOR", _executor_test, "Engine ready")
    results.append(result)
    if result == "PASS": passed += 1
    elif result == "FAIL": failed += 1

    # SQLite
    def _sqlite_test():
        import aiosqlite
        assert aiosqlite is not None
    
    result = selftest_check("SQLITE", _sqlite_test, "aiosqlite available")
    results.append(result)
    if result == "PASS": passed += 1
    elif result == "FAIL": failed += 1

    # Logging
    def _logging_test():
        from loguru import logger
        assert logger is not None
    
    result = selftest_check("LOGGING", _logging_test, "loguru available")
    results.append(result)
    if result == "PASS": passed += 1
    elif result == "FAIL": failed += 1

    # ── OPTIONAL ─────────────────────────────────────────────────────────
    print(f"{BOLD}OPTIONAL{NC}")

    # API (check if FastAPI is installed)
    def _api_test():
        try:
            import fastapi
            from api.router import create_app
            from config.loader import get_config
            cfg = get_config()
            app = create_app(version=cfg["app"]["version"], platform_info={"os_name": "linux"})
            assert app is not None
        except ImportError:
            raise ImportError("FastAPI not installed. Run: bash install_api.sh")
    
    try:
        import fastapi
        result = selftest_check("API", _api_test, "FastAPI available")
        results.append(result)
        if result == "PASS": passed += 1
        elif result == "FAIL": failed += 1
    except ImportError:
        result = selftest_check("API", _api_test, "Install with: bash install_api.sh", skip=True)
        results.append(result)
        skipped += 1

    # Scheduler (check if apscheduler is installed)
    def _scheduler_test():
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            from scheduler.service import SchedulerService
            scheduler = SchedulerService(timezone="UTC")
            assert scheduler is not None
        except ImportError:
            raise ImportError("apscheduler not installed. Run: bash install_api.sh")
    
    try:
        import apscheduler
        result = selftest_check("SCHEDULER", _scheduler_test, "apscheduler available")
        results.append(result)
        if result == "PASS": passed += 1
        elif result == "FAIL": failed += 1
    except ImportError:
        result = selftest_check("SCHEDULER", _scheduler_test, "Install with: bash install_api.sh", skip=True)
        results.append(result)
        skipped += 1

    # ── Summary ──────────────────────────────────────────────────────────
    total = passed + failed + skipped
    print("")
    if failed == 0:
        print(f"{GREEN}{BOLD}══════════════════════════════════════════════════{NC}")
        print(f"{GREEN}{BOLD}  PASS {passed} / SKIP {skipped} / FAIL {failed}              {NC}")
        print(f"{GREEN}{BOLD}══════════════════════════════════════════════════{NC}")
    else:
        print(f"{RED}{BOLD}══════════════════════════════════════════════════{NC}")
        print(f"{RED}{BOLD}  PASS {passed} / SKIP {skipped} / FAIL {failed}              {NC}")
        print(f"{RED}{BOLD}══════════════════════════════════════════════════{NC}")
        sys.exit(1)


async def cmd_serve(cfg: dict, platform: dict) -> None:
    """Start the FastAPI server."""
    try:
        from api.router import create_app
        import uvicorn
    except ImportError:
        logger.error("FastAPI not installed. Run: bash install_api.sh")
        sys.exit(1)

    host = cfg["api"]["host"]
    port = cfg["api"]["port"]

    logger.info("Starting FlowCore API on {}:{}", host, port)
    app = create_app(version=cfg["app"]["version"], platform_info=platform)

    if host == "0.0.0.0":
        logger.warning("API is bound to 0.0.0.0 — accessible from network")
        logger.warning("Consider setting api.host = 127.0.0.1 for security")

    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


async def cmd_run(cfg: dict, platform: dict) -> None:
    """Start the full application (API + scheduler + agents)."""
    try:
        import uvicorn
        from api.router import create_app
    except ImportError:
        logger.error("FastAPI not installed. Run: bash install_api.sh")
        sys.exit(1)

    logger.info("Starting FlowCore full application...")
    rt = FlowCoreRuntime(ROOT)
    await rt.start()
    app = create_app(version=cfg["app"]["version"], platform_info=platform)
    host = cfg["api"]["host"]
    port = cfg["api"]["port"]
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    try:
        await server.serve()
    except KeyboardInterrupt:
        pass
    finally:
        await rt.stop()
        logger.info("FlowCore stopped gracefully")


def cmd_health(cfg: dict) -> None:
    """Quick health check — core only."""
    print("")
    print(f"{BOLD}{CYAN}╔══════════════════════════════════════════════════╗{NC}")
    print(f"{BOLD}{CYAN}║         FlowCore Health Status                  ║{NC}")
    print(f"{BOLD}{CYAN}╚══════════════════════════════════════════════════╝{NC}")
    print("")

    print(f"  {GREEN}✓{NC} Core")
    print(f"  {GREEN}✓{NC} Config")
    print(f"  {GREEN}✓{NC} Runtime")

    try:
        import fastapi
        print(f"  {GREEN}✓{NC} API")
    except ImportError:
        print(f"  {YELLOW}○{NC} API (not installed)")

    try:
        import apscheduler
        print(f"  {GREEN}✓{NC} Scheduler")
    except ImportError:
        print(f"  {YELLOW}○{NC} Scheduler (not installed)")

    print("")
    print(f"{GREEN}{BOLD}Status: Healthy{NC}")
    print("")


def cmd_version(cfg: dict) -> None:
    """Print version info."""
    platform = detect_platform()
    print(f"FlowCore {cfg['app']['version']}")
    print(f"  Python: {platform['python_version']}")
    print(f"  Platform: {platform['os_name']}")
    print(f"  Termux: {platform['termux']}")
    print(f"  Android: {platform['android']}")


def cmd_chat(cfg: dict) -> None:
    """Interactive chat session."""
    print("")
    print(f"{BOLD}{CYAN}╔══════════════════════════════════════════════════╗{NC}")
    print(f"{BOLD}{CYAN}║         FlowCore Chat                           ║{NC}")
    print(f"{BOLD}{CYAN}╚══════════════════════════════════════════════════╝{NC}")
    print("")
    print("Type 'quit' to exit")
    print("")

    while True:
        try:
            user_input = input(f"{GREEN}You:{NC} ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit", "q"):
                print(f"{GREEN}Goodbye!{NC}")
                break

            logger.info(f"User input: {user_input}")
            print(f"{CYAN}FlowCore:{NC} Received: {user_input}")

        except (KeyboardInterrupt, EOFError):
            print(f"\n{GREEN}Goodbye!{NC}")
            break
        except Exception as e:
            logger.error(f"Chat error: {e}")
            print(f"{RED}Error: {e}{NC}")


def _get_memories_file() -> Path:
    """Get path to memories.json file."""
    home = Path.home()
    memories_dir = home / ".flowcore"
    memories_dir.mkdir(exist_ok=True)
    return memories_dir / "memories.json"


def _load_memories() -> list:
    """Load memories from JSON file."""
    file_path = _get_memories_file()
    if not file_path.exists():
        return []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Error loading memories: {e}")
        return []


def _save_memories(memories: list) -> None:
    """Save memories to JSON file."""
    file_path = _get_memories_file()
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(memories, f, indent=2, ensure_ascii=False)
    except IOError as e:
        logger.error(f"Error saving memories: {e}")


def cmd_remember(text: str) -> None:
    """Save a memory."""
    memories = _load_memories()
    memory = {
        "text": text,
        "timestamp": datetime.now().isoformat(),
        "topics": []
    }

    # Extract topics (words starting with #)
    for word in text.split():
        if word.startswith("#") and len(word) > 1:
            memory["topics"].append(word[1:].lower())

    memories.append(memory)
    _save_memories(memories)

    print(f"{GREEN}✓ Memory saved{NC}")
    if memory["topics"]:
        print(f"  Topics: {', '.join(memory['topics'])}")
    logger.info(f"Memory saved: {text}")


def cmd_recall(topic: str) -> None:
    """Recall memories by topic."""
    memories = _load_memories()

    if not memories:
        print(f"{YELLOW}No memories found{NC}")
        return

    topic_lower = topic.lower().lstrip("#")
    matching = [m for m in memories if topic_lower in [t.lower() for t in m.get("topics", [])]]

    if not matching:
        print(f"{YELLOW}No memories found for topic: {topic}{NC}")
        return

    print(f"\n{BOLD}{CYAN}Memories for: #{topic_lower}{NC}")
    for i, memory in enumerate(matching, 1):
        timestamp = memory.get("timestamp", "Unknown")
        text = memory.get("text", "")
        print(f"  {i}. {text}")
        print(f"     {YELLOW}└─ {timestamp[:10]}{NC}")


def cmd_memories() -> None:
    """List all memories."""
    memories = _load_memories()

    if not memories:
        print(f"{YELLOW}No memories yet. Use: python3 flowcore.py remember \"<text>\"{NC}")
        return

    print(f"\n{BOLD}{CYAN}╔══════════════════════════════════════════════════╗{NC}")
    print(f"{BOLD}{CYAN}║         FlowCore Memories                       ║{NC}")
    print(f"{BOLD}{CYAN}╚══════════════════════════════════════════════════╝{NC}\n")

    for i, memory in enumerate(memories, 1):
        text = memory.get("text", "")
        timestamp = memory.get("timestamp", "Unknown")
        topics = memory.get("topics", [])

        print(f"{GREEN}{i}.{NC} {text}")
        if topics:
            print(f"   {YELLOW}Topics:{NC} {', '.join([f'#{t}' for t in topics])}")
        print(f"   {YELLOW}Date:{NC} {timestamp[:10]}")
        print()


def main() -> None:
    """Main CLI handler."""
    parser = argparse.ArgumentParser(description="FlowCore CLI")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("serve", help="Start the API server")
    subparsers.add_parser("run", help="Start full application (API + scheduler + agents)")
    subparsers.add_parser("health", help="Quick health check")
    subparsers.add_parser("version", help="Print version info")
    subparsers.add_parser("selftest", help="Validate the entire installation")
    subparsers.add_parser("chat", help="Interactive chat session")

    remember_parser = subparsers.add_parser("remember", help="Save a memory")
    remember_parser.add_argument("text", nargs="+", help="Memory text (use #topic for tagging)")

    recall_parser = subparsers.add_parser("recall", help="Recall memories by topic")
    recall_parser.add_argument("topic", help="Topic to search (e.g., FlowCore)")

    subparsers.add_parser("memories", help="List all memories")

    args = parser.parse_args()
    cfg = get_config()
    platform = detect_platform()

    if args.command == "serve":
        asyncio.run(cmd_serve(cfg, platform))
    elif args.command == "run":
        asyncio.run(cmd_run(cfg, platform))
    elif args.command == "health":
        cmd_health(cfg)
    elif args.command == "version":
        cmd_version(cfg)
    elif args.command == "selftest":
        cmd_selftest()
    elif args.command == "chat":
        cmd_chat(cfg)
    elif args.command == "remember":
        text = " ".join(args.text)
        cmd_remember(text)
    elif args.command == "recall":
        cmd_recall(args.topic)
    elif args.command == "memories":
        cmd_memories()
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
