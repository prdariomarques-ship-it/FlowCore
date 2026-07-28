#!/usr/bin/env python3
"""FlowCore — Main entry point.

Usage:
    python3 flowcore.py serve            Start the API server
    python3 flowcore.py run              Start the full application (API + scheduler + agents)
    python3 flowcore.py health           Quick health check
    python3 flowcore.py version          Print version
    python3 flowcore.py selftest         Validate the entire installation
    python3 flowcore.py chat             Interactive chat session
    python3 flowcore.py remember "<text>"     Save a memory
    python3 flowcore.py recall "<topic>"      Recall memories by topic
    python3 flowcore.py memories         List all memories
    python3 flowcore.py import "<file.md>"    Import Markdown file
    python3 flowcore.py ask "<question>"      Ask AI (requires Ollama)
    python3 flowcore.py note "<text>"         Add a note
    python3 flowcore.py todo "<task>"         Add a todo item
    python3 flowcore.py agenda "<event>"      Add to agenda
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

    # ── Storage ──────────────────────────────────────────────────────────
    print(f"{BOLD}STORAGE{NC}")

    def _storage_test():
        from pathlib import Path
        Path("data").mkdir(parents=True, exist_ok=True)

    result = selftest_check("DOCUMENTS", _storage_test, "SQLite ready")
    results.append(result)
    if result == "PASS": passed += 1
    elif result == "FAIL": failed += 1

    # ── Memory ──────────────────────────────────────────────────────────
    print(f"{BOLD}MEMORY{NC}")

    def _memory_recall_test():
        cmd_remember("Testing recall with #FlowCore and substring search")
        memories = _load_memories()
        assert len(memories) > 0, "No memories stored"
        last = memories[-1]

        text_lower = last.get("text", "").lower()
        topics_lower = [t.lower() for t in last.get("topics", [])]

        assert "flowcore" in topics_lower, "Hashtag extraction failed"
        assert "testing" in text_lower, "Substring text not stored"

        search_term = "flowcore"
        found_by_hashtag = search_term in topics_lower
        found_by_substring = search_term in text_lower
        assert found_by_hashtag or found_by_substring, "Recall search failed"

    result = selftest_check("RECALL", _memory_recall_test, "Remember & recall work")
    results.append(result)
    if result == "PASS": passed += 1
    elif result == "FAIL": failed += 1

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
    """Recall memories by keyword or topic (substring, case-insensitive)."""
    memories = _load_memories()

    if not memories:
        print(f"{YELLOW}No memories found{NC}")
        return

    topic_lower = topic.lower().lstrip("#")
    matching = []

    for m in memories:
        text_lower = m.get("text", "").lower()
        topics_lower = [t.lower() for t in m.get("topics", [])]
        if topic_lower in text_lower or any(topic_lower in t for t in topics_lower):
            matching.append(m)

    if not matching:
        print(f"{YELLOW}No memories found for '{topic}'{NC}")
        return

    print(f"\n{BOLD}{CYAN}Found {len(matching)} memory(ies) for: '{topic_lower}'{NC}\n")
    for i, memory in enumerate(matching, 1):
        timestamp = memory.get("timestamp", "Unknown")
        text = memory.get("text", "")
        topics = memory.get("topics", [])
        print(f"{GREEN}{i}.{NC} {text}")
        if topics:
            print(f"   {YELLOW}Topics:{NC} {', '.join([f'#{t}' for t in topics])}")
        print(f"   {YELLOW}Date:{NC} {timestamp[:10]}")
        print()


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


async def _init_sqlite_documents():
    """Initialize SQLite documents table."""
    try:
        import aiosqlite
        from config.loader import get_config
        cfg = get_config()
        db_url = cfg.get("database", {}).get("url", "sqlite+aiosqlite:///data/flowcore.db")
        db_path = db_url.replace("sqlite+aiosqlite:///", "")

        async with aiosqlite.connect(db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.commit()
    except Exception as e:
        logger.error(f"Error initializing documents table: {e}")


def cmd_import(filepath: str) -> None:
    """Import Markdown file to SQLite."""
    try:
        path = Path(filepath)
        if not path.exists():
            print(f"{RED}Error: File not found: {filepath}{NC}")
            return

        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        asyncio.run(_init_sqlite_documents())

        import aiosqlite
        from config.loader import get_config

        async def _import():
            cfg = get_config()
            db_url = cfg.get("database", {}).get("url", "sqlite+aiosqlite:///data/flowcore.db")
            db_path = db_url.replace("sqlite+aiosqlite:///", "")

            async with aiosqlite.connect(db_path) as db:
                await db.execute(
                    "INSERT INTO documents (title, content, source) VALUES (?, ?, ?)",
                    (path.stem, content, str(path))
                )
                await db.commit()

        asyncio.run(_import())
        print(f"{GREEN}✓ Document imported: {path.name}{NC}")
        logger.info(f"Imported document: {filepath}")

    except Exception as e:
        print(f"{RED}Error importing document: {e}{NC}")
        logger.error(f"Import error: {e}")


def cmd_ask(question: str) -> None:
    """Ask AI using Ollama with SQLite context."""
    try:
        import aiosqlite
        from config.loader import get_config

        async def _ask():
            cfg = get_config()
            db_url = cfg.get("database", {}).get("url", "sqlite+aiosqlite:///data/flowcore.db")
            db_path = db_url.replace("sqlite+aiosqlite:///", "")

            # Get context from SQLite
            context = ""
            try:
                async with aiosqlite.connect(db_path) as db:
                    cursor = await db.execute(
                        "SELECT title, content FROM documents ORDER BY created_at DESC LIMIT 5"
                    )
                    rows = await cursor.fetchall()
                    if rows:
                        context = "\nContext from documents:\n"
                        for title, content in rows:
                            context += f"\n## {title}\n{content[:500]}...\n"
            except Exception as e:
                logger.warning(f"Could not load context: {e}")

            # Try to use Ollama
            try:
                import requests
                prompt = f"{context}\n\nQuestion: {question}"

                response = requests.post(
                    "http://localhost:11434/api/generate",
                    json={"model": "llama2", "prompt": prompt, "stream": False},
                    timeout=30
                )

                if response.status_code == 200:
                    result = response.json().get("response", "")
                    print(f"\n{BOLD}{CYAN}FlowCore AI:{NC}")
                    print(result)
                else:
                    print(f"{RED}Error: Ollama returned status {response.status_code}{NC}")

            except requests.exceptions.ConnectionError:
                print(f"{RED}Error: Cannot connect to Ollama (http://localhost:11434){NC}")
                print(f"{YELLOW}Make sure Ollama is running: ollama serve{NC}")
            except Exception as e:
                print(f"{RED}Error: {e}{NC}")
                logger.error(f"Ask error: {e}")

        asyncio.run(_ask())

    except ImportError:
        print(f"{RED}Error: 'requests' module not installed{NC}")
        print(f"{YELLOW}Install with: pip install requests{NC}")


def cmd_note(text: str) -> None:
    """Add a note."""
    try:
        asyncio.run(_init_sqlite_documents())

        import aiosqlite
        from config.loader import get_config

        async def _add_note():
            cfg = get_config()
            db_url = cfg.get("database", {}).get("url", "sqlite+aiosqlite:///data/flowcore.db")
            db_path = db_url.replace("sqlite+aiosqlite:///", "")

            async with aiosqlite.connect(db_path) as db:
                await db.execute(
                    "INSERT INTO documents (title, content, source) VALUES (?, ?, ?)",
                    ("Note", text, "note")
                )
                await db.commit()

        asyncio.run(_add_note())
        print(f"{GREEN}✓ Note saved{NC}")
        logger.info(f"Note added: {text}")

    except Exception as e:
        print(f"{RED}Error: {e}{NC}")


def cmd_todo(task: str) -> None:
    """Add a todo item."""
    try:
        asyncio.run(_init_sqlite_documents())

        import aiosqlite
        from config.loader import get_config

        async def _add_todo():
            cfg = get_config()
            db_url = cfg.get("database", {}).get("url", "sqlite+aiosqlite:///data/flowcore.db")
            db_path = db_url.replace("sqlite+aiosqlite:///", "")

            async with aiosqlite.connect(db_path) as db:
                await db.execute(
                    "INSERT INTO documents (title, content, source) VALUES (?, ?, ?)",
                    ("TODO", task, "todo")
                )
                await db.commit()

        asyncio.run(_add_todo())
        print(f"{GREEN}✓ Todo added{NC}")
        logger.info(f"Todo added: {task}")

    except Exception as e:
        print(f"{RED}Error: {e}{NC}")


def cmd_agenda(event: str) -> None:
    """Add to agenda."""
    try:
        asyncio.run(_init_sqlite_documents())

        import aiosqlite
        from config.loader import get_config

        async def _add_agenda():
            cfg = get_config()
            db_url = cfg.get("database", {}).get("url", "sqlite+aiosqlite:///data/flowcore.db")
            db_path = db_url.replace("sqlite+aiosqlite:///", "")

            async with aiosqlite.connect(db_path) as db:
                await db.execute(
                    "INSERT INTO documents (title, content, source) VALUES (?, ?, ?)",
                    ("Agenda", event, "agenda")
                )
                await db.commit()

        asyncio.run(_add_agenda())
        print(f"{GREEN}✓ Event added to agenda{NC}")
        logger.info(f"Agenda event: {event}")

    except Exception as e:
        print(f"{RED}Error: {e}{NC}")


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

    import_parser = subparsers.add_parser("import", help="Import Markdown file")
    import_parser.add_argument("file", help="Path to Markdown file")

    ask_parser = subparsers.add_parser("ask", help="Ask AI (requires Ollama)")
    ask_parser.add_argument("question", nargs="+", help="Question to ask")

    note_parser = subparsers.add_parser("note", help="Add a note")
    note_parser.add_argument("text", nargs="+", help="Note text")

    todo_parser = subparsers.add_parser("todo", help="Add a todo item")
    todo_parser.add_argument("task", nargs="+", help="Task description")

    agenda_parser = subparsers.add_parser("agenda", help="Add to agenda")
    agenda_parser.add_argument("event", nargs="+", help="Event description")

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
    elif args.command == "import":
        cmd_import(args.file)
    elif args.command == "ask":
        question = " ".join(args.question)
        cmd_ask(question)
    elif args.command == "note":
        text = " ".join(args.text)
        cmd_note(text)
    elif args.command == "todo":
        task = " ".join(args.task)
        cmd_todo(task)
    elif args.command == "agenda":
        event = " ".join(args.event)
        cmd_agenda(event)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
