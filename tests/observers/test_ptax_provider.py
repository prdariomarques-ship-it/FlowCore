"""Tests for runtime.observers.providers.ptax_provider -- the Banco
Central PTAX fallback for the "Câmbio" market group's single indicator.

Nothing here makes a real network call: urllib.request.urlopen is always
mocked, same convention as tests/observers/test_yfinance_provider.py.
"""

from __future__ import annotations

import datetime as _dt
import json
import sys
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.observers.base import ObserverError  # noqa: E402


def _response(payload: dict):
    body = json.dumps(payload).encode("utf-8")
    return BytesIO(body)


class TestFetchDay:
    def test_returns_last_quote_of_the_day(self):
        from runtime.observers.providers.ptax_provider import _fetch_day

        payload = {"value": [{"cotacaoVenda": 5.10}, {"cotacaoVenda": 5.12}]}
        with patch("urllib.request.urlopen", return_value=_response(payload)):
            assert _fetch_day(_dt.date(2024, 1, 10)) == 5.12

    def test_none_when_no_quotation_published(self):
        from runtime.observers.providers.ptax_provider import _fetch_day

        with patch("urllib.request.urlopen", return_value=_response({"value": []})):
            assert _fetch_day(_dt.date(2024, 1, 6)) is None  # a Saturday

    def test_raises_observer_error_on_network_failure(self):
        from runtime.observers.providers.ptax_provider import _fetch_day

        with patch("urllib.request.urlopen", side_effect=OSError("network down")):
            with pytest.raises(ObserverError):
                _fetch_day(_dt.date(2024, 1, 10))


class TestFetchUsdbrlPtax:
    def test_success_with_two_consecutive_business_days(self):
        from runtime.observers.providers.ptax_provider import fetch_usdbrl_ptax

        with patch("runtime.observers.providers.ptax_provider._fetch_day", side_effect=[5.20, 5.18]):
            result = fetch_usdbrl_ptax()
        assert result == {"symbol": "USDBRL=PTAX", "price": 5.20, "previous_close": 5.18}

    def test_skips_weekend_with_no_quotation(self):
        from runtime.observers.providers.ptax_provider import fetch_usdbrl_ptax

        # Today (Monday) has a quote, Sunday and Saturday don't, Friday does.
        with patch(
            "runtime.observers.providers.ptax_provider._fetch_day",
            side_effect=[5.20, None, None, 5.15],
        ):
            result = fetch_usdbrl_ptax()
        assert result == {"symbol": "USDBRL=PTAX", "price": 5.20, "previous_close": 5.15}

    def test_only_one_day_found_has_no_previous_close(self):
        from runtime.observers.providers.ptax_provider import fetch_usdbrl_ptax

        with patch(
            "runtime.observers.providers.ptax_provider._fetch_day",
            side_effect=[5.20] + [None] * 9,
        ):
            result = fetch_usdbrl_ptax()
        assert result == {"symbol": "USDBRL=PTAX", "price": 5.20, "previous_close": None}

    def test_raises_when_nothing_found_in_lookback_window(self):
        from runtime.observers.providers.ptax_provider import fetch_usdbrl_ptax

        with patch("runtime.observers.providers.ptax_provider._fetch_day", return_value=None):
            with pytest.raises(ObserverError):
                fetch_usdbrl_ptax()
