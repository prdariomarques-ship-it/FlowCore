"""Database module — initializes and manages the SQLite database schema for Radar Imobiliário AI."""

from __future__ import annotations

import sqlite3
from pathlib import Path

DB_FILE = "data/radar.db"


def get_connection(db_path: str = DB_FILE) -> sqlite3.Connection:
    """Return a connection to the SQLite database, ensuring directories exist."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema(db_path: str = DB_FILE) -> None:
    """Create all required tables for Radar Imobiliário AI idempotently."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    # User
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Source
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sources (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            category TEXT NOT NULL, -- extrajudicial / judicial
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Auctioneer (Leiloeiro)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS auctioneers (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            url TEXT,
            registration_number TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Auction
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS auctions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT,
            auctioneer_id TEXT,
            auction_code TEXT,
            first_call TIMESTAMP,
            second_call TIMESTAMP,
            status TEXT NOT NULL, -- pending, active, finished, cancelled
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(source_id) REFERENCES sources(id),
            FOREIGN KEY(auctioneer_id) REFERENCES auctioneers(id)
        )
    """)

    # Property
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS properties (
            id TEXT PRIMARY KEY, -- CAIXA ID or custom hashed ID
            source_id TEXT NOT NULL,
            title TEXT NOT NULL,
            property_type TEXT, -- Apartamento, Casa, Terreno, etc.
            description TEXT,
            status TEXT NOT NULL, -- available, sold, pending
            source_url TEXT NOT NULL,
            property_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(source_id) REFERENCES sources(id)
        )
    """)

    # PropertyAddress
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS property_addresses (
            property_id TEXT PRIMARY KEY,
            state TEXT NOT NULL,
            city TEXT NOT NULL,
            neighborhood TEXT,
            street TEXT,
            number TEXT,
            complement TEXT,
            zip_code TEXT,
            FOREIGN KEY(property_id) REFERENCES properties(id) ON DELETE CASCADE
        )
    """)

    # PropertyFinancial
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS property_financials (
            property_id TEXT PRIMARY KEY,
            appraisal_value REAL NOT NULL, -- valor de avaliação original
            minimum_bid REAL NOT NULL,     -- lance mínimo atual
            discount_percent REAL,         -- porcentagem de desconto
            condo_debts REAL DEFAULT 0.0,
            iptu_debts REAL DEFAULT 0.0,
            other_debts REAL DEFAULT 0.0,
            estimated_market_value REAL,   -- valor de mercado estimado
            total_acquisition_cost REAL,   -- custo total (bid + impostos + dividas)
            potential_margin REAL,         -- margem de lucro estimada
            FOREIGN KEY(property_id) REFERENCES properties(id) ON DELETE CASCADE
        )
    """)

    # PropertyLegal
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS property_legals (
            property_id TEXT PRIMARY KEY,
            is_occupied INTEGER NOT NULL DEFAULT 1, -- 1 = occupied, 0 = vacant
            lawsuit_number TEXT,
            registry_office TEXT, -- cartório de registro
            matricula_number TEXT,
            legal_risks_summary TEXT,
            FOREIGN KEY(property_id) REFERENCES properties(id) ON DELETE CASCADE
        )
    """)

    # PropertyRisk
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS property_risks (
            property_id TEXT PRIMARY KEY,
            risk_score REAL NOT NULL DEFAULT 0.0, -- 0 to 100
            risk_level TEXT NOT NULL DEFAULT 'MEDIUM', -- LOW, MEDIUM, HIGH
            details TEXT, -- JSON explanation string
            FOREIGN KEY(property_id) REFERENCES properties(id) ON DELETE CASCADE
        )
    """)

    # Document
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            property_id TEXT NOT NULL,
            name TEXT NOT NULL, -- Edital, Matrícula, etc.
            url TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(property_id) REFERENCES properties(id) ON DELETE CASCADE
        )
    """)

    # DocumentVersion
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS document_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            hash TEXT NOT NULL,
            file_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
        )
    """)

    # Valuation
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS valuations (
            property_id TEXT PRIMARY KEY,
            method TEXT NOT NULL, -- AVM, comparable, appraisal
            estimated_value REAL NOT NULL,
            confidence_score REAL NOT NULL, -- 0 to 100
            details TEXT, -- JSON metadata
            computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(property_id) REFERENCES properties(id) ON DELETE CASCADE
        )
    """)

    # Comparable (imóveis parecidos na região)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS comparables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            property_id TEXT NOT NULL,
            title TEXT NOT NULL,
            price REAL NOT NULL,
            source TEXT NOT NULL,
            url TEXT,
            distance_meters REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(property_id) REFERENCES properties(id) ON DELETE CASCADE
        )
    """)

    # Analysis
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS analyses (
            property_id TEXT PRIMARY KEY,
            summary TEXT,
            detailed_markdown TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(property_id) REFERENCES properties(id) ON DELETE CASCADE
        )
    """)

    # OpportunityScore
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS opportunity_scores (
            property_id TEXT PRIMARY KEY,
            score REAL NOT NULL, -- 0 to 100
            confidence REAL NOT NULL, -- 0 to 100 (data confidence)
            explanation TEXT, -- JSON lists of pros & cons
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(property_id) REFERENCES properties(id) ON DELETE CASCADE
        )
    """)

    # SavedSearch
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS saved_searches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            filters TEXT NOT NULL, -- JSON formatted filters
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # Favorite
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS favorites (
            user_id INTEGER NOT NULL,
            property_id TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(user_id, property_id),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(property_id) REFERENCES properties(id) ON DELETE CASCADE
        )
    """)

    # Notification
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            property_id TEXT NOT NULL,
            channel TEXT NOT NULL, -- Telegram, email, etc.
            status TEXT NOT NULL, -- pending, sent, failed
            sent_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(property_id) REFERENCES properties(id) ON DELETE CASCADE
        )
    """)

    # PriceHistory
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS price_histories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            property_id TEXT NOT NULL,
            price REAL NOT NULL,
            appraisal_value REAL,
            recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(property_id) REFERENCES properties(id) ON DELETE CASCADE
        )
    """)

    # CollectionRun
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS collection_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT NOT NULL,
            start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            end_time TIMESTAMP,
            status TEXT NOT NULL, -- running, completed, failed
            records_collected INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(source_id) REFERENCES sources(id)
        )
    """)

    # CollectionError
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS collection_errors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            error_message TEXT NOT NULL,
            traceback_details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(run_id) REFERENCES collection_runs(id) ON DELETE CASCADE
        )
    """)

    # AuditLog
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT NOT NULL,
            details TEXT,
            ip_address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
        )
    """)

    conn.commit()
    conn.close()
