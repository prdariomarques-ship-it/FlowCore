"""Proof of concept script for the CAIXA extrajudicial property collector."""

from __future__ import annotations

import os
from radar.collectors.caixa import CaixaCollector
from radar.database.db import get_connection, ensure_schema

DB_FILE = "data/radar.db"


def main():
    print("--- RADAR IMOBILIÁRIO AI: POC COLETOR CAIXA ---")

    # Ensure database folder and schema exist
    ensure_schema(DB_FILE)

    # Initialize and execute collector
    collector = CaixaCollector(DB_FILE)
    print("Iniciando ingestão ativa de imóveis da CAIXA...")
    count = collector.run()
    print(f"Sucesso! {count} imóveis ingeridos/atualizados com sucesso.")

    # Query sample from database
    conn = get_connection(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.id, p.title, f.appraisal_value, f.minimum_bid, f.discount_percent, o.score
        FROM properties p
        JOIN property_financials f ON p.id = f.property_id
        JOIN opportunity_scores o ON p.id = o.property_id
        LIMIT 3
    """)
    rows = cursor.fetchall()

    print("\nSample de Imóveis Ingeridos no Banco de Dados:")
    for r in rows:
        print(f"- ID: {r['id']} | {r['title']}")
        print(f"  Avaliação: R$ {r['appraisal_value']:,.2f} | Lance Mínimo: R$ {r['minimum_bid']:,.2f} ({r['discount_percent']}% OFF)")
        print(f"  Opportunity Score: {r['score']}/100")

    conn.close()


if __name__ == "__main__":
    main()
