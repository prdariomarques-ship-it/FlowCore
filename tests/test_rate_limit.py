"""Tests for runtime/rate_limit.py -- the coarse in-memory throttle
protecting CPU/network-heavy public endpoints (/api/ask, /api/agent/run)
that had no rate limiting at all before this, unlike /api/auth/login's
DB-backed OWASP throttle (storage/tenant_repo.py, a different mechanism
for a different purpose: brute-force protection, not CPU protection).
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.rate_limit import check_rate_limit, reset_rate_limit  # noqa: E402


class TestCheckRateLimit:
    def setup_method(self):
        reset_rate_limit()

    def test_allows_requests_under_the_limit(self):
        for _ in range(5):
            assert check_rate_limit("k", max_requests=5, window_seconds=60) is True

    def test_blocks_the_request_that_exceeds_the_limit(self):
        for _ in range(5):
            check_rate_limit("k", max_requests=5, window_seconds=60)
        assert check_rate_limit("k", max_requests=5, window_seconds=60) is False

    def test_different_keys_have_independent_budgets(self):
        for _ in range(5):
            check_rate_limit("a", max_requests=5, window_seconds=60)
        assert check_rate_limit("a", max_requests=5, window_seconds=60) is False
        assert check_rate_limit("b", max_requests=5, window_seconds=60) is True

    def test_old_requests_age_out_of_the_window(self):
        with patch("runtime.rate_limit.time.time", return_value=1000.0):
            for _ in range(5):
                check_rate_limit("k", max_requests=5, window_seconds=60)
        # 61s later -- the whole earlier batch has aged out of a 60s window
        with patch("runtime.rate_limit.time.time", return_value=1061.0):
            assert check_rate_limit("k", max_requests=5, window_seconds=60) is True

    def test_a_throttled_caller_does_not_extend_their_own_block(self):
        # Retrying while blocked must not count as a new attempt -- only
        # allowed requests are recorded, so hammering the limiter can't
        # push the window forward and keep someone blocked forever.
        with patch("runtime.rate_limit.time.time", return_value=1000.0):
            for _ in range(5):
                check_rate_limit("k", max_requests=5, window_seconds=60)
        with patch("runtime.rate_limit.time.time", return_value=1030.0):
            for _ in range(10):  # hammer while still inside the window
                assert check_rate_limit("k", max_requests=5, window_seconds=60) is False
        with patch("runtime.rate_limit.time.time", return_value=1061.0):
            assert check_rate_limit("k", max_requests=5, window_seconds=60) is True


class TestResetRateLimit:
    def test_reset_one_key(self):
        for _ in range(5):
            check_rate_limit("k", max_requests=5, window_seconds=60)
        assert check_rate_limit("k", max_requests=5, window_seconds=60) is False
        reset_rate_limit("k")
        assert check_rate_limit("k", max_requests=5, window_seconds=60) is True

    def test_reset_all(self):
        for key in ("a", "b"):
            for _ in range(5):
                check_rate_limit(key, max_requests=5, window_seconds=60)
        reset_rate_limit()
        assert check_rate_limit("a", max_requests=5, window_seconds=60) is True
        assert check_rate_limit("b", max_requests=5, window_seconds=60) is True
