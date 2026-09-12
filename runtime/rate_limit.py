"""Coarse in-memory rate limiting for CPU/network-heavy endpoints (chat,
autonomous agent runs) on this single-process Termux deployment.

Distinct from storage/tenant_repo.py's login throttling: that one is a
DB-backed, OWASP-style failed-attempt counter scoped to brute-force
protection on /api/auth/login. This one only exists to stop a public
endpoint from being hammered into pegging the phone's CPU -- every
request counts, success or failure, and state is plain in-memory
(correct only because this runs as one process; would need a shared
store behind multiple workers/instances).
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

_HISTORY: dict[str, deque[float]] = defaultdict(deque)


def check_rate_limit(key: str, max_requests: int, window_seconds: float) -> bool:
    """True if `key` may proceed now; False if it should be throttled.

    Records the attempt only when allowed, so a caller stuck at the
    limit doesn't keep pushing their own window forward by retrying --
    they become eligible again as soon as their oldest counted request
    ages out, not later."""
    now = time.time()
    history = _HISTORY[key]
    while history and history[0] < now - window_seconds:
        history.popleft()
    if len(history) >= max_requests:
        return False
    history.append(now)
    return True


def reset_rate_limit(key: str | None = None) -> None:
    """Test-only escape hatch. None clears every key."""
    if key is None:
        _HISTORY.clear()
    else:
        _HISTORY.pop(key, None)
