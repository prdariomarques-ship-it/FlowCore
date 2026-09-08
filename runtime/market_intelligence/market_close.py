"""Market close package — end-of-day digest built from the same real
data pipeline as build_briefing() (curve, FX, equities, regime, news),
rendered into two audience-tailored texts and persisted to disk.

busca os dados -> interpreta -> cruza informações: delegated to
build_briefing(), already deterministic and network-failure-tolerant.
This module only adds the "monta o texto" (client + Instagram) and
"salva tudo organizado" steps — no LLM required, same as the briefing.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from runtime.market_intelligence.briefing import build_briefing

_HISTORY_DIR = Path.home() / ".flowcore" / "market_close"

_INSTAGRAM_MAX_CHARS = 2200  # Instagram's hard caption limit


def _client_version(lines: list[str], generated_at: str) -> str:
    date_label = datetime.fromisoformat(generated_at).strftime("%d/%m/%Y %H:%M UTC")
    body = "\n".join(f"• {line}" for line in lines) if lines else "• Sem dados disponíveis neste fechamento."
    return (
        f"📊 FECHAMENTO DE MERCADO — {date_label}\n\n"
        f"{body}\n\n"
        f"—\n"
        f"Relatório gerado automaticamente pelo FlowCore a partir de fontes públicas "
        f"(Banco Central, Tesouro dos EUA, Yahoo Finance). Não constitui recomendação de investimento."
    )


def _instagram_version(lines: list[str], generated_at: str) -> str:
    date_label = datetime.fromisoformat(generated_at).strftime("%d/%m")
    highlights = lines[:5] if lines else ["Sem dados disponíveis hoje."]
    body = "\n".join(f"▪️ {line}" for line in highlights)
    text = (
        f"📈 Fechamento de mercado — {date_label}\n\n"
        f"{body}\n\n"
        f"#mercadofinanceiro #investimentos #economia #bolsadevalores"
    )
    return text[: _INSTAGRAM_MAX_CHARS]


def _persist(package: dict[str, Any]) -> str | None:
    """Save the package to disk, keyed by date. Never raises — a write
    failure degrades to a skipped save, not a broken close package."""
    try:
        _HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        date_key = datetime.fromisoformat(package["generated_at"]).strftime("%Y-%m-%d")
        path = _HISTORY_DIR / f"{date_key}.json"
        path.write_text(json.dumps(package, ensure_ascii=False, indent=2))
        return str(path)
    except OSError:
        return None


def _render_card(lines: list[str], generated_at: str) -> str | None:
    """Render the visual card (cria os cards). Never raises — Pillow is
    an optional API-tier dependency; without it (or on any render
    failure) the text versions still stand on their own."""
    try:
        from runtime.market_intelligence.market_close_card import render_close_card
        date_key = datetime.fromisoformat(generated_at).strftime("%Y-%m-%d")
        path = _HISTORY_DIR / f"{date_key}.png"
        return render_close_card(lines, generated_at, path)
    except Exception:
        return None


def build_market_close() -> dict[str, Any]:
    """Prepare o fechamento de mercado: real data, two rendered texts,
    a visual card, all saved under ~/.flowcore/market_close/<date>.*"""
    briefing = build_briefing()
    lines = briefing["lines"]
    generated_at = briefing["generated_at"]

    package = {
        "generated_at": generated_at,
        "raw_lines": lines,
        "client_version": _client_version(lines, generated_at),
        "instagram_version": _instagram_version(lines, generated_at),
    }
    package["card_path"] = _render_card(lines, generated_at)
    package["saved_to"] = _persist(package)
    return package
