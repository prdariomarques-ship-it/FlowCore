"""Shared helper for calling async code from sync call sites.

Used wherever a function's existing call sites are synchronous but it
needs to await a coroutine internally (e.g. an async repository method,
RegimeEngine.classify_all()) — without forcing every caller up the stack
to become async too.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Any, Coroutine, TypeVar

_T = TypeVar("_T")


def run_sync(coro: Coroutine[Any, Any, _T]) -> _T:
    """Run *coro* to completion, safe whether or not a loop is already
    running in this thread.

    ``asyncio.run()`` alone raises ``RuntimeError: asyncio.run() cannot be
    called from a running event loop`` when the caller is itself inside an
    async context (a FastAPI request handler, the MCP server's event
    loop). When that happens, fall back to a fresh loop on a separate
    thread instead of failing.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()
