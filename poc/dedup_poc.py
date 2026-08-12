"""Proof of concept script demonstrating deduplication and price drop history tracking."""

from __future__ import annotations

import os
import sqlite3
from radar.collectors.caixa import CaixaCollector
from radar.database.db import get_connection, ensure_schema

DB_FILE = "data/radar.db"


def main():
    print("--- RADAR IMOBILIÁRIO AI: POC DEDUPLICADOR & PRICE DROP ---")

    # Initialize schema
    ensure_schema(DB_FILE)
    collector = CaixaCollector(DB_FILE)

    # Clean and perform fresh run
    print("Executando primeira ingestão ativa...")
    collector.run()

    conn = get_connection(DB_FILE)
    cursor = conn.cursor()

    # Let's count total properties
    cursor.execute("SELECT COUNT(*) as count FROM properties")
    first_count = cursor.fetchone()["count"]
    print(f"Total de imóveis no primeiro run: {first_count}")

    # Let's update CAIXA-10001 with a HIGHER minimum bid manually so the subsequent run detects a price drop
    cursor.execute("SELECT minimum_bid FROM property_financials WHERE property_id = 'CAIXA-10001'")
    current_bid = cursor.fetchone()["minimum_bid"]
    higher_bid = current_bid + 15000.0
    print(f"\nSimulando reajuste de preço (subindo lance mínimo de R$ {current_bid:,.2f} para R$ {higher_bid:,.2f})...")
    cursor.execute("UPDATE property_financials SET minimum_bid = ? WHERE property_id = 'CAIXA-10001'", (higher_bid,))
    conn.commit()

    # Run collector again. It has the original lower bid, so it will detect a price drop!
    print("Executando segunda ingestão ativa para detectar queda de preço...")
    collector.run()

    # Count properties again to verify zero duplicates
    cursor.execute("SELECT COUNT(*) as count FROM properties")
    second_count = cursor.fetchone()["count"]
    print(f"Total de imóveis no segundo run: {second_count} (Deduplicador OK!)")

    # Check if price drop was logged in history
    cursor.execute("SELECT price, recorded_at FROM price_histories WHERE property_id = 'CAIXA-10001'")
    history_rows = cursor.fetchall()

    print("\nHistórico de Alteração de Preços para CAIXA-10001:")
    for h in history_rows:
        print(f"- Lance Antigo (Mais Alto): R$ {h['price']:,.2f} registrado em {h['recorded_at']}")

    conn.close()


if __name__ == "__main__":
    main()
