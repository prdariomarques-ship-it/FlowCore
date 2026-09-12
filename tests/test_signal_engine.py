"""Tests for scripts/signal_engine.py -- turns real fired alerts
(runtime/market_intelligence/alerts.py's evaluate_alerts()) into real
Telegram messages. No invented signal logic here, just message
formatting and the send loop's error handling.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.signal_engine import check_and_send_signals, format_alert_message  # noqa: E402


def _alert(**overrides):
    base = {
        "rule": "sp500_daily_drop",
        "source": "sp500",
        "severity": "critical",
        "label": "S&P 500 cai mais de 3% no dia",
        "payload": {"value": 4200.5, "delta_pct": -3.4},
        "fired_at": "2026-01-01T00:00:00+00:00",
    }
    base.update(overrides)
    return base


class TestFormatAlertMessage:
    def test_includes_label_value_and_delta(self):
        msg = format_alert_message(_alert())
        assert "S&amp;P 500" in msg or "S&P 500" in msg
        assert "4200.50" in msg
        assert "-3.40%" in msg

    def test_critical_severity_gets_red_emoji(self):
        assert "🔴" in format_alert_message(_alert(severity="critical"))

    def test_warning_severity_gets_yellow_emoji(self):
        assert "🟡" in format_alert_message(_alert(severity="warning"))

    def test_missing_delta_is_omitted_not_fabricated(self):
        msg = format_alert_message(_alert(payload={"value": 25.5}))
        assert "Variação" not in msg
        assert "25.50" in msg

    def test_missing_value_is_omitted_not_fabricated(self):
        msg = format_alert_message(_alert(payload={}))
        assert "Valor atual" not in msg

    def test_html_escapes_the_label(self):
        msg = format_alert_message(_alert(label="Test <script>alert(1)</script>"))
        assert "<script>" not in msg


class TestCheckAndSendSignals:
    def test_sends_one_message_per_fired_alert(self):
        alerts = [_alert(rule="a"), _alert(rule="b")]
        with (
            patch("runtime.market_intelligence.alerts.evaluate_alerts", return_value=alerts),
            patch("runtime.telegram.send_message") as mock_send,
        ):
            sent = check_and_send_signals()
        assert mock_send.call_count == 2
        assert [a["rule"] for a in sent] == ["a", "b"]

    def test_no_fired_alerts_sends_nothing(self):
        with (
            patch("runtime.market_intelligence.alerts.evaluate_alerts", return_value=[]),
            patch("runtime.telegram.send_message") as mock_send,
        ):
            sent = check_and_send_signals()
        assert sent == []
        mock_send.assert_not_called()

    def test_telegram_not_configured_stops_without_raising(self):
        from runtime.telegram import TelegramNotConfiguredError

        with (
            patch("runtime.market_intelligence.alerts.evaluate_alerts", return_value=[_alert()]),
            patch("runtime.telegram.send_message", side_effect=TelegramNotConfiguredError("no token")),
        ):
            sent = check_and_send_signals()  # must not raise
        assert sent == []

    def test_one_failed_send_does_not_block_the_rest(self):
        from runtime.telegram import TelegramError

        alerts = [_alert(rule="a"), _alert(rule="b")]
        with (
            patch("runtime.market_intelligence.alerts.evaluate_alerts", return_value=alerts),
            patch("runtime.telegram.send_message", side_effect=[TelegramError("boom"), {"ok": True}]),
        ):
            sent = check_and_send_signals()
        assert [a["rule"] for a in sent] == ["b"]
