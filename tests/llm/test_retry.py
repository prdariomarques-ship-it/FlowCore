"""Tests for runtime.llm.retry.with_retry."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestWithRetry:
    def test_succeeds_first_try_no_retry_needed(self):
        from runtime.llm.retry import with_retry

        calls = []

        def fn():
            calls.append(1)
            return "ok"

        assert with_retry(fn, attempts=3, backoff_seconds=0) == "ok"
        assert len(calls) == 1

    def test_retries_on_llm_error_then_succeeds(self):
        from runtime.llm import LLMProviderUnavailableError
        from runtime.llm.retry import with_retry

        calls = []

        def fn():
            calls.append(1)
            if len(calls) < 2:
                raise LLMProviderUnavailableError("transient")
            return "ok"

        assert with_retry(fn, attempts=3, backoff_seconds=0) == "ok"
        assert len(calls) == 2

    def test_exhausts_attempts_and_raises_last_error(self):
        from runtime.llm import LLMProviderUnavailableError
        from runtime.llm.retry import with_retry

        calls = []

        def fn():
            calls.append(1)
            raise LLMProviderUnavailableError(f"fail {len(calls)}")

        with pytest.raises(LLMProviderUnavailableError, match="fail 2"):
            with_retry(fn, attempts=2, backoff_seconds=0)
        assert len(calls) == 2

    def test_non_llm_error_propagates_immediately_no_retry(self):
        from runtime.llm.retry import with_retry

        calls = []

        def fn():
            calls.append(1)
            raise ValueError("not retryable")

        with pytest.raises(ValueError, match="not retryable"):
            with_retry(fn, attempts=3, backoff_seconds=0)
        assert len(calls) == 1
