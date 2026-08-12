"""Proof of concept script for the notifications dispatcher."""

from __future__ import annotations

import os
from radar.notifications.dispatcher import TelegramBotDispatcher


def main():
    print("--- RADAR IMOBILIÁRIO AI: POC NOTIFICAÇÕES ---")

    # Instantiate dispatcher without Telegram tokens so it falls back to log file
    dispatcher = TelegramBotDispatcher()

    sample_prop = {
        "title": "Apartamento Luxo de Frente para o Mar",
        "city": "Santos",
        "state": "SP",
        "appraisal_value": 750000.0,
        "minimum_bid": 380000.0,
        "discount_percent": 49.3,
        "score": 92.5,
        "risk_level": "LOW",
        "document_url": "https://venda-imoveis.caixa.gov.br/editais/edital_05.pdf"
    }

    print("Disparando alerta para o imóvel modelo...")
    success = dispatcher.send_alert(sample_prop)

    if success:
        print("\nAlerta enviado com sucesso!")
        print(f"Confira o log de fallback em: {dispatcher.fallback_file}")

        # Read the log to verify
        if os.path.exists(dispatcher.fallback_file):
            print("\nÚltimo Alerta Gravado:")
            with open(dispatcher.fallback_file, "r") as f:
                lines = f.readlines()
            # Print last 15 lines of the log file
            print("".join(lines[-15:]))


if __name__ == "__main__":
    main()
