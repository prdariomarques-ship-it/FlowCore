#!/usr/bin/env python3
"""FlowCore — Main entry point.

Usage:
    python3 flowcore.py serve        Start the API server
    python3 flowcore.py run          Start the full application (API + scheduler + agents)
    python3 flowcore.py health       Quick health check
    python3 flowcore.py version      Print version
    python3 flowcore.py selftest     Validate the entire installation
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import os
import sys
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


def selftest_check(name: str, fn, detail: str = "") -> bool:
    """Run a single self-test check and print the result."""
    try:
        fn()
        print(f"  {GREEN}PASS{NC}  {name}")
        if detail:
            print(f"         {detail}")
        return True
    except Exception as e:
        print(f"  {RED}FAIL{NC}  {name}")
        print(f"         {e}")
        return False


def cmd_selftest() -> None:
    """Validate the entire FlowCore installation."""
    passed = 0
    failed = 0

    print("")
    print(f"{BOLD}{CYAN}╔══════════════════════════════════════════════════╗{NC}")
    print(f"{BOLD}{CYAN}║         FlowCore Self-Test                      ║{NC}")
    print(f"{BOLD}{CYAN}╚══════════════════════════════════════════════════╝{NC}")
    print("")

    # ── 1. Imports ───────────────────────────────────────────────────────
    print(f"{BOLD}1. Python Imports{NC}")
    modules = ["config.loader", "runtime.core", "executor.engine",
               "scheduler.service", "api.router", "agents.base",
               "agents.health_agent", "scripts.helpers"]
    for mod in modules:
        def _import():
            importlib.import_module(mod)
        if selftest_check(f"import {mod}", _import):
            passed += 1
        else:
            failed += 1

    # ── 2. Configuration ─────────────────────────────────────────────────
    print(f"\n{BOLD}2. Configuration{NC}")

    def _load_config():
        from config.loader import get_config
        cfg = get_config()
        assert cfg["app"]["name"] == "FlowCore"
        assert "api" in cfg
        assert cfg["api"]["host"] == "127.0.0.1"

    if selftest_check("load config/default.yml", _load_config,
                      "name=FlowCore, host=127.0.0.1"):
        passed += 1
    else:
        failed += 1

    # ── 3. Database ──────────────────────────────────────────────────────
    print(f"\n{BOLD}3. Database (SQLite){NC}")

    async def _db_init():
        from runtime.core import init_database
        cfg = get_config()
        await init_database(cfg)

    async def _db_query():
        import aiosqlite
        async with aiosqlite.connect("data/flowcore.db") as db:
            cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = await cursor.fetchall()
            assert len(tables) > 0

    from config.loader import get_config
    if asyncio.run(_run_async(_db_init)):
        passed += 1
    else:
        failed += 1

    if asyncio.run(_run_async(_db_query)):
        passed += 1
    else:
        failed += 1

    # ── 4. Executor ──────────────────────────────────────────────────────
    print(f"\n{BOLD}4. Executor{NC}")

    async def _executor_run():
        from executor.engine import ExecutorEngine, Task
        executor = ExecutorEngine()
        await executor.start()
        async def _noop(*a, **kw):
            return {"result": "ok"}
        task = Task(name="selftest", handler=_noop)
        result = await executor.submit(task)
        assert result is not None

    if asyncio.run(_run_async(_executor_run)):
        passed += 1
    else:
        failed += 1

    # ── 5. Scheduler ─────────────────────────────────────────────────────
    print(f"\n{BOLD}5. Scheduler{NC}")

    def _scheduler_create():
        from scheduler.service import SchedulerService
        scheduler = SchedulerService(timezone="UTC")
        assert scheduler is not None

    if selftest_check("create scheduler", _scheduler_create):
        passed += 1
    else:
        failed += 1

    # ── 6. Agent Framework ───────────────────────────────────────────────
    print(f"\n{BOLD}6. Agent Framework{NC}")

    async def _agent_run():
        from agents.health_agent import HealthAgent
        agent = HealthAgent()
        result = await agent.run()
        assert result["status"] == "ok"
        assert "data" in result

    if asyncio.run(_run_async(_agent_run)):
        passed += 1
    else:
        failed += 1

    async def _agent_health():
        from agents.health_agent import HealthAgent
        agent = HealthAgent()
        hc = await agent.health_check()
        assert hc["status"] == "ok"

    if asyncio.run(_run_async(_agent_health)):
        passed += 1
    else:
        failed += 1

    # ── 7. API ───────────────────────────────────────────────────────────
    print(f"\n{BOLD}7. API (FastAPI){NC}")

    def _api_create():
        from api.router import create_app
        app = create_app(version="1.0.0", platform_info={"os_name": "linux"})
        assert app is not None

    if selftest_check("create FastAPI app", _api_create):
        passed += 1
    else:
        failed += 1

    async def _api_health_endpoint():
        from httpx import AsyncClient, ASGITransport
        from api.router import create_app
        app = create_app(version="1.0.0", platform_info={"os_name": "linux"})
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"

    if asyncio.run(_run_async(_api_health_endpoint)):
        passed += 1
    else:
        failed += 1

    # ── 8. CLI ───────────────────────────────────────────────────────────
    print(f"\n{BOLD}8. CLI Commands{NC}")

    def _version_cmd():
        from config.loader import get_config
        cfg = get_config()
        from runtime.core import detect_platform
        p = detect_platform()
        assert cfg["app"]["version"] == "1.0.0"

    if selftest_check("version command", _version_cmd, "v1.0.0"):
        passed += 1
    else:
        failed += 1

    # ── 9. Directory Structure ───────────────────────────────────────────
    print(f"\n{BOLD}9. Directory Structure{NC}")

    required_dirs = ["config", "runtime", "executor", "scheduler",
                     "api", "agents", "scripts", "logs", "backups", "data"]
    for d in required_dirs:
        def _check_dir():
            assert (ROOT / d).is_dir()
        if selftest_check(f"directory {d}/", _check_dir):
            passed += 1
        else:
            failed += 1

    required_files = ["flowcore.py", "daemon.py", "install.sh",
                      "validate_android.sh", "doctor.sh", "requirements.txt"]
    for f in required_files:
        def _check_file(path=f):
            assert (ROOT / path).exists()
        if selftest_check(f"file {f}", _check_file):
            passed += 1
        else:
            failed += 1

    # ── 10. Logs ─────────────────────────────────────────────────────────
    print(f"\n{BOLD}10. Logging{NC}")

    def _loguru_import():
        from loguru import logger
        assert logger is not None

    if selftest_check("loguru logging", _loguru_import):
        passed += 1
    else:
        failed += 1

    # ── Summary ──────────────────────────────────────────────────────────
    total = passed + failed
    print("")
    if failed == 0:
        print(f"{GREEN}{BOLD}══════════════════════════════════════════════════{NC}")
        print(f"{GREEN}{BOLD}  ALL TESTS PASSED: {passed}/{total}              {NC}")
        print(f"{GREEN}{BOLD}══════════════════════════════════════════════════{NC}")
    else:
        print(f"{RED}{BOLD}══════════════════════════════════════════════════{NC}")
        print(f"{RED}{BOLD}  FAILED: {failed}/{total}  (passed: {passed})       {NC}")
        print(f"{RED}{BOLD}══════════════════════════════════════════════════{NC}")
        print(f"\n{YELLOW}Run 'bash doctor.sh' for diagnostics.{NC}")
        print(f"{YELLOW}Run 'bash repair.sh' to attempt auto-fix.{NC}")
        sys.exit(1)


async def _run_async(coro_fn) -> bool:
    """Helper to run an async function and return True/False."""
    try:
        await coro_fn()
        return True
    except Exception as e:
        print(f"  {RED}FAIL{NC}  (async error)")
        print(f"         {e}")
        return False


async def cmd_serve(cfg: dict, platform: dict) -> None:
    """Start the FastAPI server."""
    try:
        from api.router import create_app
    except ImportError:
        logger.error("FastAPI not installed. Run: bash install_api.sh")
        sys.exit(1)
    from api.router import create_app

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
    import uvicorn

    from api.router import create_app
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


async def cmd_health(cfg: dict) -> None:
    """Quick health check."""
    import httpx
    host = cfg["api"]["host"]
    port = cfg["api"]["port"]
    url = f"http://{host}:{port}/api/health"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                print(f"Status:  {data['status']}")
                print(f"Version: {data['version']}")
                print(f"Uptime:  {data['uptime_seconds']:.1f}s")
            else:
                print(f"Unhealthy: HTTP {resp.status_code}")
                sys.exit(1)
    except Exception as e:
        print(f"Cannot reach API: {e}")
        print("Is FlowCore running? (python3 flowcore.py serve)")
        sys.exit(1)


def cmd_version(cfg: dict) -> None:
    """Print version info."""
    platform = detect_platform()
    print(f"FlowCore {cfg['app']['version']}")
    print(f"  Python: {platform['python_version']}")
    print(f"  Platform: {platform['os_name']}")
    print(f"  Termux: {platform['termux']}")
    print(f"  Android: {platform['android']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="FlowCore CLI")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("serve", help="Start the API server")
    subparsers.add_parser("run", help="Start full application (API + scheduler + agents)")
    subparsers.add_parser("health", help="Quick health check")
    subparsers.add_parser("version", help="Print version info")
    subparsers.add_parser("selftest", help="Validate the entire installation")

    args = parser.parse_args()

    cfg = get_config()
    platform = detect_platform()

    if args.command == "serve":
        asyncio.run(cmd_serve(cfg, platform))
    elif args.command == "run":
        asyncio.run(cmd_run(cfg, platform))
    elif args.command == "health":
        asyncio.run(cmd_health(cfg))
    elif args.command == "version":
        cmd_version(cfg)
    elif args.command == "selftest":
        cmd_selftest()
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
