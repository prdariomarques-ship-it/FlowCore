"""Generic, provider-agnostic retry wrapper. Used by the Router around
each individual provider attempt, before falling through to the next
provider in the policy's ordered list -- retry handles transient
failures of *one* provider; fallback (in router.py) handles a provider
being down entirely.
"""

from __future__ import annotations

import random
import re
import time
from collections.abc import Callable
from typing import TypeVar

from config.loader import get_config
from runtime.llm.models import (
    LLMAuthenticationError,
    LLMBudgetExceededError,
    LLMError,
    LLMModelNotFoundError,
    LLMProviderUnavailableError,
    LLMTimeoutError,
)

__all__ = ["with_retry"]

T = TypeVar("T")

_NON_RETRYABLE_STATUS_CODES = re.compile(r"\b(?:400|401|403|404)\b")
_NON_RETRYABLE_MESSAGES = (
    "invalid api key",
    "invalid request",
    "bad prompt",
    "model not found",
    "not configured",
)


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes", "on"}


def _configured_retry() -> dict[str, bool | int | str]:
    retry = get_config()["llm"]["retry"]
    return {
        "enabled": _as_bool(retry["enabled"]),
        "max_attempts": int(retry["max_attempts"]),
        "backoff": str(retry["backoff"]).lower(),
        "initial_delay_ms": int(retry["initial_delay_ms"]),
        "max_delay_ms": int(retry["max_delay_ms"]),
        "jitter": _as_bool(retry["jitter"]),
    }


def _is_retryable(error: LLMError) -> bool:
    if isinstance(error, (LLMAuthenticationError, LLMModelNotFoundError, LLMBudgetExceededError)):
        return False
    if isinstance(error, LLMTimeoutError):
        return True
    if not isinstance(error, LLMProviderUnavailableError):
        return False

    message = str(error).lower()
    return not _NON_RETRYABLE_STATUS_CODES.search(message) and not any(
        marker in message for marker in _NON_RETRYABLE_MESSAGES
    )


def _delay_seconds(attempt: int, settings: dict[str, bool | int | str]) -> float:
    initial_delay = int(settings["initial_delay_ms"]) / 1000
    max_delay = int(settings["max_delay_ms"]) / 1000
    multiplier = 2**attempt if settings["backoff"] == "exponential" else 1
    delay = min(initial_delay * multiplier, max_delay)
    return random.uniform(0, delay) if settings["jitter"] else delay


def with_retry(fn: Callable[[], T], attempts: int | None = None, backoff_seconds: float | None = None) -> T:
    """Retry transient provider failures according to the configured policy.

    The optional arguments preserve the legacy call surface. When omitted,
    values come from ``config/default.json`` (and its normal local/env
    overlays). A supplied ``backoff_seconds`` keeps the previous fixed,
    no-jitter behavior for callers that explicitly use it.
    """
    settings = _configured_retry()
    effective_attempts = attempts if attempts is not None else int(settings["max_attempts"])
    if not settings["enabled"]:
        effective_attempts = 1
    if effective_attempts < 1:
        raise ValueError("llm.retry.max_attempts must be at least 1")

    if backoff_seconds is not None:
        settings = {
            "backoff": "fixed",
            "initial_delay_ms": int(backoff_seconds * 1000),
            "max_delay_ms": int(backoff_seconds * 1000),
            "jitter": False,
        }

    last_error: LLMError | None = None
    for attempt in range(effective_attempts):
        try:
            return fn()
        except LLMError as e:
            last_error = e
            if not _is_retryable(e) or attempt == effective_attempts - 1:
                raise
            time.sleep(_delay_seconds(attempt, settings))
    assert last_error is not None
    raise last_error
