"""Tests for runtime.market_intelligence.news._fetch_news's link
extraction -- the frontend only renders a news item as clickable when
canonical_url is a real http(s) URL (see web/index.html's renderNewsList),
so a gap in this fallback chain silently degrades every affected item to
"nothing happens when you tap it".
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.market_intelligence.news import _fetch_news  # noqa: E402


def _yfinance_item(content: dict, **extra) -> dict:
    return {"content": content, **extra}


class TestFetchNewsLinkExtraction:
    def _fetch_with(self, item: dict) -> dict:
        fake_ticker = MagicMock()
        fake_ticker.news = [item]
        with patch("yfinance.Ticker", return_value=fake_ticker):
            results = _fetch_news("^GSPC")
        assert len(results) == 1
        return results[0]

    def test_canonical_url_dict_with_url_key(self):
        item = _yfinance_item({"title": "Headline", "canonicalUrl": {"url": "https://example.com/a"}})
        assert self._fetch_with(item)["link"] == "https://example.com/a"

    def test_canonical_url_dict_with_raw_key(self):
        item = _yfinance_item({"title": "Headline", "canonicalUrl": {"raw": "https://example.com/b"}})
        assert self._fetch_with(item)["link"] == "https://example.com/b"

    def test_falls_back_to_click_through_url(self):
        item = _yfinance_item(
            {
                "title": "Headline",
                "canonicalUrl": None,
                "clickThroughUrl": {"url": "https://example.com/c"},
            }
        )
        assert self._fetch_with(item)["link"] == "https://example.com/c"

    def test_falls_back_to_preview_url(self):
        item = _yfinance_item({"title": "Headline", "previewUrl": "https://example.com/d"})
        assert self._fetch_with(item)["link"] == "https://example.com/d"

    def test_falls_back_to_top_level_link(self):
        item = _yfinance_item({"title": "Headline"}, link="https://example.com/e")
        assert self._fetch_with(item)["link"] == "https://example.com/e"

    def test_no_link_anywhere_is_empty_not_fabricated(self):
        item = _yfinance_item({"title": "Headline"})
        assert self._fetch_with(item)["link"] == ""
