"""Tests for the evaluate_alerts() TTL cache (runtime/market_intelligence/alerts.py).

Real-device evidence: FlowCore Mobile's /api/market/overview timed out on
both the Cloudflare and Tailscale routes. evaluate_alerts() did a live
~11-way concurrent yfinance sweep on EVERY request purely to keep the
alerts table warm (its own docstring) -- the caller discards its return
value and reads alerts via list_alerts() (a separate DB read) instead.
These tests cover the TTL cache added to stop that live sweep from
running on every single request.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.market_intelligence.alerts import (  # noqa: E402
    ALERT_DEFAULTS,
    evaluate_alerts,
    reset_evaluation_cache,
)


def _no_events(source):
    return []


class TestEvaluationCache:
    def setup_method(self):
        reset_evaluation_cache()

    def test_second_call_within_ttl_skips_the_sweep_entirely(self, tmp_path):
        db = str(tmp_path / "alerts.db")
        with patch("runtime.market_intelligence.alerts._observe", side_effect=_no_events) as mocked:
            evaluate_alerts(db_path=db)
            assert mocked.call_count == len(ALERT_DEFAULTS)
            result = evaluate_alerts(db_path=db)
        assert result == []
        assert mocked.call_count == len(ALERT_DEFAULTS)  # unchanged -- second call never touched an observer

    def test_different_db_paths_get_independent_caches(self, tmp_path):
        db_a = str(tmp_path / "a.db")
        db_b = str(tmp_path / "b.db")
        with patch("runtime.market_intelligence.alerts._observe", side_effect=_no_events) as mocked:
            evaluate_alerts(db_path=db_a)
            assert mocked.call_count == len(ALERT_DEFAULTS)
            evaluate_alerts(db_path=db_b)
        # A second, distinct db_path is not covered by db_a's cache entry --
        # its own sweep still ran.
        assert mocked.call_count == len(ALERT_DEFAULTS) * 2

    def test_reset_forces_a_fresh_sweep(self, tmp_path):
        db = str(tmp_path / "alerts.db")
        with patch("runtime.market_intelligence.alerts._observe", side_effect=_no_events) as mocked:
            evaluate_alerts(db_path=db)
            reset_evaluation_cache(db)
            evaluate_alerts(db_path=db)
        assert mocked.call_count == len(ALERT_DEFAULTS) * 2

    def test_reset_all_clears_every_db_path(self, tmp_path):
        db_a = str(tmp_path / "a.db")
        db_b = str(tmp_path / "b.db")
        with patch("runtime.market_intelligence.alerts._observe", side_effect=_no_events) as mocked:
            evaluate_alerts(db_path=db_a)
            evaluate_alerts(db_path=db_b)
            reset_evaluation_cache()  # no db_path -- clears both
            evaluate_alerts(db_path=db_a)
        assert mocked.call_count == len(ALERT_DEFAULTS) * 3

    def test_ttl_expiry_allows_a_fresh_sweep(self, tmp_path):
        db = str(tmp_path / "alerts.db")
        with patch("runtime.market_intelligence.alerts.time.monotonic", return_value=1000.0):
            with patch("runtime.market_intelligence.alerts._observe", side_effect=_no_events) as mocked:
                evaluate_alerts(db_path=db)
        # 61s later -- past the 60s TTL
        with patch("runtime.market_intelligence.alerts.time.monotonic", return_value=1061.0):
            with patch("runtime.market_intelligence.alerts._observe", side_effect=_no_events) as mocked:
                evaluate_alerts(db_path=db)
                assert mocked.call_count == len(ALERT_DEFAULTS)
