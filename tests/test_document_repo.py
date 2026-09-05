"""Tests for DocumentRepository and the /api/notes endpoints.

Covers a real regression: DocumentRepository.list_all() used to omit the
`content` column, so every note rendered in the web dashboard as just its
generic label ("Nota"/"TODO"/"Agenda") instead of its actual text. Also
covers the "radar" note kind used for manager-letters digests (Verde,
Legacy, Kinea, TAG...), including title derivation from the first line.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestDocumentRepositoryListAll:
    def test_list_all_includes_content(self, tmp_path):
        from storage.document_repo import DocumentRepository

        repo = DocumentRepository(db_path=str(tmp_path / "docs.db"))
        repo.insert_sync("Nota", "conteúdo completo da nota", "note")

        docs = repo.list_all_sync()
        assert docs[0]["content"] == "conteúdo completo da nota"


class TestNotesApiRadarKind:
    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        pytest.importorskip("fastapi")
        pytest.importorskip("httpx")
        from fastapi.testclient import TestClient
        from api.router import create_app

        monkeypatch.setattr(
            "storage.document_repo.get_db_path", lambda: str(tmp_path / "docs.db")
        )
        app = create_app(version="test", platform_info={"os_name": "test"})
        return TestClient(app)

    def test_create_radar_note_derives_title_from_first_line(self, client):
        r = client.post("/api/notes", json={
            "text": "## Radar de Cartas de Gestão | 05/09/2026\n\nresto do conteúdo",
            "kind": "radar",
        })
        assert r.status_code == 201

        listed = client.get("/api/notes", params={"kind": "radar"}).json()["notes"]
        assert len(listed) == 1
        assert listed[0]["title"] == "Radar de Cartas de Gestão | 05/09/2026"
        assert "resto do conteúdo" in listed[0]["content"]

    def test_rejects_unknown_kind(self, client):
        r = client.post("/api/notes", json={"text": "x", "kind": "bogus"})
        assert r.status_code == 422
