#!/usr/bin/env python3
"""FlowCore — Main entry point.

Usage:
    python3 flowcore.py serve        Start the API server
    python3 flowcore.py run          Start the full application (API + scheduler + agents)
    python3 flowcore.py health       Quick health check
    python3 flowcore.py version      Print version
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to Python path so imports work regardless of CWD.
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.loader import get_config
from runtime.core import FlowCoreRuntime, detect_platform
from api.router import create_app
from loguru import logger


async def cmd_serve(cfg: dict, platform: dict) -> None:
    """Start the FastAPI server."""
    import uvicorn

    host = cfg["api"]["host"]
    port = cfg["api"]["port"]

    logger.info("Starting FlowCore API on {}:{}", host, port)
    app = create_app(version=cfg["app"]["version"], platform_info=platform)

    # SECURITY: bind to localhost only
    if host == "0.0.0.0":
        logger.warning("API is bound to 0.0.0.0 — accessible from network")
        logger.warning("Consider setting api.host = 127.0.0.1 for security")

    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


async def cmd_run(cfg: dict, platform: dict) -> None:
    """Start the full application (API + scheduler + agents)."""
    import uvicorn

    logger.info("Starting FlowCore full application...")

    # Start runtime
    rt = FlowCoreRuntime(ROOT)
    await rt.start()

    # Create app
    app = create_app(version=cfg["app"]["version"], platform_info=platform)

    # Start server
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
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
