"""Integration tests for the Radar Imobiliário AI system."""

from __future__ import annotations

import os
import sqlite3
import json
from pathlib import Path
from fastapi.testclient import TestClient

from radar.database.db import get_connection, ensure_schema
from radar.collectors.caixa import CaixaCollector
from radar.scoring.score import OpportunityScoringEngine
from radar.notifications.dispatcher import TelegramBotDispatcher
from api.router import app

TEST_DB = "data/test_radar.db"


class TestDatabaseSchema:
    def test_tables_created(self):
        """Verify that all required tables are successfully created in SQLite."""
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)

        ensure_schema(TEST_DB)
        conn = get_connection(TEST_DB)
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row["name"] for row in cursor.fetchall()]

        required = [
            "users", "sources", "properties", "property_addresses",
            "property_financials", "property_legals", "property_risks",
            "opportunity_scores", "documents", "price_histories", "collection_runs"
        ]
        for t in required:
            assert t in tables, f"Table {t} should exist in schema."

        conn.close()


class TestCaixaCollectorAndDeduplication:
    def test_pipeline_runs_cleanly(self):
        """Test collector run, data normalization, deduplication, and price drop logging."""
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)

        ensure_schema(TEST_DB)
        collector = CaixaCollector(TEST_DB)

        # 1. First run: should ingest 20 mock listings
        ingested_count = collector.run()
        assert ingested_count == 20, "Should ingest 20 initial listings."

        conn = get_connection(TEST_DB)
        cursor = conn.cursor()

        # Verify 20 items in properties
        cursor.execute("SELECT COUNT(*) as count FROM properties")
        assert cursor.fetchone()["count"] == 20, "Properties count should be exactly 20."

        # Verify 20 items in opportunity scores
        cursor.execute("SELECT COUNT(*) as count FROM opportunity_scores")
        assert cursor.fetchone()["count"] == 20, "Opportunity scores count should be exactly 20."

        # 2. Second run with same data: should have no duplicates (deduplication)
        ingested_count_2 = collector.run()
        assert ingested_count_2 == 20, "Should process 20 listings in second run."

        cursor.execute("SELECT COUNT(*) as count FROM properties")
        assert cursor.fetchone()["count"] == 20, "Properties count should remain exactly 20."

        # 3. Simulate a price drop to verify price histories
        cursor.execute("SELECT minimum_bid FROM property_financials WHERE property_id = 'CAIXA-10001'")
        original_bid = cursor.fetchone()["minimum_bid"]

        # Update minimum_bid to a higher value manually so the run triggers a 'price drop'
        cursor.execute("UPDATE property_financials SET minimum_bid = ? WHERE property_id = 'CAIXA-10001'", (original_bid + 5000.0,))
        conn.commit()

        # Re-run: should detect the 'price drop' back to original bid and log to histories
        collector.run()

        cursor.execute("SELECT price FROM price_histories WHERE property_id = 'CAIXA-10001'")
        history = cursor.fetchall()
        assert len(history) > 0, "Price drop should be logged to price_histories."
        assert history[0]["price"] == original_bid + 5000.0, "Logged price should be the previous higher value."

        conn.close()


class TestScoringEngine:
    def test_scores_correctness(self):
        """Verify calculations of opportunity, confidence, and risk scores."""
        engine = OpportunityScoringEngine()
        prop = {
            "discount_percent": 35.0,
            "is_occupied": 0, # vacant
            "zip_code": "01311-000",
            "street": "Rua Paulista",
            "matricula_number": "MAT-123",
            "property_url": "https://url.com"
        }
        opp, conf, risk = engine.compute(prop)
        assert opp > 50.0, "Discounts and vacant properties should yield high opportunity scores."
        assert conf == 100.0, "All verification fields present should yield 100% confidence."
        assert risk == 30.0, "Vacant, no-lawsuit properties should have low risk."


class TestNotificationDispatcher:
    def test_alert_formatting_and_logging(self):
        """Verify alert construction and fallback logging."""
        dispatcher = TelegramBotDispatcher()
        prop = {
            "title": "Apartamento Luxo Curitiba",
            "city": "Curitiba",
            "state": "PR",
            "appraisal_value": 450000.0,
            "minimum_bid": 250000.0,
            "discount_percent": 44.4,
            "score": 85.0,
            "risk_level": "LOW",
            "document_url": "https://venda-imoveis.caixa.gov.br/editais/edital_01.pdf"
        }
        alert = dispatcher.format_alert_markdown(prop)
        assert "🚨 *NOVA OPORTUNIDADE DETECTADA — RADAR IMOBILIÁRIO AI* 🚨" in alert
        assert "Apartamento Luxo Curitiba" in alert
        assert "44.4%" in alert

        # Test dispatch with fallback logging
        if os.path.exists(dispatcher.fallback_file):
            os.remove(dispatcher.fallback_file)

        success = dispatcher.send_alert(prop)
        assert success is True, "Notification delivery should fall back gracefully and succeed."
        assert os.path.exists(dispatcher.fallback_file), "Fallback log file should be written."


class TestAPIRouter:
    def test_endpoints_responses(self):
        """Test REST API routes using TestClient."""
        client = TestClient(app)

        # Get status
        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == "1.0.0"
        assert "database" in data
        assert "doctor" in data

        # POST Doctor / Active Ingestion Trigger
        resp_run = client.post("/api/doctor/run")
        assert resp_run.status_code == 200
        assert resp_run.json()["status"] == "success"

        # Get Opportunities list
        resp_opps = client.get("/api/opportunities")
        assert resp_opps.status_code == 200
        assert "opportunities" in resp_opps.json()
        assert len(resp_opps.json()["opportunities"]) == 20

        # POST Favorite and GET Favorites
        prop_id = "CAIXA-10001"
        resp_fav = client.post(f"/api/favorites/{prop_id}")
        assert resp_fav.status_code == 200
        assert resp_fav.json()["status"] == "success"

        resp_list_favs = client.get("/api/favorites")
        assert resp_list_favs.status_code == 200
        assert "favorites" in resp_list_favs.json()
        assert len(resp_list_favs.json()["favorites"]) == 1
        assert resp_list_favs.json()["favorites"][0]["id"] == prop_id
