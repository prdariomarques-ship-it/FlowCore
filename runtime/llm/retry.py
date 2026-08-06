"""Generic, provider-agnostic retry wrapper. Used by the Router around
each individual provider attempt, before falling through to the next
provider in the policy's ordered list -- retry handles transient
failures of *one* provider; fallback (in router.py) handles a provider
being down entirely.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

from runtime.llm.models import LLMError

__all__ = ["with_retry"]

T = TypeVar("T")


def with_retry(fn: Callable[[], T], attempts: int = 2, backoff_seconds: float = 1.0) -> T:
    """Retries `fn` up to `attempts` times on LLMError, with a fixed
    backoff between attempts. Re-raises the last error once exhausted.
    Only LLMError (or a subclass) is retried -- a programming error
    (KeyError, TypeError, ...) propagates immediately."""
    last_error: LLMError | None = None
    for attempt in range(attempts):
        try:
            return fn()
        except LLMError as e:
            last_error = e
            if attempt < attempts - 1:
                time.sleep(backoff_seconds)
    assert last_error is not None
    raise last_error
