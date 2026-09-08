"""Renders the market close data into a square PNG card (Instagram-ready),
using Pillow — a lightweight, pure-Python-friendly choice with real
Termux/Android packages available (`pkg install python-pillow`), unlike
a headless-browser render which is impractical on that target.

Fonts are bundled under assets/fonts/ so this never depends on a system
font being present (see assets/fonts/LICENSE.txt — Liberation Sans,
SIL OFL 1.1).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from textwrap import wrap
from typing import Any

from PIL import Image, ImageDraw, ImageFont

_ROOT = Path(__file__).resolve().parent.parent.parent
_FONT_DIR = _ROOT / "assets" / "fonts"

_SIZE = 1080
_BG = (10, 15, 30)          # #0a0f1e
_PANEL = (17, 24, 39)       # #111827
_BORDER = (30, 58, 95)      # #1e3a5f
_ACCENT = (0, 212, 255)     # #00d4ff
_ACCENT2 = (124, 58, 237)   # #7c3aed
_TEXT = (226, 232, 240)     # #e2e8f0
_TEXT2 = (148, 163, 184)    # #94a3b8

_MAX_HIGHLIGHTS = 6
_WRAP_CHARS = 44


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(_FONT_DIR / name), size)


def render_close_card(
    lines: list[str],
    generated_at: str,
    output_path: str | Path,
) -> str:
    """Draw the market-close card and save it as a PNG. Returns the path.

    *lines* should already be the deterministic market lines from
    build_briefing()/build_market_close() — no LLM, no fabricated data.
    Only the first _MAX_HIGHLIGHTS (after filtering the REGIME: line,
    which reads poorly on a card) are shown; the rest stay in the text
    versions.
    """
    regular = _font("LiberationSans-Regular.ttf", 28)
    bold = _font("LiberationSans-Bold.ttf", 30)
    title_font = _font("LiberationSans-Bold.ttf", 56)
    subtitle_font = _font("LiberationSans-Regular.ttf", 30)
    date_font = _font("LiberationSans-Regular.ttf", 26)
    footer_font = _font("LiberationSans-Regular.ttf", 22)

    img = Image.new("RGB", (_SIZE, _SIZE), _BG)
    draw = ImageDraw.Draw(img)

    # Header
    draw.text((60, 70), "FlowCore", font=title_font, fill=_ACCENT)
    draw.text((60, 145), "FECHAMENTO DE MERCADO", font=subtitle_font, fill=_TEXT2)

    date_label = datetime.fromisoformat(generated_at).strftime("%d/%m/%Y")
    date_w = draw.textlength(date_label, font=date_font)
    draw.text((_SIZE - 60 - date_w, 90), date_label, font=date_font, fill=_TEXT2)

    draw.line([(60, 210), (_SIZE - 60, 210)], fill=_BORDER, width=2)

    # Highlights panel
    highlights = [line for line in lines if not line.startswith("REGIME:")][:_MAX_HIGHLIGHTS]
    if not highlights:
        highlights = ["Sem dados disponíveis neste fechamento."]

    panel_top = 250
    panel_bottom = _SIZE - 140
    draw.rounded_rectangle(
        [(60, panel_top), (_SIZE - 60, panel_bottom)],
        radius=24, fill=_PANEL, outline=_BORDER, width=2,
    )

    y = panel_top + 40
    for raw_line in highlights:
        stripped = raw_line.strip()
        is_subitem = raw_line.startswith("  ")
        wrapped = wrap(stripped, width=_WRAP_CHARS) or [stripped]
        font = regular if is_subitem else bold
        color = _TEXT2 if is_subitem else _TEXT
        for i, part in enumerate(wrapped):
            prefix = ("· " if is_subitem else "• ") if i == 0 else "  "
            draw.text((100, y), f"{prefix}{part}", font=font, fill=color)
            y += 42
        y += 10
        if y > panel_bottom - 60:
            break

    # Footer
    footer = "Dados públicos (BCB, Tesouro dos EUA, Yahoo Finance) — não é recomendação de investimento."
    draw.text((60, _SIZE - 100), footer, font=footer_font, fill=_TEXT2)
    draw.text(
        (60, _SIZE - 65),
        "flowcore.admissaoazusa.com.br",
        font=footer_font,
        fill=_ACCENT2,
    )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, format="PNG")
    return str(output_path)
