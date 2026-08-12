"""Notifications dispatcher — builds and sends Markdown alerts to Telegram or local fallback file."""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone


class TelegramBotDispatcher:
    """Dispatches real-estate opportunity notifications and alerts."""

    def __init__(self, bot_token: str | None = None, chat_id: str | None = None) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.fallback_file = "/tmp/radar_notifications_log.txt"

    def format_alert_markdown(self, prop: dict) -> str:
        """Construct high-fidelity Markdown notification with deep links."""
        title = prop.get("title", "Novo Imóvel")
        city = prop.get("city", "Cidade")
        state = prop.get("state", "UF")
        appraisal = prop.get("appraisal_value", 0.0)
        minimum_bid = prop.get("minimum_bid", 0.0)
        discount = prop.get("discount_percent", 0.0)
        score = prop.get("score", 0.0)
        risk = prop.get("risk_level", "MEDIUM")
        doc_url = prop.get("document_url", "https://venda-imoveis.caixa.gov.br")

        msg = (
            f"🚨 *NOVA OPORTUNIDADE DETECTADA — RADAR IMOBILIÁRIO AI* 🚨\n\n"
            f"🏠 *Imóvel:* {title}\n"
            f"📍 *Localização:* {city}/{state}\n"
            f"📊 *Opportunity Score:* {score}/100\n"
            f"⚠️ *Risco:* {risk}\n\n"
            f"💰 *Avaliação Original:* R$ {appraisal:,.2f}\n"
            f"💵 *Lance Mínimo:* R$ {minimum_bid:,.2f}\n"
            f"📉 *Desconto:* {discount}%\n\n"
            f"📄 [Ver Edital do Leilão]({doc_url})\n"
            f"🔗 [Acessar Console do Radar](http://localhost:3000)\n"
        )
        return msg

    def send_alert(self, prop: dict) -> bool:
        """Send alert via Telegram Bot API or fallback log file."""
        message = self.format_alert_markdown(prop)
        success = False

        if self.bot_token and self.chat_id:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "Markdown",
                "disable_web_page_preview": False
            }
            try:
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=5) as res:
                    if res.status == 200:
                        success = True
            except Exception:
                # Fall back on exception
                pass

        # Write to local fallback file as fallback
        with open(self.fallback_file, "a", encoding="utf-8") as f:
            f.write(f"=== ALERT DISPATCHED AT {datetime.now(timezone.utc).isoformat()} ===\n")
            f.write(message)
            f.write("\n==================================================\n\n")

        return success or True
