"""Tests for runtime.llm.retry.with_retry."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestWithRetry:
    @staticmethod
    def _config(**overrides):
        retry = {
            "enabled": True,
            "max_attempts": 3,
            "backoff": "exponential",
            "initial_delay_ms": 100,
            "max_delay_ms": 500,
            "jitter": False,
        }
        retry.update(overrides)
        return {"llm": {"retry": retry}}

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

    def test_non_recoverable_error_is_not_retried(self, monkeypatch):
        from runtime.llm import LLMAuthenticationError
        from runtime.llm import retry

        monkeypatch.setattr(retry, "get_config", lambda: self._config())
        calls = []

        def fn():
            calls.append(1)
            raise LLMAuthenticationError("invalid API key")

        with pytest.raises(LLMAuthenticationError):
            retry.with_retry(fn)
        assert len(calls) == 1

    def test_max_attempts_one_does_not_retry(self, monkeypatch):
        from runtime.llm import LLMProviderUnavailableError
        from runtime.llm import retry

        monkeypatch.setattr(retry, "get_config", lambda: self._config(max_attempts=1))
        calls = []

        def fn():
            calls.append(1)
            raise LLMProviderUnavailableError("503 unavailable")

        with pytest.raises(LLMProviderUnavailableError):
            retry.with_retry(fn)
        assert len(calls) == 1

    def test_disabled_retry_does_not_retry(self, monkeypatch):
        from runtime.llm import LLMProviderUnavailableError
        from runtime.llm import retry

        monkeypatch.setattr(retry, "get_config", lambda: self._config(enabled=False))
        calls = []

        def fn():
            calls.append(1)
            raise LLMProviderUnavailableError("503 unavailable")

        with pytest.raises(LLMProviderUnavailableError):
            retry.with_retry(fn)
        assert len(calls) == 1

    def test_exponential_backoff_uses_configured_delays(self, monkeypatch):
        from runtime.llm import LLMProviderUnavailableError
        from runtime.llm import retry

        monkeypatch.setattr(retry, "get_config", lambda: self._config(max_attempts=3, max_delay_ms=150))
        delays = []
        monkeypatch.setattr(retry.time, "sleep", delays.append)
        calls = []

        def fn():
            calls.append(1)
            if len(calls) < 3:
                raise LLMProviderUnavailableError("503 unavailable")
            return "ok"

        assert retry.with_retry(fn) == "ok"
        assert delays == [0.1, 0.15]

    def test_jitter_enabled_randomizes_delay(self, monkeypatch):
        from runtime.llm import LLMProviderUnavailableError
        from runtime.llm import retry

        monkeypatch.setattr(retry, "get_config", lambda: self._config(max_attempts=2, jitter=True))
        intervals = []
        delays = []
        monkeypatch.setattr(retry.random, "uniform", lambda start, end: intervals.append((start, end)) or 0.03)
        monkeypatch.setattr(retry.time, "sleep", delays.append)
        calls = []

        def fn():
            calls.append(1)
            if len(calls) == 1:
                raise LLMProviderUnavailableError("503 unavailable")
            return "ok"

        assert retry.with_retry(fn) == "ok"
        assert intervals == [(0, 0.1)]
        assert delays == [0.03]

    def test_jitter_disabled_uses_full_delay(self, monkeypatch):
        from runtime.llm import LLMProviderUnavailableError
        from runtime.llm import retry

        monkeypatch.setattr(retry, "get_config", lambda: self._config(max_attempts=2, jitter=False))
        delays = []
        monkeypatch.setattr(retry.time, "sleep", delays.append)

        calls = []

        def fn():
            calls.append(1)
            if len(calls) == 1:
                raise LLMProviderUnavailableError("503 unavailable")
            return "ok"

        assert retry.with_retry(fn) == "ok"
        assert delays == [0.1]
