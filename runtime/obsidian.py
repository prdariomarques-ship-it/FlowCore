"""runtime/obsidian.py — Obsidian vault sync for FlowCore Daily Notes."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

_DEFAULT_VAULT = Path("/storage/emulated/0/Obsidian/obsidian_updated_vault")
_DAILY_FOLDER = "Daily Notes"
_CFG_PATH = Path.home() / ".flowcore" / "obsidian.json"


def _load_cfg() -> dict:
    if _CFG_PATH.exists():
        try:
            return json.loads(_CFG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _vault_path() -> Path:
    return Path(_load_cfg().get("vault_path", str(_DEFAULT_VAULT)))


def _fmt_num(v: Any, fmt: str = "+.2f", suffix: str = "") -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):{fmt}}{suffix}"
    except (TypeError, ValueError):
        return str(v)


def _brief_to_markdown(brief: dict[str, Any]) -> str:
    """Convert a build_brief() result to Obsidian Markdown."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sections = brief.get("sections", {})
    lines: list[str] = []

    lines.append(f"# Brief Matinal — {today}")
    lines.append(f"*Gerado às {brief.get('generated_at', '')[:16]} UTC via FlowCore*")
    lines.append("")

    if brief.get("llm_polish"):
        lines.append("## Resumo")
        lines.append(brief["llm_polish"])
        lines.append("")

    y = sections.get("yield", {})
    if y.get("ok"):
        lines.append("## Curva de Juros (EUA)")
        lines.append(f"- Estado: **{y.get('state', '—')}** | Forma: {y.get('shape', '—')}")
        slope = y.get("slope_10y_2y")
        if slope is not None:
            lines.append(f"- Inclinação 10Y-2Y: **{slope} bps**")
        if y.get("interpretation"):
            lines.append(f"- {y['interpretation']}")
        for pt in y.get("points", []):
            if pt.get("yield_pct") is not None:
                lines.append(f"  - {pt['label']}: {pt['yield_pct']}%")
        lines.append("")

    fx = sections.get("fx", {})
    if fx.get("ok"):
        lines.append("## Câmbio / DXY")
        lines.append(f"- DXY: **{_fmt_num(fx.get('dxy_delta'), suffix='%')}**")
        for pair in fx.get("pairs", [])[:4]:
            if pair.get("level") is not None:
                d = _fmt_num(pair.get("delta_pct_1d"), suffix="%")
                lines.append(f"  - {pair['name']}: {pair['level']:.4f} ({d})")
        lines.append("")

    reg = sections.get("regime", {})
    if reg.get("ok") and reg.get("signals"):
        lines.append("## Regime de Mercado")
        for s in reg["signals"]:
            val_str = f" ({_fmt_num(s.get('value'))})" if s.get("value") is not None else ""
            lines.append(f"- {s['name']}: **{s['status']}**{val_str}")
        lines.append("")

    mac = sections.get("macro", {})
    if mac.get("ok") and mac.get("dimensions"):
        lines.append("## Macro Score")
        for dim in mac["dimensions"]:
            val_str = _fmt_num(dim.get("value"))
            lines.append(f"- {dim['dimension']}: **{val_str}** "
                         f"({dim.get('status', '')} {dim.get('trend', '')})")
        lines.append("")

    news = sections.get("news", {})
    if news.get("ok") and news.get("top"):
        lines.append(f"## Notícias ({news.get('total', 0)} itens)")
        for item in news["top"][:5]:
            lines.append(f"- [{item['category']}] {item['headline']}")
        lines.append("")

    alts = sections.get("alerts", {})
    if alts.get("ok") and alts.get("alerts"):
        lines.append("## Alertas Ativos")
        for a in alts["alerts"]:
            lines.append(f"- {a.get('label', str(a))}")
        lines.append("")

    lines.append("---")
    lines.append("*FlowCore · DarioOS*")
    return "\n".join(lines)


class ObsidianSync:
    def __init__(self, vault: Path | None = None) -> None:
        self.vault = vault or _vault_path()
        self.daily_folder = self.vault / _DAILY_FOLDER

    def vault_exists(self) -> bool:
        return self.vault.exists()

    def write_daily_note(self, content: str, for_date: date | None = None) -> Path:
        today = for_date or date.today()
        self.daily_folder.mkdir(parents=True, exist_ok=True)
        note_path = self.daily_folder / f"{today.isoformat()}.md"
        if note_path.exists():
            existing = note_path.read_text(encoding="utf-8")
            if content.strip() not in existing:
                note_path.write_text(existing + "\n\n---\n\n" + content, encoding="utf-8")
        else:
            note_path.write_text(content, encoding="utf-8")
        return note_path

    def write_brief(self, brief: dict[str, Any]) -> dict[str, Any]:
        if not self.vault_exists():
            return {"written": False, "reason": f"vault not found: {self.vault}"}
        try:
            md = _brief_to_markdown(brief)
            path = self.write_daily_note(md)
            return {"written": True, "path": str(path)}
        except Exception as exc:
            return {"written": False, "reason": str(exc)}

    def status(self) -> dict[str, Any]:
        return {
            "vault": str(self.vault),
            "vault_exists": self.vault_exists(),
            "daily_notes_folder": str(self.daily_folder),
        }
