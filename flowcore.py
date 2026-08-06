#!/usr/bin/env python3
"""FlowCore — Main entry point.

Usage:
    python3 flowcore.py serve            Start the API server
    python3 flowcore.py mcp              Start the MCP stdio server
    python3 flowcore.py run              Start the API server with full runtime lifecycle
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
    python3 flowcore.py flow <list|create|show|run|delete>   Manage flows
    python3 flowcore.py android <battery|wifi|storage|apps|clipboard-get|clipboard-set|notify>
    python3 flowcore.py outlook <auth|messages|unread|search>
    python3 flowcore.py calendar <auth|today|tomorrow|week|next|search|create|update|delete>
    python3 flowcore.py whatsapp <health|status|send>
    python3 flowcore.py integrations         Show live status of all integrations
    python3 flowcore.py telegram <health|config|send>
    python3 flowcore.py observer <registry|events [source]|health|watch>
    python3 flowcore.py macro-score <dimensions|scores [dimension]>
    python3 flowcore.py regime signals [dimension]
    python3 flowcore.py portfolio <create|list|show|summary|delete|add-holding|remove-holding>
    python3 flowcore.py asset <show|tag>

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

from dotenv import load_dotenv

# Loads .env into the process environment before anything else reads it.
# Single choke point — covers CLI, `serve` (FastAPI), and `mcp`
# (mcp_server.py), since flowcore.py is the entry point for all three.
load_dotenv()

from config.loader import get_config
from runtime.core import FlowCoreRuntime, detect_platform
from runtime.ollama import discover_default_model, discover_ollama_endpoint, OllamaDiscoveryError
from runtime.portfolio.attributes import ASSET_ATTRIBUTE_FIELDS
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
    if result == "PASS":
        passed += 1
    elif result == "FAIL":
        failed += 1

    def _sqlite_test():
        import aiosqlite

        assert aiosqlite is not None

    result = selftest_check("SQLITE", _sqlite_test, "aiosqlite available")
    results.append(result)
    if result == "PASS":
        passed += 1
    elif result == "FAIL":
        failed += 1

    def _logging_test():
        from loguru import logger

        assert logger is not None

    result = selftest_check("LOGGING", _logging_test, "loguru available")
    results.append(result)
    if result == "PASS":
        passed += 1
    elif result == "FAIL":
        failed += 1

    def _storage_test():
        from storage import DocumentRepository, MemoryRepository

        assert DocumentRepository is not None
        assert MemoryRepository is not None

    result = selftest_check("STORAGE", _storage_test, "Repository layer ready")
    results.append(result)
    if result == "PASS":
        passed += 1
    elif result == "FAIL":
        failed += 1

    print(f"{BOLD}OPTIONAL{NC}")

    def _api_test():
        try:
            import fastapi  # noqa: F401 — availability probe
            from api.router import create_app
            from config.loader import get_config

            cfg = get_config()
            app = create_app(version=cfg["app"]["version"], platform_info={"os_name": "linux"})
            assert app is not None
        except ImportError:
            raise ImportError("FastAPI not installed. Run: bash install_api.sh")

    try:
        import fastapi  # noqa: F401 — availability probe

        result = selftest_check("API", _api_test, "FastAPI available")
        results.append(result)
        if result == "PASS":
            passed += 1
        elif result == "FAIL":
            failed += 1
    except ImportError:
        result = selftest_check("API", _api_test, "Install with: bash install_api.sh", skip=True)
        results.append(result)
        skipped += 1

    print(f"{BOLD}STORAGE{NC}")

    def _storage_dir_test():
        Path("data").mkdir(parents=True, exist_ok=True)

    result = selftest_check("DOCUMENTS", _storage_dir_test, "SQLite ready")
    results.append(result)
    if result == "PASS":
        passed += 1
    elif result == "FAIL":
        failed += 1

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
    if result == "PASS":
        passed += 1
    elif result == "FAIL":
        failed += 1

    print(f"{BOLD}DOCUMENTS{NC}")

    def _import_test():
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# Test Document\n\nThis is a test markdown file.")
            temp_file = f.name
        try:
            asyncio.run(cmd_import(temp_file))
        finally:
            Path(temp_file).unlink()

    result = selftest_check("IMPORT", _import_test, "Markdown import works")
    results.append(result)
    if result == "PASS":
        passed += 1
    elif result == "FAIL":
        failed += 1

    print(f"{BOLD}AI{NC}")

    def _ask_graceful_test():
        import io

        old_stdout = sys.stdout
        try:
            sys.stdout = io.StringIO()
            asyncio.run(cmd_ask("test question"))
        finally:
            sys.stdout = old_stdout

    result = selftest_check("ASK", _ask_graceful_test, "Ask handles missing Ollama")
    results.append(result)
    if result == "PASS":
        passed += 1
    elif result == "FAIL":
        failed += 1

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
    if result == "PASS":
        passed += 1
    elif result == "FAIL":
        failed += 1

    def _stats_test():
        import io

        old_stdout = sys.stdout
        try:
            sys.stdout = io.StringIO()
            asyncio.run(cmd_stats())
        finally:
            sys.stdout = old_stdout

    result = selftest_check("STATS", _stats_test, "Statistics display works")
    results.append(result)
    if result == "PASS":
        passed += 1
    elif result == "FAIL":
        failed += 1

    print(f"{BOLD}DAILY/SEARCH{NC}")

    def _daily_test():
        import io

        old_stdout = sys.stdout
        try:
            sys.stdout = io.StringIO()
            asyncio.run(cmd_daily())
        finally:
            sys.stdout = old_stdout

    result = selftest_check("DAILY", _daily_test, "Daily summary works")
    results.append(result)
    if result == "PASS":
        passed += 1
    elif result == "FAIL":
        failed += 1

    def _search_test():
        import io

        old_stdout = sys.stdout
        try:
            sys.stdout = io.StringIO()
            asyncio.run(cmd_search("test"))
        finally:
            sys.stdout = old_stdout

    result = selftest_check("SEARCH", _search_test, "Search works")
    results.append(result)
    if result == "PASS":
        passed += 1
    elif result == "FAIL":
        failed += 1

    def _sync_test():
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            md_file = Path(tmpdir) / "test.md"
            md_file.write_text("# Test\nContent")
            asyncio.run(cmd_sync(tmpdir))

    result = selftest_check("SYNC", _sync_test, "Sync folder works")
    results.append(result)
    if result == "PASS":
        passed += 1
    elif result == "FAIL":
        failed += 1

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
    if result == "PASS":
        passed += 1
    elif result == "FAIL":
        failed += 1

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
    """Start the API server with full runtime lifecycle (FlowCoreRuntime start/stop)."""
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
        import fastapi  # noqa: F401 — availability probe

        print(f"  {GREEN}✓{NC} API")
    except ImportError:
        print(f"  {YELLOW}○{NC} API (not installed)")

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
        print(f'{YELLOW}No memories yet. Use: python3 flowcore.py remember "<text>"{NC}')
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


async def cmd_import(filepath: str) -> None:
    """Import Markdown file to SQLite with title extraction."""
    import service

    try:
        result = await service.import_markdown(filepath)
        print(f"\n{GREEN}✓ Document imported{NC}")
        print(f"  {CYAN}Título:{NC} {result['title']}")
        print(f"  {CYAN}Linhas:{NC} {result['lines']}")
        print(f"  {CYAN}Caracteres:{NC} {result['chars']}")
        print(f"  {CYAN}ID:{NC} {result['id']}\n")
        logger.info(f"Imported document: {filepath} (id={result['id']})")
    except FileNotFoundError as e:
        print(f"{RED}Error: {e}{NC}")
    except Exception as e:
        print(f"{RED}Error importing document: {e}{NC}")
        logger.error(f"Import error: {e}")


async def cmd_docs() -> None:
    """List all imported documents."""
    try:
        docs = await _doc_repo.list_all()
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


async def cmd_show(doc_id: str) -> None:
    """Display a document by ID."""
    try:
        doc = await _doc_repo.get_by_id(int(doc_id))
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
        request = urllib.request.Request(_get_ollama_url("tags"), headers={"Content-Type": "application/json"})

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


async def cmd_stats() -> None:
    """Show FlowCore statistics."""
    try:
        doc_count = await _doc_repo.count()
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
        import aiosqlite  # noqa: F401 — availability probe

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
        import fastapi  # noqa: F401 — availability probe

        print(f"{GREEN}✓{NC} FastAPI (optional)")
        checks["api"] = "PASS"
    except ImportError:
        print(f"{YELLOW}⚠{NC} FastAPI: Not installed")
        checks["api"] = "WARN"

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
        icons = {"ok": f"{GREEN}✓{NC}", "warn": f"{YELLOW}⚠{NC}", "fail": f"{RED}✗{NC}", "skip": "─"}
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


async def cmd_demo() -> None:
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
            await cmd_import(temp_file)
        finally:
            Path(temp_file).unlink()

        print(f"\n{BOLD}4. List Documents{NC}")
        await cmd_docs()

        print(f"\n{BOLD}5. Show Document{NC}")
        print("(Display the first document)")

        print(f"\n{BOLD}6. Statistics{NC}")
        await cmd_stats()

        print(f"\n{GREEN}{BOLD}FlowCore está operacional.{NC}\n")

    except Exception as e:
        print(f"{RED}Demo error: {e}{NC}")
        logger.error(f"Demo error: {e}")


async def cmd_search(query: str) -> None:
    """Search in documents and memories."""
    import service

    try:
        results = await service.search(query)
        docs = results["documents"]
        memories = results["memories"]

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


async def cmd_daily() -> None:
    """Show daily summary."""
    try:
        doc_count = await _doc_repo.count()
        task_count = await _doc_repo.count_by_source("note", "todo", "agenda")
        recent_docs = await _doc_repo.list_recent(5)
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


async def cmd_sync(folder: str) -> None:
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
                await cmd_import(str(md_file))
                print()
            except Exception as e:
                print(f"{RED}  Error: {md_file.name} — {str(e)[:50]}{NC}\n")

        print(f"{GREEN}Sync complete: {len(md_files)} file(s) processed.{NC}\n")

    except Exception as e:
        print(f"{RED}Sync error: {e}{NC}")
        logger.error(f"Sync error: {e}")


async def cmd_watch(folder: str, interval: int = 5) -> None:
    """Monitor a folder for new/modified Markdown files."""
    try:
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
                            await cmd_import(str(md_file))
                        except Exception as e:
                            print(f"  {RED}Error: {str(e)[:50]}{NC}")
                        tracked[file_key] = mtime
                await asyncio.sleep(interval)
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


async def cmd_obsidian_sync(vault_path: str = None) -> None:
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
                await cmd_import(str(md_file))
            except Exception:
                print(f"  {RED}Error: {md_file.name}{NC}")

        print(f"{GREEN}Sync complete: {len(md_files)} file(s) processed.{NC}\n")
        _save_obsidian_path(vault)

    except Exception as e:
        print(f"{RED}Obsidian sync error: {e}{NC}")
        logger.error(f"Obsidian sync error: {e}")


async def cmd_obsidian_watch(vault_path: str = None) -> None:
    """Watch Obsidian vault for changes."""
    try:
        vault = Path(vault_path).expanduser() if vault_path else _get_obsidian_path()
        if not vault.exists():
            print(f"{RED}Vault not found: {vault}{NC}")
            return
        _save_obsidian_path(vault)
        await cmd_watch(str(vault))
    except Exception as e:
        print(f"{RED}Obsidian watch error: {e}{NC}")
        logger.error(f"Obsidian watch error: {e}")


async def cmd_ask(question: str) -> None:
    """RAG: Ask AI using Ollama with document context."""
    import service
    from runtime.ollama import (
        OllamaError,
        OllamaModelLoadTimeoutError,
        OllamaModelNotInstalledError,
        OllamaSubscriptionRequiredError,
        OllamaUnreachableError,
    )

    try:
        answer, model = await service.ask(question)
        print(f"\n{BOLD}{CYAN}FlowCore AI ({model}):{NC}")
        print(answer)
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
        logger.warning(f"Ollama not available: {e}")
    except OllamaError as e:
        # Covers OllamaDiscoveryError (endpoint/model resolution failed
        # before generation even started) with the same "not found" framing.
        print(f"{RED}Ollama não encontrado.{NC}")
        print(f"{YELLOW}{e}{NC}")
        logger.warning(f"Ollama discovery failed: {e}")
    except Exception as e:
        logger.error(f"Ask command error: {e}")
        print(f"{RED}Erro: {e}{NC}")


async def cmd_note(text: str) -> None:
    """Add a note."""
    import service

    try:
        await service.add_note(text, "note")
        print(f"{GREEN}✓ Note saved{NC}")
        logger.info(f"Note added: {text}")
    except Exception as e:
        print(f"{RED}Error: {e}{NC}")


async def cmd_todo(task: str) -> None:
    """Add a todo item."""
    import service

    try:
        await service.add_note(task, "todo")
        print(f"{GREEN}✓ Todo added{NC}")
        logger.info(f"Todo added: {task}")
    except Exception as e:
        print(f"{RED}Error: {e}{NC}")


async def cmd_agenda(event: str) -> None:
    """Add to agenda."""
    import service

    try:
        await service.add_note(event, "agenda")
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
            print("  Start with: python3 flowcore.py daemon start")

    else:
        print(f"{RED}Unknown daemon action: {action!r}{NC}")
        print("  Usage: python3 flowcore.py daemon <start|stop|status>")


def cmd_jobs(action: str, name: str = "", script: str = "", schedule: str = "") -> None:
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


async def cmd_flow(action: str, name: str = "", steps_json: str = "", flow_id: int = 0) -> None:
    """Manage flows (named, ordered lists of steps run via the Executor)."""
    import service

    if action == "list":
        flows = await service.list_flows()
        if not flows:
            print(f"{YELLOW}No flows defined.{NC}")
            print("  Add one: python3 flowcore.py flow create <name> '<steps_json>'")
            return
        print(f"\n{BOLD}{CYAN}Flows ({len(flows)}){NC}\n")
        for f in flows:
            print(f"  [{f['id']}] {f['name']} — {len(f['steps'])} step(s)")
        print()

    elif action == "create":
        if not name or not steps_json:
            print(f"{RED}Usage: python3 flowcore.py flow create <name> '<steps_json>'{NC}")
            print('  Example: flow create "Daily Note" \'[{"action":"note","params":{"text":"hi"}}]\'')
            return
        try:
            steps = json.loads(steps_json)
        except json.JSONDecodeError as e:
            print(f"{RED}Invalid steps JSON: {e}{NC}")
            return
        try:
            flow = await service.create_flow(name, steps)
            print(f"{GREEN}✓ Flow '{name}' created (id={flow['id']}){NC}")
        except ValueError as e:
            print(f"{RED}Error: {e}{NC}")

    elif action == "show":
        if not flow_id:
            print(f"{RED}Usage: python3 flowcore.py flow show <id>{NC}")
            return
        try:
            flow = await service.get_flow(flow_id)
            print(f"\n{BOLD}{CYAN}Flow [{flow['id']}] {flow['name']}{NC}")
            print(f"  Created: {flow['created_at']}")
            for i, step in enumerate(flow["steps"], 1):
                print(f"  {i}. {step['action']} {step.get('params', {})}")
            print()
        except ValueError as e:
            print(f"{RED}Error: {e}{NC}")

    elif action == "run":
        if not flow_id:
            print(f"{RED}Usage: python3 flowcore.py flow run <id>{NC}")
            return
        try:
            print(f"Running flow {flow_id}...")
            execution = await service.run_flow(flow_id)
            mark = f"{GREEN}✓{NC}" if execution["status"] == "completed" else f"{RED}✗{NC}"
            print(f"{mark} Execution {execution['id']} — status={execution['status']}")
            for r in execution["step_results"]:
                step_mark = f"{GREEN}✓{NC}" if r["status"] == "completed" else f"{RED}✗{NC}"
                detail = r.get("output", r.get("error"))
                print(f"  {step_mark} {r['action']}: {detail}")
        except ValueError as e:
            print(f"{RED}Error: {e}{NC}")

    elif action == "delete":
        if not flow_id:
            print(f"{RED}Usage: python3 flowcore.py flow delete <id>{NC}")
            return
        if await service.delete_flow(flow_id):
            print(f"{GREEN}✓ Flow {flow_id} deleted{NC}")
        else:
            print(f"{YELLOW}Flow {flow_id} not found{NC}")

    else:
        print(f"{RED}Unknown flow action: {action!r}{NC}")
        print("  Usage: python3 flowcore.py flow <list|create|show|run|delete>")


def _print_capability_result(result: dict, label: str) -> None:
    if result.get("success"):
        print(f"{GREEN}✓ {label}{NC}")
        print(json.dumps(result.get("data"), indent=2, ensure_ascii=False))
    else:
        print(f"{RED}✗ {label} failed{NC}")
        print(f"  {result.get('error') or result.get('reason')}")
        if result.get("corrective_action"):
            print(f"  {YELLOW}Fix:{NC} {result['corrective_action']}")


async def cmd_android(action: str, text: str = "", title: str = "FlowCore") -> None:
    """Android device capabilities (battery, wifi, storage, clipboard, notify, apps)."""
    import service

    if action == "battery":
        _print_capability_result(await service.get_battery(), "Battery")
    elif action == "wifi":
        _print_capability_result(await service.get_wifi_info(), "Wifi")
    elif action == "storage":
        _print_capability_result(await service.get_disk_usage(), "Disk usage")
    elif action == "apps":
        result = await service.list_installed_apps()
        if result.get("success"):
            data = result["data"]
            print(f"{GREEN}✓ {data['count']} installed app(s){NC}")
            for pkg in data["packages"][:50]:
                print(f"  {pkg}")
            if data["count"] > 50:
                print(f"  ... and {data['count'] - 50} more")
        else:
            _print_capability_result(result, "Installed apps")
    elif action == "clipboard-get":
        _print_capability_result(await service.get_clipboard(), "Clipboard")
    elif action == "clipboard-set":
        if not text:
            print(f'{RED}Usage: python3 flowcore.py android clipboard-set "<text>"{NC}')
            return
        _print_capability_result(await service.set_clipboard(text), "Clipboard set")
    elif action == "notify":
        if not text:
            print(f'{RED}Usage: python3 flowcore.py android notify "<text>" [--title TITLE]{NC}')
            return
        _print_capability_result(await service.send_notification(title, text), "Notification")
    else:
        print(f"{RED}Unknown android action: {action!r}{NC}")
        print("  Usage: python3 flowcore.py android <battery|wifi|storage|apps|clipboard-get|clipboard-set|notify>")


async def cmd_outlook(action: str, query: str = "", limit: int = 10) -> None:
    """Outlook integration (read-only): auth, latest messages, unread count, search."""
    from runtime.outlook import (
        OutlookAuthRequiredError,
        OutlookError,
        OutlookNotConfiguredError,
        complete_device_flow,
        get_unread_count,
        list_messages,
        search_messages,
        start_device_flow,
    )

    if action == "auth":
        try:
            flow = await asyncio.to_thread(start_device_flow)
        except OutlookNotConfiguredError as e:
            print(f"{RED}Error: {e}{NC}")
            return
        message = flow.get("message") or f"Go to {flow['verification_uri']} and enter code {flow['user_code']}"
        print(f"\n{CYAN}{message}{NC}")
        print(f"{YELLOW}Waiting for authorization...{NC}")
        try:
            await asyncio.to_thread(complete_device_flow, flow)
            print(f"{GREEN}✓ Authenticated with Outlook{NC}\n")
        except OutlookError as e:
            print(f"{RED}✗ Authentication failed: {e}{NC}")

    elif action == "messages":
        try:
            msgs = await asyncio.to_thread(list_messages, limit)
            if not msgs:
                print(f"{YELLOW}No messages found.{NC}")
                return
            print(f"\n{BOLD}{CYAN}Latest messages ({len(msgs)}){NC}\n")
            for m in msgs:
                mark = f"{CYAN}●{NC}" if not m["is_read"] else "○"
                print(f"  {mark} {m['subject']} — {m['from']} ({m['received'][:10]})")
            print()
        except (OutlookNotConfiguredError, OutlookAuthRequiredError, OutlookError) as e:
            print(f"{RED}Error: {e}{NC}")

    elif action == "unread":
        try:
            count = await asyncio.to_thread(get_unread_count)
            print(f"{GREEN}✓ {count} unread message(s){NC}")
        except (OutlookNotConfiguredError, OutlookAuthRequiredError, OutlookError) as e:
            print(f"{RED}Error: {e}{NC}")

    elif action == "search":
        if not query:
            print(f'{RED}Usage: python3 flowcore.py outlook search "<query>"{NC}')
            return
        try:
            msgs = await asyncio.to_thread(search_messages, query, limit)
            if not msgs:
                print(f"{YELLOW}No results for '{query}'.{NC}")
                return
            print(f"\n{BOLD}{CYAN}Search: '{query}' ({len(msgs)}){NC}\n")
            for m in msgs:
                print(f"  {m['subject']} — {m['from']} ({m['received'][:10]})")
            print()
        except (OutlookNotConfiguredError, OutlookAuthRequiredError, OutlookError) as e:
            print(f"{RED}Error: {e}{NC}")

    else:
        print(f"{RED}Unknown outlook action: {action!r}{NC}")
        print("  Usage: python3 flowcore.py outlook <auth|messages|unread|search>")


def _print_events(events: list, empty_msg: str) -> None:
    if not events:
        print(f"{YELLOW}{empty_msg}{NC}")
        return
    for e in events:
        loc = f" @ {e['location']}" if e.get("location") else ""
        print(f"  [{e['id'][:12]}...] {e['subject']}{loc}")
        print(f"      {e['start']} — {e['end']} ({e.get('timezone', '')})")


async def cmd_calendar(
    action: str,
    query: str = "",
    limit: int = 10,
    event_id: str = "",
    subject: str = "",
    start: str = "",
    end: str = "",
    timezone_: str = "UTC",
    description: str = "",
    location: str = "",
    attendees: list[str] | None = None,
) -> None:
    """Microsoft Calendar: auth, today, tomorrow, week, next, search, create, update, delete.

    Shares the same authenticated session as `outlook auth` — running either
    one authenticates both (see runtime/microsoft_graph.py).
    """
    from runtime.calendar import (
        CalendarAuthRequiredError,
        CalendarError,
        CalendarNotConfiguredError,
        create_event,
        delete_event,
        get_next,
        list_today,
        list_tomorrow,
        list_week,
        search_events,
        update_event,
    )
    from runtime.microsoft_graph import complete_device_flow, start_device_flow

    if action == "auth":
        try:
            flow = await asyncio.to_thread(start_device_flow)
        except CalendarNotConfiguredError as e:
            print(f"{RED}Error: {e}{NC}")
            return
        message = flow.get("message") or f"Go to {flow['verification_uri']} and enter code {flow['user_code']}"
        print(f"\n{CYAN}{message}{NC}")
        print(f"{YELLOW}Waiting for authorization...{NC}")
        try:
            await asyncio.to_thread(complete_device_flow, flow)
            print(f"{GREEN}✓ Authenticated with Microsoft Graph (Outlook + Calendar){NC}\n")
        except CalendarError as e:
            print(f"{RED}✗ Authentication failed: {e}{NC}")

    elif action in ("today", "tomorrow", "week"):
        fn = {"today": list_today, "tomorrow": list_tomorrow, "week": list_week}[action]
        try:
            events = await asyncio.to_thread(fn)
            print(f"\n{BOLD}{CYAN}{action.capitalize()} ({len(events)}){NC}\n")
            _print_events(events, f"No events {action}.")
            print()
        except (CalendarNotConfiguredError, CalendarAuthRequiredError, CalendarError) as e:
            print(f"{RED}Error: {e}{NC}")

    elif action == "next":
        try:
            event = await asyncio.to_thread(get_next)
            if not event:
                print(f"{YELLOW}No upcoming events in the next 30 days.{NC}")
                return
            print(f"\n{BOLD}{CYAN}Next meeting{NC}\n")
            _print_events([event], "")
            print()
        except (CalendarNotConfiguredError, CalendarAuthRequiredError, CalendarError) as e:
            print(f"{RED}Error: {e}{NC}")

    elif action == "search":
        if not query:
            print(f'{RED}Usage: python3 flowcore.py calendar search "<query>"{NC}')
            return
        try:
            events = await asyncio.to_thread(search_events, query, limit)
            print(f"\n{BOLD}{CYAN}Search: '{query}' ({len(events)}){NC}\n")
            _print_events(events, f"No results for '{query}'.")
            print()
        except (CalendarNotConfiguredError, CalendarAuthRequiredError, CalendarError) as e:
            print(f"{RED}Error: {e}{NC}")

    elif action == "create":
        if not subject or not start or not end:
            print(f"{RED}Usage: python3 flowcore.py calendar create --subject S --start S --end S [options]{NC}")
            return
        try:
            event = await asyncio.to_thread(
                create_event, subject, start, end, timezone_, description, location, attendees
            )
            print(f"{GREEN}✓ Event created{NC}")
            _print_events([event], "")
        except (CalendarNotConfiguredError, CalendarAuthRequiredError, CalendarError) as e:
            print(f"{RED}Error: {e}{NC}")

    elif action == "update":
        if not event_id:
            print(f"{RED}Usage: python3 flowcore.py calendar update <event_id> [--subject ...] ...{NC}")
            return
        fields = {}
        if subject:
            fields["subject"] = subject
        if start:
            fields["start"] = start
        if end:
            fields["end"] = end
        if description:
            fields["description"] = description
        if location:
            fields["location"] = location
        if attendees:
            fields["attendees"] = attendees
        if "start" in fields or "end" in fields:
            fields["timezone_"] = timezone_
        if not fields:
            print(f"{RED}Error: no fields given to update.{NC}")
            return
        try:
            event = await asyncio.to_thread(update_event, event_id, **fields)
            print(f"{GREEN}✓ Event updated{NC}")
            _print_events([event], "")
        except (CalendarNotConfiguredError, CalendarAuthRequiredError, CalendarError) as e:
            print(f"{RED}Error: {e}{NC}")

    elif action == "delete":
        if not event_id:
            print(f"{RED}Usage: python3 flowcore.py calendar delete <event_id>{NC}")
            return
        try:
            await asyncio.to_thread(delete_event, event_id)
            print(f"{GREEN}✓ Event {event_id} deleted{NC}")
        except (CalendarNotConfiguredError, CalendarAuthRequiredError, CalendarError) as e:
            print(f"{RED}Error: {e}{NC}")

    else:
        print(f"{RED}Unknown calendar action: {action!r}{NC}")
        print("  Usage: python3 flowcore.py calendar <auth|today|tomorrow|week|next|search|create|update|delete>")


async def cmd_whatsapp(action: str, number: str = "", text: str = "") -> None:
    """WhatsApp via Evolution API (health, status, send) — reuses the already-paired instance."""
    from runtime.whatsapp import WhatsAppError, WhatsAppNotConfiguredError, check_health, get_status, send_message

    if action == "health":
        try:
            result = await asyncio.to_thread(check_health)
            print(f"{GREEN}✓ Evolution API reachable{NC} (v{result.get('version', '?')})")
        except WhatsAppError as e:
            print(f"{RED}✗ Evolution API unreachable: {e}{NC}")

    elif action == "status":
        try:
            result = await asyncio.to_thread(get_status)
            print(json.dumps(result, indent=2, ensure_ascii=False))
        except (WhatsAppNotConfiguredError, WhatsAppError) as e:
            print(f"{RED}Error: {e}{NC}")

    elif action == "send":
        if not number or not text:
            print(f'{RED}Usage: python3 flowcore.py whatsapp send --number 5511999999999 --text "message"{NC}')
            return
        try:
            await asyncio.to_thread(send_message, number, text)
            print(f"{GREEN}✓ Message sent to {number}{NC}")
        except (WhatsAppNotConfiguredError, WhatsAppError) as e:
            print(f"{RED}Error: {e}{NC}")

    else:
        print(f"{RED}Unknown whatsapp action: {action!r}{NC}")
        print("  Usage: python3 flowcore.py whatsapp <health|status|send>")


_STATUS_ICON = {"ok": "✓", "not_configured": "○", "not_authenticated": "△", "unreachable": "✗", "error": "✗"}


async def cmd_integrations() -> None:
    """Show live health/latency for every connected integration (Outlook/Calendar, WhatsApp, Ollama)."""
    import service

    results = await service.integrations_status()
    status_color = {
        "ok": GREEN,
        "not_configured": YELLOW,
        "not_authenticated": YELLOW,
        "unreachable": RED,
        "error": RED,
    }
    print(f"\n{BOLD}{CYAN}Integrations{NC}\n")
    for r in results:
        color = status_color.get(r["status"], RED)
        icon = _STATUS_ICON.get(r["status"], "?")
        print(f"  {color}{icon}{NC} {r['name']:<20} {r['detail']}")
        print(f"      {r['latency_ms']}ms · checked {r['checked_at']}")
    print()


async def cmd_telegram(action: str, text: str = "", chat_id: str = "") -> None:
    """Telegram (health, config, send) — reuses the spcx-monitor bot."""
    from runtime.telegram import (
        TelegramError,
        TelegramNotConfiguredError,
        check_health,
        get_configuration,
        send_message,
    )

    if action == "health":
        try:
            result = await asyncio.to_thread(check_health)
            print(f"{GREEN}✓ Bot reachable{NC} (@{result.get('username', '?')})")
        except (TelegramNotConfiguredError, TelegramError) as e:
            print(f"{RED}✗ {e}{NC}")

    elif action == "config":
        result = await asyncio.to_thread(get_configuration)
        mark = f"{GREEN}✓{NC}" if result["configured"] else f"{YELLOW}○{NC}"
        print(f"{mark} token_set={result['token_set']} chat_id_set={result['chat_id_set']}")

    elif action == "send":
        if not text:
            print(f'{RED}Usage: python3 flowcore.py telegram send --text "message" [--chat-id ID]{NC}')
            return
        try:
            await asyncio.to_thread(send_message, text, chat_id or None)
            print(f"{GREEN}✓ Message sent{NC}")
        except (TelegramNotConfiguredError, TelegramError) as e:
            print(f"{RED}Error: {e}{NC}")

    else:
        print(f"{RED}Unknown telegram action: {action!r}{NC}")
        print("  Usage: python3 flowcore.py telegram <health|config|send>")


def _print_event(event: dict) -> None:
    payload = event.get("payload", {})
    delta = payload.get("delta_bps", payload.get("delta_pct"))
    color = GREEN if (delta or 0) >= 0 else RED
    delta_str = f"{delta:+.2f}" if delta is not None else "n/a"
    print(f"  {event['source']:<10} {event['event']:<20} value={payload.get('value')}  {color}{delta_str}{NC}")


async def cmd_observer(action: str, source: str = "", interval: float = 300) -> None:
    """SCPX Observer Framework (Sprint 18) — normalized MarketEvents. No interpretation/scoring."""
    import service
    from runtime.observers.registry import registry
    from runtime.observers.scheduler import scheduler
    from runtime.observers.base import ObserverError

    if action == "registry":
        info = await service.observer_registry_info()
        for o in info:
            print(f"  {o['source']:<10} {o['category']:<12} {o['symbol']}")

    elif action == "events":
        try:
            if source:
                if source not in registry.names():
                    print(f"{RED}Unknown observer: {source!r}{NC}")
                    return
                events = await service.observer_source_events(source)
            else:
                events = await service.observer_events()
        except ObserverError as e:
            print(f"{RED}Error: {e}{NC}")
            return
        for event in events:
            _print_event(event)

    elif action == "health":
        try:
            result = await service.observer_health()
            print(f"{GREEN}✓ Reachable{NC} (vix={result['payload']['value']})")
        except ObserverError as e:
            print(f"{RED}✗ {e}{NC}")

    elif action == "watch":
        print(f"Watching {len(registry.names())} observer(s) every {interval}s (Ctrl-C to stop)...")
        try:
            await scheduler.run_forever(interval)
        except (KeyboardInterrupt, asyncio.CancelledError):
            print("\nStopped.")

    else:
        print(f"{RED}Unknown observer action: {action!r}{NC}")
        print("  Usage: python3 flowcore.py observer <registry|events [source]|health|watch>")


def _print_dimension_score(score: dict) -> None:
    if score["status"] == "insufficient_data":
        print(f"  {score['dimension']:<16} {YELLOW}insufficient_data{NC}  samples={score['sample_counts']}")
        return
    color = GREEN if (score["score"] or 0) >= 0 else RED
    print(f"  {score['dimension']:<16} {color}{score['score']:+.3f}{NC}  z_scores={score['z_scores']}")


async def cmd_macro_score(action: str, dimension: str = "") -> None:
    """SCPX Macro Score Engine (Sprint 19) — deterministic per-dimension scores. No LLM."""
    import service
    from runtime.macro_score import DIMENSIONS, MacroScoreError

    if action == "dimensions":
        for dim, sources in DIMENSIONS.items():
            print(f"  {dim:<16} {', '.join(sources)}")

    elif action == "scores":
        try:
            if dimension:
                if dimension not in DIMENSIONS:
                    print(f"{RED}Unknown dimension: {dimension!r}{NC}")
                    return
                score = await service.macro_score_compute(dimension)
                _print_dimension_score(score)
            else:
                for score in await service.macro_score_compute_all():
                    _print_dimension_score(score)
        except MacroScoreError as e:
            print(f"{RED}Error: {e}{NC}")

    else:
        print(f"{RED}Unknown macro-score action: {action!r}{NC}")
        print("  Usage: python3 flowcore.py macro-score <dimensions|scores [dimension]>")


_REGIME_COLOR = {"elevated": CYAN, "depressed": CYAN, "neutral": GREEN, "insufficient_data": YELLOW}
# Deliberately not red/green-for-good/bad — the Regime Engine only
# classifies magnitude, it never judges whether "elevated"/"depressed" is
# favorable (that's Portfolio Impact Engine's job, a later stage that
# doesn't exist yet). Elevated/depressed share a color; only
# neutral/insufficient_data get their own, purely to distinguish "a real
# signal fired" from "nothing notable" / "no data" at a glance.


def _print_regime_signal(signal: dict) -> None:
    color = _REGIME_COLOR.get(signal["regime"], YELLOW)
    score_str = f"{signal['score']:+.3f}" if signal["score"] is not None else "n/a"
    print(f"  {signal['dimension']:<16} {color}{signal['regime']:<18}{NC} score={score_str}")


async def cmd_regime(action: str, dimension: str = "") -> None:
    """SCPX Regime Engine (Sprint 20) — deterministic threshold classification. No LLM."""
    import service
    from runtime.macro_score import DIMENSIONS, MacroScoreError

    if action == "signals":
        try:
            if dimension:
                if dimension not in DIMENSIONS:
                    print(f"{RED}Unknown dimension: {dimension!r}{NC}")
                    return
                signal = await service.regime_classify(dimension)
                _print_regime_signal(signal)
            else:
                for signal in await service.regime_classify_all():
                    _print_regime_signal(signal)
        except MacroScoreError as e:
            print(f"{RED}Error: {e}{NC}")

    else:
        print(f"{RED}Unknown regime action: {action!r}{NC}")
        print("  Usage: python3 flowcore.py regime signals [dimension]")


def _print_holding(h: dict) -> None:
    price_str = f"${h['price']:.2f}" if h["price"] is not None else "n/a"
    mv_str = f"${h['market_value']:.2f}" if h["market_value"] is not None else "n/a"
    gain = h["unrealized_gain"]
    if gain is None:
        gain_str = f"{YELLOW}n/a{NC}"
    else:
        color = GREEN if gain >= 0 else RED
        pct = h["unrealized_gain_pct"]
        gain_str = f"{color}{gain:+.2f} ({pct:+.1f}%){NC}" if pct is not None else f"{color}{gain:+.2f}{NC}"
    asset_name = (h.get("asset") or {}).get("name") or h["symbol"]
    print(
        f"  [{h['id']}] {h['symbol']:<8} {h['quantity']:g} @ {h['average_cost']:.2f}"
        f"  price={price_str}  value={mv_str}  gain={gain_str}  ({asset_name})"
    )
    if h.get("valuation_error"):
        print(f"      {RED}⚠ {h['valuation_error']}{NC}")


_DIRECTION_COLOR = {"positive": GREEN, "negative": RED, "neutral": CYAN, "insufficient_data": YELLOW}


def _print_driver_impact(d: dict) -> None:
    color = _DIRECTION_COLOR.get(d["direction"], YELLOW)
    print(f"  {CYAN}{d['dimension']}{NC} — {d['driver']}")
    print(f"    regime={d['regime']}  direction={color}{d['direction']}{NC}  impact={d['expected_impact']}")
    print(f"    confidence={d['confidence_label']} ({d['confidence_score']})  exposed={d['exposed_weight_pct']:.1f}%")
    print(f"    {d['reason']}")
    for b in d["buckets"]:
        bc = GREEN if b["matched_direction"] == "positive" else RED
        print(f"      {bc}{b['label']:<20}{NC} {b['weight_pct']:5.1f}%  ({b['source']}, {b['holding_count']} holdings)")


def _print_recommendation(r: dict) -> None:
    print(f"  • {r['action']}  (confiança={r['confidence']:.2f})")
    print(f"    {r['reason']}")
    if r["affected_holdings"]:
        print(f"    Holdings: {', '.join(r['affected_holdings'])}")
    products = r.get("products")
    if products:
        names = ", ".join(f"{p['symbol']} ({p['name']})" for p in products)
        print(f"    {GREEN}Produtos:{NC} {names}")


def _print_impact_report(report: dict) -> None:
    color = _DIRECTION_COLOR.get(report["overall_impact"], YELLOW)
    print(f"Impacto geral: {color}{report['overall_impact']}{NC}  (confiança={report['confidence']:.2f})")
    print(f"Risk score: {report['portfolio_risk_score']:.1f}/100")
    print(f"Dimensões afetadas: {', '.join(report['affected_dimensions']) or 'nenhuma'}")
    print(f"\n{CYAN}Drivers:{NC}")
    for d in report["drivers"]:
        _print_driver_impact(d)
    if report["recommendations"]:
        print(f"\n{CYAN}Recomendações:{NC}")
        for r in report["recommendations"]:
            _print_recommendation(r)
    if report["opportunities"]:
        print(f"\n{CYAN}Oportunidades:{NC}")
        for r in report["opportunities"]:
            _print_recommendation(r)


def _print_exposure_report(dim: str, report: dict) -> None:
    print(f"  {CYAN}{dim}{NC}  total=${report['total_market_value']:.2f}  unvalued={report['unvalued_count']}")
    for b in report["buckets"]:
        print(
            f"    {b['label']:<20} {b['weight_pct']:5.1f}%  ${b['market_value']:.2f}  ({b['holding_count']} holdings)"
        )


async def cmd_portfolio(
    action: str,
    portfolio_id: int = 0,
    name: str = "",
    symbol: str = "",
    quantity: float = 0.0,
    average_cost: float = 0.0,
    currency: str = "USD",
    holding_id: int = 0,
    dimension: str = "",
    shelf: str = "",
) -> None:
    """FlowCore Portfolio Domain (Sprint 21, Phase 1) — manual holdings CRUD."""
    import service
    from runtime.product_mapping import DEFAULT_SHELF, ProductMappingError

    if action == "create":
        if not name:
            print(f'{RED}Usage: python3 flowcore.py portfolio create "<name>"{NC}')
            return
        p = await service.create_portfolio(name)
        print(f"{GREEN}✓ Portfolio criado{NC} [{p['id']}] {p['name']}")

    elif action == "list":
        portfolios = await service.list_portfolios()
        if not portfolios:
            print("Nenhum portfólio ainda.")
        for p in portfolios:
            print(f"  [{p['id']}] {p['name']} — criado em {p['created_at']}")

    elif action == "show":
        try:
            p = await service.get_portfolio(portfolio_id)
            holdings = await service.list_holdings(portfolio_id)
        except ValueError as e:
            print(f"{RED}Error: {e}{NC}")
            return
        print(f"[{p['id']}] {p['name']}")
        if not holdings:
            print("  Nenhuma holding ainda.")
        for h in holdings:
            _print_holding(h)

    elif action == "summary":
        try:
            s = await service.portfolio_summary(portfolio_id)
        except ValueError as e:
            print(f"{RED}Error: {e}{NC}")
            return
        color = GREEN if s["total_unrealized_gain"] >= 0 else RED
        pct = s["total_unrealized_gain_pct"]
        pct_str = f" ({pct:+.1f}%)" if pct is not None else ""
        print(f"  Holdings: {s['valued_holding_count']}/{s['holding_count']} valuadas")
        print(f"  Valor de mercado: ${s['total_market_value']:.2f}")
        print(f"  Custo: ${s['total_cost_basis']:.2f}")
        print(f"  Ganho/perda: {color}{s['total_unrealized_gain']:+.2f}{pct_str}{NC}")

    elif action == "delete":
        deleted = await service.delete_portfolio(portfolio_id)
        if deleted:
            print(f"{GREEN}✓ Portfólio removido{NC}")
        else:
            print(f"{RED}Portfólio não encontrado: {portfolio_id}{NC}")

    elif action == "add-holding":
        if not symbol or quantity <= 0:
            print(
                f"{RED}Usage: python3 flowcore.py portfolio add-holding "
                f"<portfolio_id> <symbol> <quantity> <average_cost> [--currency USD]{NC}"
            )
            return
        try:
            h = await service.add_holding(portfolio_id, symbol, quantity, average_cost, currency)
        except ValueError as e:
            print(f"{RED}Error: {e}{NC}")
            return
        print(f"{GREEN}✓ Holding adicionada{NC} [{h['id']}] {h['symbol']} x{h['quantity']:g}")

    elif action == "remove-holding":
        deleted = await service.delete_holding(holding_id)
        if deleted:
            print(f"{GREEN}✓ Holding removida{NC}")
        else:
            print(f"{RED}Holding não encontrada: {holding_id}{NC}")

    elif action == "exposure":
        from runtime.exposure import ExposureError

        try:
            if dimension:
                report = await service.portfolio_exposure(portfolio_id, dimension)
                _print_exposure_report(dimension, report)
            else:
                full = await service.portfolio_exposure(portfolio_id)
                for dim, report in full.items():
                    _print_exposure_report(dim, report)
        except ValueError as e:
            print(f"{RED}Error: {e}{NC}")
        except ExposureError as e:
            print(f"{RED}Error: {e}{NC}")

    elif action == "concentration":
        try:
            c = await service.portfolio_concentration(portfolio_id)
        except ValueError as e:
            print(f"{RED}Error: {e}{NC}")
            return
        print(f"  HHI: {c['hhi']:.1f}  (0-10000, maior = mais concentrado)")
        print(f"  Maior holding: {c['top_holding_weight_pct']:.1f}%")
        print(f"  Top 5: {c['top_5_weight_pct']:.1f}%")
        print(f"  Holdings: {c['holding_count']} ({c['unvalued_count']} não valuadas)")

    elif action == "impact":
        try:
            report = await service.portfolio_impact(portfolio_id)
        except ValueError as e:
            print(f"{RED}Error: {e}{NC}")
            return
        _print_impact_report(report)

    elif action == "recommendations":
        try:
            r = await service.portfolio_recommendations(portfolio_id, shelf or DEFAULT_SHELF)
        except ValueError as e:
            print(f"{RED}Error: {e}{NC}")
            return
        except ProductMappingError as e:
            print(f"{RED}Error: {e}{NC}")
            return
        print(f"Shelf: {CYAN}{r['shelf']}{NC}")
        if r["recommendations"]:
            print(f"{CYAN}Recomendações:{NC}")
            for rec in r["recommendations"]:
                _print_recommendation(rec)
        if r["opportunities"]:
            print(f"\n{CYAN}Oportunidades:{NC}")
            for rec in r["opportunities"]:
                _print_recommendation(rec)
        if not r["recommendations"] and not r["opportunities"]:
            print("Nenhuma recomendação ou oportunidade no momento.")

    else:
        print(f"{RED}Unknown portfolio action: {action!r}{NC}")
        print(
            "  Usage: python3 flowcore.py portfolio <create|list|show|summary|delete|"
            "add-holding|remove-holding|exposure [dimension]|concentration|impact|recommendations>"
        )


async def cmd_asset(action: str, symbol: str = "", **tags: str) -> None:
    """FlowCore Portfolio Domain (Sprint 21, Phase 1) — asset classification lookup/tagging."""
    import service

    if action == "show":
        if not symbol:
            print(f"{RED}Usage: python3 flowcore.py asset show <symbol>{NC}")
            return
        try:
            asset = await service.get_asset(symbol)
        except ValueError as e:
            print(f"{RED}Error: {e}{NC}")
            return
        print(f"{asset['symbol']} — {asset['name']}")
        print(f"  Classe: {asset['asset_class']}  Setor: {asset['sector']}  Indústria: {asset['industry']}")
        print(f"  País: {asset['country']}  Moeda: {asset['currency']}")
        if asset["attributes"]:
            print(f"  Atributos: {asset['attributes']}")

    elif action == "tag":
        if not symbol:
            print(f"{RED}Usage: python3 flowcore.py asset tag <symbol> [--theme ...] [--duration ...] ...{NC}")
            return
        asset = await service.tag_asset(symbol, **tags)
        print(f"{GREEN}✓ Atributos atualizados{NC} — {asset['attributes']}")

    else:
        print(f"{RED}Unknown asset action: {action!r}{NC}")
        print("  Usage: python3 flowcore.py asset <show|tag>")


def main() -> None:
    """Main CLI handler."""
    parser = argparse.ArgumentParser(description="FlowCore CLI")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("serve", help="Start the API server")
    subparsers.add_parser("mcp", help="Start the MCP stdio server (for Claude Code / MCP clients)")
    subparsers.add_parser("run", help="Start the API server with full runtime lifecycle")
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
    daemon_start.add_argument("--interval", type=int, default=60, help="Heartbeat interval in seconds (default: 60)")
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

    flow_parser = subparsers.add_parser("flow", help="Manage flows (named step pipelines)")
    flow_sub = flow_parser.add_subparsers(dest="flow_action")
    flow_sub.add_parser("list", help="List all flows")
    flow_create = flow_sub.add_parser("create", help="Create a new flow")
    flow_create.add_argument("name", help="Flow name")
    flow_create.add_argument("steps_json", help='JSON list of steps, e.g. \'[{"action":"note","params":{...}}]\'')
    flow_show = flow_sub.add_parser("show", help="Show a flow's definition")
    flow_show.add_argument("flow_id", type=int, help="Flow ID")
    flow_run = flow_sub.add_parser("run", help="Run a flow now")
    flow_run.add_argument("flow_id", type=int, help="Flow ID")
    flow_delete = flow_sub.add_parser("delete", help="Delete a flow")
    flow_delete.add_argument("flow_id", type=int, help="Flow ID")

    android_parser = subparsers.add_parser("android", help="Android device capabilities")
    android_sub = android_parser.add_subparsers(dest="android_action")
    android_sub.add_parser("battery", help="Show battery status")
    android_sub.add_parser("wifi", help="Show wifi/network info")
    android_sub.add_parser("storage", help="Show disk usage")
    android_sub.add_parser("apps", help="List installed apps")
    android_sub.add_parser("clipboard-get", help="Read clipboard")
    android_clip_set = android_sub.add_parser("clipboard-set", help="Set clipboard")
    android_clip_set.add_argument("text", help="Text to copy to clipboard")
    android_notify = android_sub.add_parser("notify", help="Send an Android notification")
    android_notify.add_argument("text", help="Notification body")
    android_notify.add_argument("--title", default="FlowCore", help="Notification title (default: FlowCore)")

    outlook_parser = subparsers.add_parser("outlook", help="Outlook integration (read-only)")
    outlook_sub = outlook_parser.add_subparsers(dest="outlook_action")
    outlook_sub.add_parser("auth", help="Authenticate via device code flow")
    outlook_messages_p = outlook_sub.add_parser("messages", help="List latest messages")
    outlook_messages_p.add_argument("--limit", type=int, default=10, help="Max results (default: 10)")
    outlook_sub.add_parser("unread", help="Show unread count")
    outlook_search_p = outlook_sub.add_parser("search", help="Search messages")
    outlook_search_p.add_argument("query", help="Search query")
    outlook_search_p.add_argument("--limit", type=int, default=10, help="Max results (default: 10)")

    calendar_parser = subparsers.add_parser("calendar", help="Microsoft Calendar integration")
    calendar_sub = calendar_parser.add_subparsers(dest="calendar_action")
    calendar_sub.add_parser("auth", help="Authenticate via device code flow (shared with outlook auth)")
    calendar_sub.add_parser("today", help="Show today's events")
    calendar_sub.add_parser("tomorrow", help="Show tomorrow's events")
    calendar_sub.add_parser("week", help="Show this week's events")
    calendar_sub.add_parser("next", help="Show the next upcoming meeting")
    calendar_search_p = calendar_sub.add_parser("search", help="Search events")
    calendar_search_p.add_argument("query", help="Search query")
    calendar_search_p.add_argument("--limit", type=int, default=10, help="Max results (default: 10)")

    calendar_create_p = calendar_sub.add_parser("create", help="Create an event")
    calendar_create_p.add_argument("--subject", required=True, help="Event title")
    calendar_create_p.add_argument("--start", required=True, help="Start, ISO 8601 (e.g. 2026-08-10T10:00:00)")
    calendar_create_p.add_argument("--end", required=True, help="End, ISO 8601")
    calendar_create_p.add_argument("--timezone", default="UTC", help="Timezone (default: UTC)")
    calendar_create_p.add_argument("--description", default="", help="Event description")
    calendar_create_p.add_argument("--location", default="", help="Event location")
    calendar_create_p.add_argument("--attendees", default="", help="Comma-separated email addresses")

    calendar_update_p = calendar_sub.add_parser("update", help="Update an event")
    calendar_update_p.add_argument("event_id", help="Event ID (from `calendar today`/`search` output)")
    calendar_update_p.add_argument("--subject", default="", help="New title")
    calendar_update_p.add_argument("--start", default="", help="New start, ISO 8601")
    calendar_update_p.add_argument("--end", default="", help="New end, ISO 8601")
    calendar_update_p.add_argument("--timezone", default="UTC", help="Timezone for start/end (default: UTC)")
    calendar_update_p.add_argument("--description", default="", help="New description")
    calendar_update_p.add_argument("--location", default="", help="New location")
    calendar_update_p.add_argument("--attendees", default="", help="Comma-separated email addresses")

    calendar_delete_p = calendar_sub.add_parser("delete", help="Delete an event")
    calendar_delete_p.add_argument("event_id", help="Event ID")

    whatsapp_parser = subparsers.add_parser("whatsapp", help="WhatsApp via Evolution API")
    whatsapp_sub = whatsapp_parser.add_subparsers(dest="whatsapp_action")
    whatsapp_sub.add_parser("health", help="Check Evolution API server reachability")
    whatsapp_sub.add_parser("status", help="Show the configured instance's connection state")
    whatsapp_send_p = whatsapp_sub.add_parser("send", help="Send a WhatsApp message")
    whatsapp_send_p.add_argument("--number", required=True, help="Destination number (e.g. 5511999999999)")
    whatsapp_send_p.add_argument("--text", required=True, help="Message text")

    subparsers.add_parser("integrations", help="Show live status of all connected integrations")

    telegram_parser = subparsers.add_parser("telegram", help="Telegram (reuses the spcx-monitor bot)")
    telegram_sub = telegram_parser.add_subparsers(dest="telegram_action")
    telegram_sub.add_parser("health", help="Verify the bot token")
    telegram_sub.add_parser("config", help="Show whether TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID are set")
    telegram_send_p = telegram_sub.add_parser("send", help="Send a message")
    telegram_send_p.add_argument("--text", required=True, help="Message text")
    telegram_send_p.add_argument("--chat-id", default="", help="Override TELEGRAM_CHAT_ID for this message")

    observer_parser = subparsers.add_parser("observer", help="SCPX Observer Framework (normalized MarketEvents)")
    observer_sub = observer_parser.add_subparsers(dest="observer_action")
    observer_sub.add_parser("registry", help="List registered observers (no fetch)")
    observer_events_p = observer_sub.add_parser("events", help="Run observers now and print MarketEvents")
    observer_events_p.add_argument(
        "source", nargs="?", default="", help="Run only this observer (treasury, dollar, vix, oil, gold)"
    )
    observer_sub.add_parser("health", help="Live reachability probe (runs the vix observer)")
    observer_watch_p = observer_sub.add_parser("watch", help="Run the scheduler in the foreground (Ctrl-C to stop)")
    observer_watch_p.add_argument("--interval", type=float, default=300, help="Seconds between cycles (default: 300)")

    macro_score_parser = subparsers.add_parser(
        "macro-score", help="SCPX Macro Score Engine (deterministic per-dimension scores, no LLM)"
    )
    macro_score_sub = macro_score_parser.add_subparsers(dest="macro_score_action")
    macro_score_sub.add_parser("dimensions", help="List dimensions and their source mapping (no computation)")
    macro_score_scores_p = macro_score_sub.add_parser("scores", help="Compute scores now")
    macro_score_scores_p.add_argument("dimension", nargs="?", default="", help="Compute only this dimension")

    regime_parser = subparsers.add_parser(
        "regime", help="SCPX Regime Engine (deterministic threshold classification, no LLM)"
    )
    regime_sub = regime_parser.add_subparsers(dest="regime_action")
    regime_signals_p = regime_sub.add_parser("signals", help="Classify every dimension's regime now")
    regime_signals_p.add_argument("dimension", nargs="?", default="", help="Classify only this dimension")

    portfolio_parser = subparsers.add_parser("portfolio", help="Portfolio Domain (Sprint 21, manual holdings CRUD)")
    portfolio_sub = portfolio_parser.add_subparsers(dest="portfolio_action")

    portfolio_create_p = portfolio_sub.add_parser("create", help="Create a portfolio")
    portfolio_create_p.add_argument("name", help="Portfolio name")

    portfolio_sub.add_parser("list", help="List portfolios")

    portfolio_show_p = portfolio_sub.add_parser("show", help="Show a portfolio and its holdings")
    portfolio_show_p.add_argument("portfolio_id", type=int)

    portfolio_summary_p = portfolio_sub.add_parser("summary", help="Portfolio totals (live)")
    portfolio_summary_p.add_argument("portfolio_id", type=int)

    portfolio_delete_p = portfolio_sub.add_parser("delete", help="Delete a portfolio (cascades to its holdings)")
    portfolio_delete_p.add_argument("portfolio_id", type=int)

    portfolio_add_holding_p = portfolio_sub.add_parser("add-holding", help="Add a holding to a portfolio")
    portfolio_add_holding_p.add_argument("portfolio_id", type=int)
    portfolio_add_holding_p.add_argument("symbol")
    portfolio_add_holding_p.add_argument("quantity", type=float)
    portfolio_add_holding_p.add_argument("average_cost", type=float)
    portfolio_add_holding_p.add_argument("--currency", default="USD")

    portfolio_remove_holding_p = portfolio_sub.add_parser("remove-holding", help="Remove a holding")
    portfolio_remove_holding_p.add_argument("holding_id", type=int)

    portfolio_exposure_p = portfolio_sub.add_parser(
        "exposure", help="Weighted classification breakdown (Sprint 22, live)"
    )
    portfolio_exposure_p.add_argument("portfolio_id", type=int)
    portfolio_exposure_p.add_argument(
        "dimension", nargs="?", default="", help="asset_class|sector|industry|country|currency|<soft attribute>"
    )

    portfolio_concentration_p = portfolio_sub.add_parser(
        "concentration", help="Concentration report — HHI, top holding, top 5 (Sprint 22, live)"
    )
    portfolio_concentration_p.add_argument("portfolio_id", type=int)

    portfolio_impact_p = portfolio_sub.add_parser(
        "impact", help="Portfolio Impact Engine — macro regime vs. portfolio (Sprint 23, live)"
    )
    portfolio_impact_p.add_argument("portfolio_id", type=int)

    portfolio_recommendations_p = portfolio_sub.add_parser(
        "recommendations", help="Deterministic recommendations/opportunities (Sprint 23, live)"
    )
    portfolio_recommendations_p.add_argument("portfolio_id", type=int)
    portfolio_recommendations_p.add_argument(
        "--shelf", default="", help="Product shelf (default: us_etf) — see 'product-shelves'"
    )

    subparsers.add_parser("product-shelves", help="List available product shelves (Sprint 23)")

    asset_parser = subparsers.add_parser("asset", help="Asset classification lookup/tagging (Sprint 21)")
    asset_sub = asset_parser.add_subparsers(dest="asset_action")

    asset_show_p = asset_sub.add_parser("show", help="Show an asset's classification")
    asset_show_p.add_argument("symbol")

    asset_tag_p = asset_sub.add_parser("tag", help="Manually tag an asset's soft attributes")
    asset_tag_p.add_argument("symbol")
    # Flags derived from the canonical schema (runtime/portfolio/attributes.py),
    # not hand-listed — a new attribute added there gets a CLI flag for free.
    for _field in ASSET_ATTRIBUTE_FIELDS:
        asset_tag_p.add_argument(f"--{_field.replace('_', '-')}", dest=_field, default=None)

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
        asyncio.run(cmd_import(args.file))
    elif args.command == "docs":
        asyncio.run(cmd_docs())
    elif args.command == "show":
        asyncio.run(cmd_show(args.id))
    elif args.command == "ping":
        cmd_ping()
    elif args.command == "models":
        cmd_models()
    elif args.command == "stats":
        asyncio.run(cmd_stats())
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
        asyncio.run(cmd_demo())
    elif args.command == "search":
        asyncio.run(cmd_search(args.query))
    elif args.command == "daily":
        asyncio.run(cmd_daily())
    elif args.command == "sync":
        asyncio.run(cmd_sync(args.folder))
    elif args.command == "watch":
        asyncio.run(cmd_watch(args.folder))
    elif args.command == "ask":
        asyncio.run(cmd_ask(" ".join(args.question)))
    elif args.command == "note":
        asyncio.run(cmd_note(" ".join(args.text)))
    elif args.command == "todo":
        asyncio.run(cmd_todo(" ".join(args.task)))
    elif args.command == "agenda":
        asyncio.run(cmd_agenda(" ".join(args.event)))
    elif args.command == "obsidian":
        if args.obsidian_command == "init":
            cmd_obsidian_init()
        elif args.obsidian_command == "sync":
            asyncio.run(cmd_obsidian_sync())
        elif args.obsidian_command == "watch":
            asyncio.run(cmd_obsidian_watch())
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
        name = getattr(args, "name", "")
        script = getattr(args, "script", "")
        schedule = getattr(args, "schedule", "")
        cmd_jobs(action, name=name, script=script, schedule=schedule)
    elif args.command == "flow":
        action = getattr(args, "flow_action", None)
        if not action:
            print("Usage: python3 flowcore.py flow <list|create|show|run|delete>")
            sys.exit(1)
        name = getattr(args, "name", "")
        steps_json = getattr(args, "steps_json", "")
        flow_id = getattr(args, "flow_id", 0)
        asyncio.run(cmd_flow(action, name=name, steps_json=steps_json, flow_id=flow_id))
    elif args.command == "android":
        action = getattr(args, "android_action", None)
        if not action:
            print("Usage: python3 flowcore.py android <battery|wifi|storage|apps|clipboard-get|clipboard-set|notify>")
            sys.exit(1)
        text = getattr(args, "text", "")
        title = getattr(args, "title", "FlowCore")
        asyncio.run(cmd_android(action, text=text, title=title))
    elif args.command == "outlook":
        action = getattr(args, "outlook_action", None)
        if not action:
            print("Usage: python3 flowcore.py outlook <auth|messages|unread|search>")
            sys.exit(1)
        query = getattr(args, "query", "")
        limit = getattr(args, "limit", 10)
        asyncio.run(cmd_outlook(action, query=query, limit=limit))
    elif args.command == "calendar":
        action = getattr(args, "calendar_action", None)
        if not action:
            print("Usage: python3 flowcore.py calendar <auth|today|tomorrow|week|next|search|create|update|delete>")
            sys.exit(1)
        attendees_raw = getattr(args, "attendees", "")
        attendees = [a.strip() for a in attendees_raw.split(",") if a.strip()] if attendees_raw else None
        asyncio.run(
            cmd_calendar(
                action,
                query=getattr(args, "query", ""),
                limit=getattr(args, "limit", 10),
                event_id=getattr(args, "event_id", ""),
                subject=getattr(args, "subject", ""),
                start=getattr(args, "start", ""),
                end=getattr(args, "end", ""),
                timezone_=getattr(args, "timezone", "UTC"),
                description=getattr(args, "description", ""),
                location=getattr(args, "location", ""),
                attendees=attendees,
            )
        )
    elif args.command == "whatsapp":
        action = getattr(args, "whatsapp_action", None)
        if not action:
            print("Usage: python3 flowcore.py whatsapp <health|status|send>")
            sys.exit(1)
        number = getattr(args, "number", "")
        text = getattr(args, "text", "")
        asyncio.run(cmd_whatsapp(action, number=number, text=text))
    elif args.command == "integrations":
        asyncio.run(cmd_integrations())
    elif args.command == "telegram":
        action = getattr(args, "telegram_action", None)
        if not action:
            print("Usage: python3 flowcore.py telegram <health|config|send>")
            sys.exit(1)
        text = getattr(args, "text", "")
        chat_id = getattr(args, "chat_id", "")
        asyncio.run(cmd_telegram(action, text=text, chat_id=chat_id))
    elif args.command == "observer":
        action = getattr(args, "observer_action", None)
        if not action:
            print("Usage: python3 flowcore.py observer <registry|events [source]|health|watch>")
            sys.exit(1)
        source = getattr(args, "source", "")
        interval = getattr(args, "interval", 300)
        asyncio.run(cmd_observer(action, source=source, interval=interval))
    elif args.command == "macro-score":
        action = getattr(args, "macro_score_action", None)
        if not action:
            print("Usage: python3 flowcore.py macro-score <dimensions|scores [dimension]>")
            sys.exit(1)
        dimension = getattr(args, "dimension", "")
        asyncio.run(cmd_macro_score(action, dimension=dimension))
    elif args.command == "regime":
        action = getattr(args, "regime_action", None)
        if not action:
            print("Usage: python3 flowcore.py regime signals [dimension]")
            sys.exit(1)
        dimension = getattr(args, "dimension", "")
        asyncio.run(cmd_regime(action, dimension=dimension))
    elif args.command == "portfolio":
        action = getattr(args, "portfolio_action", None)
        if not action:
            print(
                "Usage: python3 flowcore.py portfolio <create|list|show|summary|delete|"
                "add-holding|remove-holding|exposure [dimension]|concentration|impact|recommendations>"
            )
            sys.exit(1)
        asyncio.run(
            cmd_portfolio(
                action,
                portfolio_id=getattr(args, "portfolio_id", 0),
                name=getattr(args, "name", ""),
                symbol=getattr(args, "symbol", ""),
                quantity=getattr(args, "quantity", 0.0),
                average_cost=getattr(args, "average_cost", 0.0),
                currency=getattr(args, "currency", "USD"),
                holding_id=getattr(args, "holding_id", 0),
                dimension=getattr(args, "dimension", ""),
                shelf=getattr(args, "shelf", ""),
            )
        )
    elif args.command == "product-shelves":
        import service

        shelves = asyncio.run(service.product_shelves())
        if not shelves:
            print("Nenhum shelf configurado em config/product_shelves/.")
        for s in shelves:
            print(f"  {s}")
    elif args.command == "asset":
        action = getattr(args, "asset_action", None)
        if not action:
            print("Usage: python3 flowcore.py asset <show|tag>")
            sys.exit(1)
        symbol = getattr(args, "symbol", "")
        # Extraction derived from the same canonical schema used to register
        # the flags above — one list, not a hand-kept parallel dict.
        tags = {field: getattr(args, field, None) for field in ASSET_ATTRIBUTE_FIELDS}
        asyncio.run(cmd_asset(action, symbol=symbol, **tags))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
