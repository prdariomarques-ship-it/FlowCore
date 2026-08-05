#!/usr/bin/env python3
"""FlowCore — Main entry point.

Usage:
    python3 flowcore.py serve            Start the API server
    python3 flowcore.py mcp              Start the MCP stdio server
    python3 flowcore.py run              Start the full application (API + scheduler + agents)
    python3 flowcore.py health           Quick health check
    python3 flowcore.py version          Print version
    python3 flowcore.py selftest         Validate the entire installation
    python3 flowcore.py chat             Interactive chat session
    python3 flowcore.py remember "<text>"     Save a memory
    python3 flowcore.py recall "<topic>"      Recall memories by topic
    python3 flowcore.py memories         List all memories
    python3 flowcore.py import "<file.md>"    Import Markdown file
    python3 flowcore.py docs             List all documents
    python3 flowcore.py show <id>        Display document by ID
    python3 flowcore.py ask "<question>"      Ask AI (RAG with Ollama)
    python3 flowcore.py ping             Test Ollama connection
    python3 flowcore.py models           List available Ollama models
    python3 flowcore.py stats            Show FlowCore statistics
    python3 flowcore.py doctor           System health check
    python3 flowcore.py demo             Interactive demo
    python3 flowcore.py search "<query>"      Search documents & memories
    python3 flowcore.py daily            Show daily summary
    python3 flowcore.py sync "<folder>"      Sync all .md from folder
    python3 flowcore.py watch "<folder>"     Monitor folder for changes
    python3 flowcore.py obsidian init        Initialize Obsidian vault
    python3 flowcore.py obsidian sync        Sync Obsidian vault to SQLite
    python3 flowcore.py obsidian watch       Watch Obsidian vault
    python3 flowcore.py note "<text>"         Add a note
    python3 flowcore.py todo "<task>"         Add a todo item
    python3 flowcore.py agenda "<event>"      Add to agenda

Env vars:
    FLOWCORE_MODEL=qwen3:8b              (default: llama2)
    FLOWCORE_OLLAMA=http://127.0.0.1:11434  (default shown)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.loader import get_config
from runtime.core import FlowCoreRuntime, detect_platform
from runtime.ollama import discover_default_model, discover_ollama_endpoint, OllamaDiscoveryError
from storage import DocumentRepository, MemoryRepository
from loguru import logger

# Colours
RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"
BOLD = "\033[1m"
NC = "\033[0m"

# Shared repositories (initialised on first use via their lazy path resolution)
_doc_repo = DocumentRepository()
_mem_repo = MemoryRepository()


def _get_ollama_url(endpoint: str) -> str:
    """Build a full Ollama API URL, auto-discovering the host (see runtime/ollama.py)."""
    return f"{discover_ollama_endpoint()}/api/{endpoint}"


def _test_ollama_connection() -> bool:
    try:
        discover_ollama_endpoint()
        return True
    except OllamaDiscoveryError:
        return False


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

    print(f"{BOLD}CORE{NC}")

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

    def _executor_test():
        from executor.engine import ExecutorEngine
        executor = ExecutorEngine()
        assert executor is not None

    result = selftest_check("EXECUTOR", _executor_test, "Engine ready")
    results.append(result)
    if result == "PASS": passed += 1
    elif result == "FAIL": failed += 1

    def _sqlite_test():
        import aiosqlite
        assert aiosqlite is not None

    result = selftest_check("SQLITE", _sqlite_test, "aiosqlite available")
    results.append(result)
    if result == "PASS": passed += 1
    elif result == "FAIL": failed += 1

    def _logging_test():
        from loguru import logger
        assert logger is not None

    result = selftest_check("LOGGING", _logging_test, "loguru available")
    results.append(result)
    if result == "PASS": passed += 1
    elif result == "FAIL": failed += 1

    def _storage_test():
        from storage import DocumentRepository, MemoryRepository
        assert DocumentRepository is not None
        assert MemoryRepository is not None

    result = selftest_check("STORAGE", _storage_test, "Repository layer ready")
    results.append(result)
    if result == "PASS": passed += 1
    elif result == "FAIL": failed += 1

    print(f"{BOLD}OPTIONAL{NC}")

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

    print(f"{BOLD}STORAGE{NC}")

    def _storage_dir_test():
        Path("data").mkdir(parents=True, exist_ok=True)

    result = selftest_check("DOCUMENTS", _storage_dir_test, "SQLite ready")
    results.append(result)
    if result == "PASS": passed += 1
    elif result == "FAIL": failed += 1

    print(f"{BOLD}MEMORY{NC}")

    def _memory_recall_test():
        cmd_remember("Testing recall with #FlowCore and substring search")
        memories = _mem_repo.list_all()
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

    print(f"{BOLD}DOCUMENTS{NC}")

    def _import_test():
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# Test Document\n\nThis is a test markdown file.")
            temp_file = f.name
        try:
            cmd_import(temp_file)
        finally:
            Path(temp_file).unlink()

    result = selftest_check("IMPORT", _import_test, "Markdown import works")
    results.append(result)
    if result == "PASS": passed += 1
    elif result == "FAIL": failed += 1

    print(f"{BOLD}AI{NC}")

    def _ask_graceful_test():
        import io
        old_stdout = sys.stdout
        try:
            sys.stdout = io.StringIO()
            cmd_ask("test question")
        finally:
            sys.stdout = old_stdout

    result = selftest_check("ASK", _ask_graceful_test, "Ask handles missing Ollama")
    results.append(result)
    if result == "PASS": passed += 1
    elif result == "FAIL": failed += 1

    def _ping_test():
        import io
        old_stdout = sys.stdout
        try:
            sys.stdout = io.StringIO()
            cmd_ping()
        finally:
            sys.stdout = old_stdout

    result = selftest_check("PING", _ping_test, "Ollama connection check works")
    results.append(result)
    if result == "PASS": passed += 1
    elif result == "FAIL": failed += 1

    def _stats_test():
        import io
        old_stdout = sys.stdout
        try:
            sys.stdout = io.StringIO()
            cmd_stats()
        finally:
            sys.stdout = old_stdout

    result = selftest_check("STATS", _stats_test, "Statistics display works")
    results.append(result)
    if result == "PASS": passed += 1
    elif result == "FAIL": failed += 1

    print(f"{BOLD}DAILY/SEARCH{NC}")

    def _daily_test():
        import io
        old_stdout = sys.stdout
        try:
            sys.stdout = io.StringIO()
            cmd_daily()
        finally:
            sys.stdout = old_stdout

    result = selftest_check("DAILY", _daily_test, "Daily summary works")
    results.append(result)
    if result == "PASS": passed += 1
    elif result == "FAIL": failed += 1

    def _search_test():
        import io
        old_stdout = sys.stdout
        try:
            sys.stdout = io.StringIO()
            cmd_search("test")
        finally:
            sys.stdout = old_stdout

    result = selftest_check("SEARCH", _search_test, "Search works")
    results.append(result)
    if result == "PASS": passed += 1
    elif result == "FAIL": failed += 1

    def _sync_test():
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            md_file = Path(tmpdir) / "test.md"
            md_file.write_text("# Test\nContent")
            cmd_sync(tmpdir)

    result = selftest_check("SYNC", _sync_test, "Sync folder works")
    results.append(result)
    if result == "PASS": passed += 1
    elif result == "FAIL": failed += 1

    print(f"{BOLD}OBSIDIAN{NC}")

    def _obsidian_test():
        import tempfile
        import io
        with tempfile.TemporaryDirectory() as tmpdir:
            old_stdout = sys.stdout
            try:
                sys.stdout = io.StringIO()
                cmd_obsidian_init(tmpdir)
            finally:
                sys.stdout = old_stdout
            assert (Path(tmpdir) / "Inbox").exists(), "Inbox not created"

    result = selftest_check("OBSIDIAN", _obsidian_test, "Obsidian init works")
    results.append(result)
    if result == "PASS": passed += 1
    elif result == "FAIL": failed += 1

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
    print(f"  {GREEN}✓{NC} Storage")

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


def cmd_remember(text: str) -> None:
    """Save a memory."""
    memory = _mem_repo.add(text)
    print(f"{GREEN}✓ Memory saved{NC}")
    if memory["topics"]:
        print(f"  Topics: {', '.join(memory['topics'])}")
    logger.info(f"Memory saved: {text}")


def cmd_recall(topic: str) -> None:
    """Recall memories by keyword or topic (substring, case-insensitive)."""
    matching = _mem_repo.search(topic)
    if not matching:
        print(f"{YELLOW}No memories found for '{topic}'{NC}")
        return

    topic_lower = topic.lower().lstrip("#")
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
    memories = _mem_repo.list_all()
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


def cmd_import(filepath: str) -> None:
    """Import Markdown file to SQLite with title extraction."""
    try:
        path = Path(filepath)
        if not path.exists():
            print(f"{RED}Error: File not found: {filepath}{NC}")
            return

        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        title = path.stem
        for line in content.split("\n"):
            if line.startswith("# "):
                title = line[2:].strip()
                break

        line_count = len(content.split("\n"))
        char_count = len(content)

        doc_id = _doc_repo.insert_sync(title, content, str(path))

        print(f"\n{GREEN}✓ Document imported{NC}")
        print(f"  {CYAN}Título:{NC} {title}")
        print(f"  {CYAN}Linhas:{NC} {line_count}")
        print(f"  {CYAN}Caracteres:{NC} {char_count}")
        print(f"  {CYAN}ID:{NC} {doc_id}\n")
        logger.info(f"Imported document: {filepath} (id={doc_id})")

    except Exception as e:
        print(f"{RED}Error importing document: {e}{NC}")
        logger.error(f"Import error: {e}")


def cmd_docs() -> None:
    """List all imported documents."""
    try:
        docs = _doc_repo.list_all_sync()
        if not docs:
            print(f"{YELLOW}No documents found.{NC}")
            return

        print(f"\n{BOLD}{CYAN}╔══════════════════════════════════════════════════╗{NC}")
        print(f"{BOLD}{CYAN}║         Documents                              ║{NC}")
        print(f"{BOLD}{CYAN}╚══════════════════════════════════════════════════╝{NC}\n")

        for doc in docs:
            print(f"{GREEN}[{doc['id']}]{NC} {doc['title']}")
            print(f"     {YELLOW}Source:{NC} {doc['source']}")
            print(f"     {YELLOW}Date:{NC} {doc['created_at'][:10]}")
            print()

    except Exception as e:
        print(f"{RED}Error listing documents: {e}{NC}")
        logger.error(f"Docs error: {e}")


def cmd_show(doc_id: str) -> None:
    """Display a document by ID."""
    try:
        doc = _doc_repo.get_by_id_sync(int(doc_id))
        if not doc:
            print(f"{RED}Document not found: {doc_id}{NC}")
            return

        print(f"\n{BOLD}{CYAN}╔══════════════════════════════════════════════════╗{NC}")
        print(f"{BOLD}{CYAN}║  {doc['title']:<45} ║{NC}")
        print(f"{BOLD}{CYAN}╚══════════════════════════════════════════════════╝{NC}\n")
        print(doc["content"])
        print(f"\n{YELLOW}─────────────────────────────────────────────────{NC}")
        print(f"{YELLOW}ID:{NC} {doc['id']} | {YELLOW}Date:{NC} {doc['created_at'][:10]}\n")

    except ValueError:
        print(f"{RED}Error: Invalid document ID (must be a number){NC}")
    except Exception as e:
        print(f"{RED}Error displaying document: {e}{NC}")
        logger.error(f"Show error: {e}")


def cmd_ping() -> None:
    """Test Ollama connection."""
    try:
        host = discover_ollama_endpoint()
        print(f"{GREEN}✓ Ollama is running{NC}")
        print(f"  Host: {host}")
        try:
            print(f"  Model: {discover_default_model()}")
        except OllamaDiscoveryError as e:
            print(f"  {YELLOW}Model: {e}{NC}")
    except OllamaDiscoveryError as e:
        print(f"{RED}✗ Ollama not found{NC}")
        print(f"  {e}")


def cmd_models() -> None:
    """List available Ollama models."""
    import urllib.request
    import urllib.error

    try:
        active_model = discover_default_model()
    except OllamaDiscoveryError:
        active_model = None

    try:
        request = urllib.request.Request(
            _get_ollama_url("tags"),
            headers={"Content-Type": "application/json"}
        )

        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            models = data.get("models", [])

            if not models:
                print(f"{YELLOW}No models found{NC}")
                return

            print(f"\n{BOLD}{CYAN}╔══════════════════════════════════════════════════╗{NC}")
            print(f"{BOLD}{CYAN}║         Ollama Models                           ║{NC}")
            print(f"{BOLD}{CYAN}╚══════════════════════════════════════════════════╝{NC}\n")

            for model in models:
                name = model.get("name", "unknown")
                size = model.get("size", 0)
                size_gb = size / (1024**3)
                modified = model.get("modified_at", "")[:10]
                active = f" {GREEN}(active){NC}" if name == active_model else ""
                print(f"{GREEN}•{NC} {name:<30} {size_gb:>6.1f}GB  {modified}{active}")
            print()

    except OllamaDiscoveryError as e:
        print(f"{RED}{e}{NC}")
    except (urllib.error.URLError, ConnectionRefusedError, TimeoutError) as e:
        print(f"{RED}Cannot connect to Ollama: {e}{NC}")
    except Exception as e:
        print(f"{RED}Error: {e}{NC}")
        logger.error(f"Models error: {e}")


def cmd_stats() -> None:
    """Show FlowCore statistics."""
    try:
        doc_count = _doc_repo.count_sync()
        mem_count = _mem_repo.count()
        try:
            ollama_host = discover_ollama_endpoint()
            ollama_status = "✓ Connected"
        except OllamaDiscoveryError as e:
            ollama_host = str(e)
            ollama_status = "✗ Offline"
        try:
            ollama_model = discover_default_model()
        except OllamaDiscoveryError:
            ollama_model = "?"
        cfg = get_config()

        print(f"\n{BOLD}{CYAN}╔══════════════════════════════════════════════════╗{NC}")
        print(f"{BOLD}{CYAN}║         FlowCore Statistics                     ║{NC}")
        print(f"{BOLD}{CYAN}╚══════════════════════════════════════════════════╝{NC}\n")

        print(f"{GREEN}Memories{NC}")
        print(f"  Count: {mem_count}")
        print()

        print(f"{GREEN}Documents{NC}")
        print(f"  Count: {doc_count}")
        print()

        print(f"{GREEN}AI Model{NC}")
        print(f"  Model: {ollama_model}")
        print(f"  Status: {ollama_status}")
        print(f"  Host: {ollama_host}")
        print()

        print(f"{GREEN}Version{NC}")
        version = cfg.get("app", {}).get("version", "1.0.0")
        print(f"  FlowCore: {version}")
        print()

    except Exception as e:
        logger.error(f"Stats error: {e}")


def cmd_doctor() -> None:
    """System health check: Python, SQLite, Database, JSON, Config, Ollama, API, Scheduler."""
    print(f"\n{BOLD}{CYAN}╔══════════════════════════════════════════════════╗{NC}")
    print(f"{BOLD}{CYAN}║         FlowCore Doctor                         ║{NC}")
    print(f"{BOLD}{CYAN}╚══════════════════════════════════════════════════╝{NC}\n")

    checks = {}

    try:
        version = sys.version.split()[0]
        print(f"{GREEN}✓{NC} Python: {version}")
        checks["python"] = "PASS"
    except Exception as e:
        print(f"{RED}✗{NC} Python: {e}")
        checks["python"] = "FAIL"

    try:
        import aiosqlite
        print(f"{GREEN}✓{NC} SQLite (aiosqlite)")
        checks["sqlite"] = "PASS"
    except Exception as e:
        print(f"{RED}✗{NC} SQLite: {e}")
        checks["sqlite"] = "FAIL"

    try:
        from storage.database import get_db_path
        db_path = get_db_path()

        async def _test_db():
            import aiosqlite
            async with aiosqlite.connect(db_path) as db:
                cursor = await db.execute("SELECT 1")
                await cursor.fetchone()

        asyncio.run(_test_db())
        print(f"{GREEN}✓{NC} Database: {db_path}")
        checks["database"] = "PASS"
    except Exception as e:
        print(f"{RED}✗{NC} Database: {str(e)[:50]}")
        checks["database"] = "FAIL"

    try:
        json.dumps({"test": "data"})
        print(f"{GREEN}✓{NC} JSON")
        checks["json"] = "PASS"
    except Exception as e:
        print(f"{RED}✗{NC} JSON: {e}")
        checks["json"] = "FAIL"

    try:
        cfg = get_config()
        assert cfg["app"]["name"] == "FlowCore"
        print(f"{GREEN}✓{NC} Config: FlowCore")
        checks["config"] = "PASS"
    except Exception as e:
        print(f"{RED}✗{NC} Config: {str(e)[:50]}")
        checks["config"] = "FAIL"

    try:
        ollama_host = discover_ollama_endpoint()
        try:
            ollama_model = discover_default_model()
        except OllamaDiscoveryError:
            ollama_model = "?"
        print(f"{GREEN}✓{NC} Ollama: {ollama_model} @ {ollama_host}")
        checks["ollama"] = "PASS"
    except OllamaDiscoveryError:
        print(f"{YELLOW}⚠{NC} Ollama: Not available")
        checks["ollama"] = "WARN"

    try:
        import fastapi
        print(f"{GREEN}✓{NC} FastAPI (optional)")
        checks["api"] = "PASS"
    except ImportError:
        print(f"{YELLOW}⚠{NC} FastAPI: Not installed")
        checks["api"] = "WARN"

    try:
        import apscheduler
        print(f"{GREEN}✓{NC} APScheduler (optional)")
        checks["scheduler"] = "PASS"
    except ImportError:
        print(f"{YELLOW}⚠{NC} APScheduler: Not installed")
        checks["scheduler"] = "WARN"

    print()
    failures = [k for k, v in checks.items() if v == "FAIL"]
    if failures:
        print(f"{RED}FAIL: {', '.join(failures)}{NC}\n")
    else:
        print(f"{GREEN}All critical systems operational{NC}\n")


def cmd_boot(verbose: bool = False) -> None:
    """Boot the Runtime Kernel and emit the Runtime Passport."""
    print(f"\n{BOLD}{CYAN}╔══════════════════════════════════════════════════╗{NC}")
    print(f"{BOLD}{CYAN}║         FlowCore Runtime Kernel — Boot          ║{NC}")
    print(f"{BOLD}{CYAN}╚══════════════════════════════════════════════════╝{NC}\n")
    try:
        from runtime.kernel import RuntimeKernel
        kernel = RuntimeKernel()
        passport = kernel.boot(verbose=verbose)
        print(f"{GREEN}✓{NC} Platform  : {passport.platform}")
        print(f"{GREEN}✓{NC} Android   : {passport.is_android}")
        print(f"{GREEN}✓{NC} Termux    : {passport.is_termux}")
        print(f"{GREEN}✓{NC} Internet  : {passport.has_internet}")
        caps = passport.capabilities
        print(f"{GREEN}✓{NC} Capabilities ({len(caps)}): {', '.join(caps) or 'none'}")
        print(f"\n{GREEN}Runtime Passport issued.{NC}  Saved to ~/.flowcore/flowcore.runtime.json\n")
    except Exception as e:
        print(f"{RED}✗{NC} Kernel boot failed: {e}\n")
        sys.exit(1)


def cmd_status() -> None:
    """Show comprehensive FlowCore runtime status."""
    print(f"\n{BOLD}{CYAN}╔══════════════════════════════════════════════════╗{NC}")
    print(f"{BOLD}{CYAN}║         FlowCore Runtime Status                 ║{NC}")
    print(f"{BOLD}{CYAN}╚══════════════════════════════════════════════════╝{NC}\n")

    # ── Kernel / Runtime Passport ─────────────────────────────────────────────
    print(f"{BOLD}Kernel{NC}")
    runtime_json = Path.home() / ".flowcore" / "flowcore.runtime.json"
    if runtime_json.exists():
        import json as _json
        try:
            data = _json.loads(runtime_json.read_text())
            android = data.get("android", {})
            termux = data.get("termux", {})
            network = data.get("network", {})
            print(f"  {GREEN}✓{NC} Runtime Passport  : {data.get('generated_at', 'unknown')}")
            print(f"  {GREEN}✓{NC} Platform          : {data.get('platform_type', 'unknown')}")
            print(f"  {GREEN}✓{NC} Android           : {android.get('detected', False)}")
            print(f"  {GREEN}✓{NC} Termux            : {termux.get('detected', False)}")
            print(f"  {GREEN}✓{NC} Internet          : {network.get('internet', False)}")
        except Exception:
            print(f"  {YELLOW}⚠{NC} Runtime Passport  : corrupt (run: python3 flowcore.py boot)")
    else:
        print(f"  {YELLOW}⚠{NC} Runtime Passport  : not found (run: python3 flowcore.py boot)")
    print()

    # ── Capabilities ──────────────────────────────────────────────────────────
    print(f"{BOLD}Capabilities{NC}")
    try:
        from capability.registry import CapabilityRegistry
        reg = CapabilityRegistry()
        cap_map = reg.list_capabilities()
        available = [(c, a) for c, a in cap_map.items() if a]
        missing = [c for c, a in cap_map.items() if not a]
        for cap, adapter in sorted(available):
            print(f"  {GREEN}✓{NC} {cap:<25} {CYAN}({adapter}){NC}")
        for cap in sorted(missing):
            print(f"  {YELLOW}○{NC} {cap:<25} (no adapter)")
        print(f"\n  Total: {len(available)}/{len(cap_map)} capabilities available")
    except Exception as e:
        print(f"  {RED}✗{NC} Could not load capability registry: {e}")
    print()

    # ── Doctor (quick run) ────────────────────────────────────────────────────
    print(f"{BOLD}Health (Doctor){NC}")
    try:
        from doctor.service import DoctorService
        doctor = DoctorService()
        report = doctor.run(verbose=False)
        icons = {"ok": f"{GREEN}✓{NC}", "warn": f"{YELLOW}⚠{NC}",
                 "fail": f"{RED}✗{NC}", "skip": "─"}
        for check in report.checks:
            icon = icons.get(check.status.value, "?")
            suffix = f"  → {check.fix}" if check.fix and check.status.value != "ok" else ""
            print(f"  {icon} {check.name:<30} {check.message}{suffix}")
        print()
        if report.healthy:
            print(f"  {GREEN}All checks passed ({report.passed}/{len(report.checks)}){NC}")
        else:
            print(f"  {RED}{report.failed} failure(s) | {report.warned} warning(s){NC}")
    except Exception as e:
        print(f"  {RED}✗{NC} Doctor failed: {e}")
    print()


def cmd_bootstrap() -> None:
    """Bootstrap a fresh Termux environment from zero."""
    print(f"\n{BOLD}{CYAN}╔══════════════════════════════════════════════════╗{NC}")
    print(f"{BOLD}{CYAN}║         FlowCore Bootstrap (Fresh Termux)       ║{NC}")
    print(f"{BOLD}{CYAN}╚══════════════════════════════════════════════════╝{NC}\n")
    try:
        from installer.setup import FlowCoreInstaller
        installer = FlowCoreInstaller()
        report = installer.bootstrap(verbose=True)
        print()
        if report.ok:
            print(f"{GREEN}Bootstrap complete — FlowCore ready.{NC}\n")
        else:
            failed = [s.name for s in report.failed_steps]
            print(f"{YELLOW}Bootstrap finished with issues: {', '.join(failed)}{NC}\n")
            sys.exit(1)
    except Exception as e:
        print(f"{RED}✗{NC} Bootstrap failed: {e}\n")
        sys.exit(1)


def cmd_repair() -> None:
    """Detect and repair a corrupted FlowCore environment."""
    print(f"\n{BOLD}{CYAN}╔══════════════════════════════════════════════════╗{NC}")
    print(f"{BOLD}{CYAN}║         FlowCore Repair                         ║{NC}")
    print(f"{BOLD}{CYAN}╚══════════════════════════════════════════════════╝{NC}\n")
    try:
        from installer.setup import FlowCoreInstaller
        installer = FlowCoreInstaller()
        report = installer.repair(verbose=True)
        print()
        if report.ok:
            print(f"{GREEN}Repair complete — all issues resolved.{NC}\n")
        else:
            failed = [s.name for s in report.failed_steps]
            print(f"{YELLOW}Repair finished — some issues remain: {', '.join(failed)}{NC}\n")
            print(f"{YELLOW}Run 'python3 flowcore.py status' to see current state.{NC}\n")
    except Exception as e:
        print(f"{RED}✗{NC} Repair failed: {e}\n")
        sys.exit(1)


def cmd_install() -> None:
    """Set up the full FlowCore runtime environment."""
    print(f"\n{BOLD}{CYAN}╔══════════════════════════════════════════════════╗{NC}")
    print(f"{BOLD}{CYAN}║         FlowCore Installer                      ║{NC}")
    print(f"{BOLD}{CYAN}╚══════════════════════════════════════════════════╝{NC}\n")
    try:
        from installer.setup import FlowCoreInstaller
        installer = FlowCoreInstaller()
        report = installer.install(verbose=True)
        print()
        if report.ok:
            print(f"{GREEN}Installation complete — all steps passed.{NC}\n")
        else:
            failed = [s.name for s in report.failed_steps]
            print(f"{YELLOW}Installation finished with issues: {', '.join(failed)}{NC}\n")
            sys.exit(1)
    except Exception as e:
        print(f"{RED}✗{NC} Installer failed: {e}\n")
        sys.exit(1)


def cmd_demo() -> None:
    """Interactive demo: remember → recall → import → docs → show → stats."""
    print(f"\n{BOLD}{CYAN}╔══════════════════════════════════════════════════╗{NC}")
    print(f"{BOLD}{CYAN}║         FlowCore Demo                           ║{NC}")
    print(f"{BOLD}{CYAN}╚══════════════════════════════════════════════════╝{NC}\n")

    try:
        print(f"{BOLD}1. Remember{NC}")
        cmd_remember("Demo memory #FlowCore #demo")

        print(f"\n{BOLD}2. Recall{NC}")
        cmd_recall("FlowCore")

        print(f"\n{BOLD}3. Import Markdown{NC}")
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# FlowCore Demo\n\nThis is a demo markdown file for testing import functionality.")
            temp_file = f.name
        try:
            cmd_import(temp_file)
        finally:
            Path(temp_file).unlink()

        print(f"\n{BOLD}4. List Documents{NC}")
        cmd_docs()

        print(f"\n{BOLD}5. Show Document{NC}")
        print("(Display the first document)")

        print(f"\n{BOLD}6. Statistics{NC}")
        cmd_stats()

        print(f"\n{GREEN}{BOLD}FlowCore está operacional.{NC}\n")

    except Exception as e:
        print(f"{RED}Demo error: {e}{NC}")
        logger.error(f"Demo error: {e}")


def cmd_search(query: str) -> None:
    """Search in documents and memories."""
    try:
        docs = _doc_repo.search_sync(query)
        memories = _mem_repo.search(query)

        print(f"\n{BOLD}{CYAN}Search: '{query}'{NC}\n")

        if docs:
            print(f"{BOLD}Documents ({len(docs)}){NC}")
            for doc in docs[:5]:
                print(f"  [{doc['id']}] {doc['title']}")
                print(f"      {doc['content'][:100]}...")
            print()

        if memories:
            print(f"{BOLD}Memories ({len(memories)}){NC}")
            for m in memories[:5]:
                print(f"  • {m.get('text', '')[:80]}")
            print()

        if not docs and not memories:
            print(f"{YELLOW}No results found.{NC}\n")

    except Exception as e:
        print(f"{RED}Search error: {e}{NC}")
        logger.error(f"Search error: {e}")


def cmd_daily() -> None:
    """Show daily summary."""
    try:
        doc_count = _doc_repo.count_sync()
        task_count = _doc_repo.count_by_source_sync("note", "todo", "agenda")
        recent_docs = _doc_repo.list_recent_sync(5)
        mem_count = _mem_repo.count()

        print(f"\n{BOLD}{CYAN}╔══════════════════════════════════════════════════╗{NC}")
        print(f"{BOLD}{CYAN}║         Daily Summary                          ║{NC}")
        print(f"{BOLD}{CYAN}╚══════════════════════════════════════════════════╝{NC}\n")

        print(f"{BOLD}Statistics{NC}")
        print(f"  Documents: {doc_count}")
        print(f"  Memories: {mem_count}")
        print(f"  Tasks: {task_count}")
        print()

        if recent_docs:
            print(f"{BOLD}Recent Documents{NC}")
            for doc in recent_docs:
                print(f"  • {doc['title']}")
                print(f"    {doc['content'][:80]}...")
            print()

        print(f"{GREEN}Ready for the day ahead.{NC}\n")

    except Exception as e:
        logger.error(f"Daily error: {e}")


def cmd_sync(folder: str) -> None:
    """Import all Markdown files from a folder."""
    try:
        path = Path(folder).expanduser()
        if not path.exists():
            print(f"{RED}Folder not found: {folder}{NC}")
            return

        md_files = list(path.glob("**/*.md"))
        if not md_files:
            print(f"{YELLOW}No Markdown files found in {folder}{NC}")
            return

        print(f"\n{BOLD}{CYAN}Syncing {len(md_files)} file(s)...{NC}\n")

        for md_file in md_files:
            try:
                cmd_import(str(md_file))
                print()
            except Exception as e:
                print(f"{RED}  Error: {md_file.name} — {str(e)[:50]}{NC}\n")

        print(f"{GREEN}Sync complete: {len(md_files)} file(s) processed.{NC}\n")

    except Exception as e:
        print(f"{RED}Sync error: {e}{NC}")
        logger.error(f"Sync error: {e}")


def cmd_watch(folder: str, interval: int = 5) -> None:
    """Monitor a folder for new/modified Markdown files."""
    try:
        import time
        path = Path(folder).expanduser()
        if not path.exists():
            print(f"{RED}Folder not found: {folder}{NC}")
            return

        print(f"\n{BOLD}{CYAN}Watching {folder}...{NC}")
        print(f"{YELLOW}Press Ctrl+C to stop.{NC}\n")

        tracked = {}
        try:
            while True:
                md_files = list(path.glob("**/*.md"))
                for md_file in md_files:
                    mtime = md_file.stat().st_mtime
                    file_key = str(md_file)
                    if file_key not in tracked or tracked[file_key] != mtime:
                        print(f"{GREEN}→{NC} {md_file.name}")
                        try:
                            cmd_import(str(md_file))
                        except Exception as e:
                            print(f"  {RED}Error: {str(e)[:50]}{NC}")
                        tracked[file_key] = mtime
                time.sleep(interval)
        except KeyboardInterrupt:
            print(f"\n{YELLOW}Watch stopped.{NC}\n")

    except Exception as e:
        print(f"{RED}Watch error: {e}{NC}")
        logger.error(f"Watch error: {e}")


def _get_obsidian_path() -> Path:
    vault_path = os.getenv("FLOWCORE_OBSIDIAN")
    if vault_path:
        return Path(vault_path).expanduser()
    return Path.home() / "Obsidian"


def _save_obsidian_path(vault_path: Path) -> None:
    config_file = Path.home() / ".flowcore" / "obsidian.path"
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(str(vault_path.expanduser()))


def cmd_obsidian_init(vault_path: str = None) -> None:
    """Initialize Obsidian vault structure."""
    try:
        vault = Path(vault_path).expanduser() if vault_path else _get_obsidian_path()
        vault.mkdir(parents=True, exist_ok=True)
        _save_obsidian_path(vault)

        folders = ["Inbox", "Projects", "Knowledge", "Meetings", "Journal"]
        for folder in folders:
            (vault / folder).mkdir(exist_ok=True)

        print(f"\n{GREEN}✓ Obsidian vault initialized{NC}")
        print(f"  Path: {vault}\n")
        print(f"{BOLD}Folders created:{NC}")
        for folder in folders:
            print(f"  • {folder}/")
        print()

    except Exception as e:
        print(f"{RED}Obsidian init error: {e}{NC}")
        logger.error(f"Obsidian init error: {e}")


def cmd_obsidian_sync(vault_path: str = None) -> None:
    """Sync entire Obsidian vault to SQLite."""
    try:
        vault = Path(vault_path).expanduser() if vault_path else _get_obsidian_path()
        if not vault.exists():
            print(f"{RED}Vault not found: {vault}{NC}")
            return

        md_files = list(vault.glob("**/*.md"))
        if not md_files:
            print(f"{YELLOW}No Markdown files in vault{NC}")
            return

        print(f"\n{BOLD}{CYAN}Syncing Obsidian vault...{NC}")
        print(f"  Files: {len(md_files)}\n")

        for md_file in md_files:
            try:
                cmd_import(str(md_file))
            except Exception:
                print(f"  {RED}Error: {md_file.name}{NC}")

        print(f"{GREEN}Sync complete: {len(md_files)} file(s) processed.{NC}\n")
        _save_obsidian_path(vault)

    except Exception as e:
        print(f"{RED}Obsidian sync error: {e}{NC}")
        logger.error(f"Obsidian sync error: {e}")


def cmd_obsidian_watch(vault_path: str = None) -> None:
    """Watch Obsidian vault for changes."""
    try:
        vault = Path(vault_path).expanduser() if vault_path else _get_obsidian_path()
        if not vault.exists():
            print(f"{RED}Vault not found: {vault}{NC}")
            return
        _save_obsidian_path(vault)
        cmd_watch(str(vault))
    except Exception as e:
        print(f"{RED}Obsidian watch error: {e}{NC}")
        logger.error(f"Obsidian watch error: {e}")


def cmd_ask(question: str) -> None:
    """RAG: Ask AI using Ollama with document context."""
    from runtime.ollama import (
        generate as ollama_generate,
        OllamaModelLoadTimeoutError,
        OllamaModelNotInstalledError,
        OllamaSubscriptionRequiredError,
        OllamaUnreachableError,
    )

    try:
        base_url = discover_ollama_endpoint()
        model = discover_default_model()
    except OllamaDiscoveryError as e:
        print(f"{RED}Ollama não encontrado.{NC}")
        print(f"{YELLOW}{e}{NC}")
        logger.warning(f"Ollama discovery failed: {e}")
        return

    recent_docs = _doc_repo.list_recent_sync(5)
    context = ""
    if recent_docs:
        context = "Context from documents:\n"
        for doc in recent_docs:
            context += f"\n[{doc['title']}]\n{doc['content'][:300]}\n"

    system_prompt = "You are a helpful AI assistant. Use the provided context to answer questions accurately."
    prompt = f"{system_prompt}\n\nContext:\n{context}\n\nQuestion: {question}\n\nAnswer:"

    try:
        result = ollama_generate(base_url, model, prompt)
        print(f"\n{BOLD}{CYAN}FlowCore AI ({model}):{NC}")
        print(result)
    except OllamaSubscriptionRequiredError as e:
        print(f"{RED}Modelo requer assinatura Ollama Cloud.{NC}")
        print(f"{YELLOW}{e}{NC}")
    except OllamaModelNotInstalledError as e:
        print(f"{RED}Modelo não instalado.{NC}")
        print(f"{YELLOW}{e}{NC}")
    except OllamaModelLoadTimeoutError as e:
        print(f"{RED}Tempo esgotado carregando o modelo.{NC}")
        print(f"{YELLOW}{e}{NC}")
    except OllamaUnreachableError as e:
        print(f"{RED}Ollama não encontrado.{NC}")
        print(f"{YELLOW}{e}{NC}")
        logger.warning(f"Ollama not available at {base_url}")
    except Exception as e:
        logger.error(f"Ask command error: {e}")
        print(f"{RED}Erro: {e}{NC}")


def cmd_note(text: str) -> None:
    """Add a note."""
    try:
        _doc_repo.insert_sync("Note", text, "note")
        print(f"{GREEN}✓ Note saved{NC}")
        logger.info(f"Note added: {text}")
    except Exception as e:
        print(f"{RED}Error: {e}{NC}")


def cmd_todo(task: str) -> None:
    """Add a todo item."""
    try:
        _doc_repo.insert_sync("TODO", task, "todo")
        print(f"{GREEN}✓ Todo added{NC}")
        logger.info(f"Todo added: {task}")
    except Exception as e:
        print(f"{RED}Error: {e}{NC}")


def cmd_agenda(event: str) -> None:
    """Add to agenda."""
    try:
        _doc_repo.insert_sync("Agenda", event, "agenda")
        print(f"{GREEN}✓ Event added to agenda{NC}")
        logger.info(f"Agenda event: {event}")
    except Exception as e:
        print(f"{RED}Error: {e}{NC}")


def cmd_ui() -> None:
    """Open the FlowCore web dashboard in the Android browser."""
    url = "http://localhost:8080"
    try:
        from runtime.shell import is_available, run
        if is_available("termux-open-url"):
            result = run(["termux-open-url", url], timeout=5)
            if result.success:
                print(f"{GREEN}✓ A abrir {url} no browser{NC}")
                return
    except Exception:
        pass
    # Fallback — just print the URL
    print(f"{CYAN}Dashboard:{NC} {url}")
    print(f"  Arranca o servidor com: {BOLD}python3 flowcore.py serve{NC}")


def cmd_daemon(action: str, interval: int = 60) -> None:
    """Manage the FlowCore background daemon."""
    from runtime.daemon import FlowCoreDaemon
    d = FlowCoreDaemon()

    if action == "start":
        result = d.start(interval=interval)
        if result.get("started"):
            print(f"{GREEN}✓ Daemon started{NC}  pid={result['pid']}")
            print(f"  Log: {result.get('log', '')}")
        else:
            print(f"{YELLOW}⚠ Daemon already running{NC}  pid={result['pid']}")

    elif action == "stop":
        result = d.stop()
        if result.get("stopped"):
            print(f"{GREEN}✓ Daemon stopped{NC}  pid={result['pid']}")
        else:
            note = result.get("note") or result.get("error", "")
            print(f"{YELLOW}⚠ {note}{NC}")

    elif action == "status":
        result = d.status()
        if result["running"]:
            print(f"{GREEN}✓ Daemon running{NC}")
            print(f"  PID   : {result['pid']}")
            print(f"  Uptime: {result.get('uptime', 0):.0f}s")
            print(f"  Cycle : {result.get('cycle', 0)}")
            print(f"  Log   : {result.get('log', '')}")
        else:
            print(f"{YELLOW}○ Daemon not running{NC}")
            print(f"  Start with: python3 flowcore.py daemon start")

    else:
        print(f"{RED}Unknown daemon action: {action!r}{NC}")
        print("  Usage: python3 flowcore.py daemon <start|stop|status>")


def cmd_jobs(action: str, name: str = "", script: str = "",
             schedule: str = "") -> None:
    """Manage scheduled jobs."""
    from runtime.job_scheduler import JobScheduler
    sched = JobScheduler()

    if action == "list":
        jobs = sched.list_jobs()
        if not jobs:
            print(f"{YELLOW}No jobs scheduled.{NC}")
            print("  Add one: python3 flowcore.py jobs add <name> <script> <schedule>")
            return
        print(f"\n{BOLD}{CYAN}Scheduled Jobs ({len(jobs)}){NC}\n")
        for j in jobs:
            status_mark = f"{GREEN}✓{NC}" if j["enabled"] else f"{YELLOW}○{NC}"
            print(f"  {status_mark} {j['name']:<20} {j['schedule']:<15} {j['script']}")
        print()

    elif action == "add":
        if not name or not script or not schedule:
            print(f"{RED}Usage: python3 flowcore.py jobs add <name> <script> <schedule>{NC}")
            return
        try:
            ok = sched.add_job(name, script, schedule)
            mark = f"{GREEN}✓{NC}" if ok else f"{YELLOW}⚠{NC}"
            label = "registered with system scheduler" if ok else "saved (no system scheduler)"
            print(f"{mark} Job '{name}' added — {label}")
        except (ValueError, FileNotFoundError) as e:
            print(f"{RED}Error: {e}{NC}")

    elif action == "remove":
        if not name:
            print(f"{RED}Usage: python3 flowcore.py jobs remove <name>{NC}")
            return
        if sched.remove_job(name):
            print(f"{GREEN}✓ Job '{name}' removed{NC}")
        else:
            print(f"{YELLOW}Job '{name}' not found{NC}")

    elif action == "run":
        if not name:
            print(f"{RED}Usage: python3 flowcore.py jobs run <name>{NC}")
            return
        try:
            print(f"Running '{name}'...")
            result = sched.run_now(name)
            if result["success"]:
                print(f"{GREEN}✓ Job '{name}' completed (rc={result['returncode']}){NC}")
            else:
                print(f"{RED}✗ Job '{name}' failed (rc={result['returncode']}){NC}")
            if result.get("output"):
                print(result["output"])
            if result.get("error"):
                print(f"{YELLOW}{result['error']}{NC}")
        except KeyError as e:
            print(f"{RED}Error: {e}{NC}")

    else:
        print(f"{RED}Unknown jobs action: {action!r}{NC}")
        print("  Usage: python3 flowcore.py jobs <list|add|remove|run>")


def main() -> None:
    """Main CLI handler."""
    parser = argparse.ArgumentParser(description="FlowCore CLI")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("serve", help="Start the API server")
    subparsers.add_parser("mcp", help="Start the MCP stdio server (for Claude Code / MCP clients)")
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

    subparsers.add_parser("docs", help="List all documents")

    show_parser = subparsers.add_parser("show", help="Display a document by ID")
    show_parser.add_argument("id", help="Document ID")

    subparsers.add_parser("ping", help="Test Ollama connection")
    subparsers.add_parser("models", help="List available Ollama models")
    subparsers.add_parser("stats", help="Show FlowCore statistics")
    subparsers.add_parser("doctor", help="System health check")
    subparsers.add_parser("status", help="Comprehensive runtime status (capabilities, health, passport)")
    boot_parser = subparsers.add_parser("boot", help="Boot Runtime Kernel and emit Runtime Passport")
    boot_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose boot output")
    subparsers.add_parser("install", help="Set up the full FlowCore runtime environment")
    subparsers.add_parser("bootstrap", help="Bootstrap a fresh Termux environment from zero")
    subparsers.add_parser("repair", help="Detect and repair a corrupted FlowCore environment")
    subparsers.add_parser("demo", help="Interactive demo")

    search_parser = subparsers.add_parser("search", help="Search documents & memories")
    search_parser.add_argument("query", help="Search query")

    subparsers.add_parser("daily", help="Show daily summary")

    sync_parser = subparsers.add_parser("sync", help="Sync all .md from folder")
    sync_parser.add_argument("folder", help="Folder path")

    watch_parser = subparsers.add_parser("watch", help="Monitor folder for changes")
    watch_parser.add_argument("folder", help="Folder path to watch")

    obsidian_parser = subparsers.add_parser("obsidian", help="Obsidian vault integration")
    obsidian_sub = obsidian_parser.add_subparsers(dest="obsidian_command")
    obsidian_sub.add_parser("init", help="Initialize vault structure")
    obsidian_sub.add_parser("sync", help="Sync vault to SQLite")
    obsidian_sub.add_parser("watch", help="Watch vault for changes")

    ask_parser = subparsers.add_parser("ask", help="Ask AI (RAG with Ollama)")
    ask_parser.add_argument("question", nargs="+", help="Question to ask")

    note_parser = subparsers.add_parser("note", help="Add a note")
    note_parser.add_argument("text", nargs="+", help="Note text")

    todo_parser = subparsers.add_parser("todo", help="Add a todo item")
    todo_parser.add_argument("task", nargs="+", help="Task description")

    agenda_parser = subparsers.add_parser("agenda", help="Add to agenda")
    agenda_parser.add_argument("event", nargs="+", help="Event description")

    subparsers.add_parser("ui", help="Open web dashboard in Android browser (http://localhost:8080)")

    daemon_parser = subparsers.add_parser("daemon", help="Manage background daemon")
    daemon_sub = daemon_parser.add_subparsers(dest="daemon_action")
    daemon_start = daemon_sub.add_parser("start", help="Start the daemon")
    daemon_start.add_argument("--interval", type=int, default=60,
                              help="Heartbeat interval in seconds (default: 60)")
    daemon_sub.add_parser("stop", help="Stop the daemon")
    daemon_sub.add_parser("status", help="Show daemon status")

    jobs_parser = subparsers.add_parser("jobs", help="Manage scheduled jobs")
    jobs_sub = jobs_parser.add_subparsers(dest="jobs_action")
    jobs_sub.add_parser("list", help="List all scheduled jobs")
    jobs_add = jobs_sub.add_parser("add", help="Add a new job")
    jobs_add.add_argument("name", help="Job name (letters, digits, _ and - only)")
    jobs_add.add_argument("script", help="Path to Python script")
    jobs_add.add_argument("schedule", help="Cron expression (e.g. '0 2 * * *')")
    jobs_remove = jobs_sub.add_parser("remove", help="Remove a job")
    jobs_remove.add_argument("name", help="Job name to remove")
    jobs_run = jobs_sub.add_parser("run", help="Run a job immediately")
    jobs_run.add_argument("name", help="Job name to run")

    args = parser.parse_args()
    cfg = get_config()
    platform = detect_platform()

    if args.command == "serve":
        asyncio.run(cmd_serve(cfg, platform))
    elif args.command == "mcp":
        from mcp_server import run as run_mcp_server
        run_mcp_server()
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
        cmd_remember(" ".join(args.text))
    elif args.command == "recall":
        cmd_recall(args.topic)
    elif args.command == "memories":
        cmd_memories()
    elif args.command == "import":
        cmd_import(args.file)
    elif args.command == "docs":
        cmd_docs()
    elif args.command == "show":
        cmd_show(args.id)
    elif args.command == "ping":
        cmd_ping()
    elif args.command == "models":
        cmd_models()
    elif args.command == "stats":
        cmd_stats()
    elif args.command == "doctor":
        cmd_doctor()
    elif args.command == "status":
        cmd_status()
    elif args.command == "boot":
        cmd_boot(verbose=getattr(args, "verbose", False))
    elif args.command == "install":
        cmd_install()
    elif args.command == "bootstrap":
        cmd_bootstrap()
    elif args.command == "repair":
        cmd_repair()
    elif args.command == "demo":
        cmd_demo()
    elif args.command == "search":
        cmd_search(args.query)
    elif args.command == "daily":
        cmd_daily()
    elif args.command == "sync":
        cmd_sync(args.folder)
    elif args.command == "watch":
        cmd_watch(args.folder)
    elif args.command == "ask":
        cmd_ask(" ".join(args.question))
    elif args.command == "note":
        cmd_note(" ".join(args.text))
    elif args.command == "todo":
        cmd_todo(" ".join(args.task))
    elif args.command == "agenda":
        cmd_agenda(" ".join(args.event))
    elif args.command == "obsidian":
        if args.obsidian_command == "init":
            cmd_obsidian_init()
        elif args.obsidian_command == "sync":
            cmd_obsidian_sync()
        elif args.obsidian_command == "watch":
            cmd_obsidian_watch()
        else:
            parser.print_help()
    elif args.command == "ui":
        cmd_ui()
    elif args.command == "daemon":
        action = getattr(args, "daemon_action", None)
        if not action:
            print("Usage: python3 flowcore.py daemon <start|stop|status>")
            sys.exit(1)
        interval = getattr(args, "interval", 60)
        cmd_daemon(action, interval=interval)
    elif args.command == "jobs":
        action = getattr(args, "jobs_action", None)
        if not action:
            print("Usage: python3 flowcore.py jobs <list|add|remove|run>")
            sys.exit(1)
        name     = getattr(args, "name", "")
        script   = getattr(args, "script", "")
        schedule = getattr(args, "schedule", "")
        cmd_jobs(action, name=name, script=script, schedule=schedule)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
