"""Tests for flowcore_mcp — tools dispatch and server construction."""
from __future__ import annotations

import sys
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ── Tool dispatch tests ────────────────────────────────────────────────────────

class TestDispatch:
    def _dispatch(self, name, args=None):
        from flowcore_mcp.tools import dispatch
        return dispatch(name, args or {})

    def test_unknown_tool_returns_error(self):
        result = self._dispatch("nonexistent_tool")
        assert result.is_error is True
        assert "Unknown tool" in result.content[0].text

    def test_capability_list_ok(self):
        mock_reg = MagicMock()
        mock_reg.list_capabilities.return_value = {
            "runPython": MagicMock(), "runGit": None
        }
        with patch("capability.registry.CapabilityRegistry", return_value=mock_reg):
            result = self._dispatch("capability_list")
        assert result.is_error is False
        data = json.loads(result.content[0].text)
        assert "capabilities" in data
        assert data["capabilities"]["runPython"] is True
        assert data["capabilities"]["runGit"] is False

    def test_capability_list_error_handled(self):
        with patch("capability.registry.CapabilityRegistry", side_effect=RuntimeError("boom")):
            result = self._dispatch("capability_list")
        assert result.is_error is True
        assert "capability_list failed" in result.content[0].text

    def test_doctor_run_ok(self):
        mock_check = MagicMock()
        mock_check.name = "python"
        mock_check.status.value = "pass"
        mock_check.message = "Python 3.11 OK"
        mock_check.fix = ""
        mock_report = MagicMock()
        mock_report.checks = [mock_check]
        mock_service = MagicMock()
        mock_service.run.return_value = mock_report
        with patch("doctor.service.DoctorService", return_value=mock_service):
            result = self._dispatch("doctor_run")
        assert result.is_error is False
        data = json.loads(result.content[0].text)
        assert "summary" in data
        assert data["summary"]["total"] == 1
        assert data["summary"]["passed"] == 1
        assert len(data["checks"]) == 1
        assert data["checks"][0]["name"] == "python"

    def test_doctor_run_error_handled(self):
        with patch("doctor.service.DoctorService", side_effect=RuntimeError("bad")):
            result = self._dispatch("doctor_run")
        assert result.is_error is True

    def test_passport_issue_ok(self):
        from passport.schema import AgentIdentity, RuntimeInfo, Passport
        fake_agent = AgentIdentity(name="mcp-agent")
        fake_runtime = RuntimeInfo(
            platform="linux", is_android=False, is_termux=False,
            has_internet=True, python_version="3.11",
        )
        fake_passport = Passport(
            agent=fake_agent, runtime=fake_runtime,
            capabilities=["runPython"], permissions=["runPython"],
            health_status="ok",
        )
        mock_gen = MagicMock()
        mock_gen.issue.return_value = fake_passport
        with patch("passport.generator.PassportGenerator", return_value=mock_gen):
            result = self._dispatch("passport_issue", {"agent_name": "mcp-agent", "ttl": 3600})
        assert result.is_error is False
        data = json.loads(result.content[0].text)
        assert data["agent"]["name"] == "mcp-agent"
        assert "hash" in data

    def test_passport_issue_with_caps(self):
        from passport.schema import AgentIdentity, RuntimeInfo, Passport
        fake_agent = AgentIdentity(name="ci")
        fake_runtime = RuntimeInfo(
            platform="linux", is_android=False, is_termux=False,
            has_internet=True, python_version="3.11",
        )
        fake_passport = Passport(
            agent=fake_agent, runtime=fake_runtime,
            capabilities=["runPython"], permissions=[],
            health_status="ok",
        )
        mock_gen = MagicMock()
        mock_gen.issue.return_value = fake_passport
        with patch("passport.generator.PassportGenerator", return_value=mock_gen):
            result = self._dispatch("passport_issue", {
                "agent_name": "ci",
                "requested_capabilities": ["runPython"],
            })
        assert result.is_error is False

    def test_memory_list_ok(self):
        mock_repo = MagicMock()
        mock_repo.list_all.return_value = [{"id": 1, "text": "hello"}]
        with patch("storage.MemoryRepository", return_value=mock_repo):
            result = self._dispatch("memory_list", {"limit": 10})
        assert result.is_error is False
        data = json.loads(result.content[0].text)
        assert "memories" in data
        assert data["total"] == 1

    def test_memory_save_ok(self):
        mock_repo = MagicMock()
        mock_repo.add.return_value = {"id": 42, "text": "saved"}
        with patch("storage.MemoryRepository", return_value=mock_repo):
            result = self._dispatch("memory_save", {"text": "remember this"})
        assert result.is_error is False
        data = json.loads(result.content[0].text)
        assert data["saved"] is True

    def test_memory_save_requires_text(self):
        result = self._dispatch("memory_save", {"text": ""})
        assert result.is_error is True
        assert "required" in result.content[0].text

    def test_note_list_ok(self):
        mock_repo = MagicMock()
        mock_repo.list_all_sync.return_value = [
            {"id": 1, "source": "note", "text": "hello"},
            {"id": 2, "source": "todo", "text": "do it"},
        ]
        with patch("storage.DocumentRepository", return_value=mock_repo):
            result = self._dispatch("note_list")
        assert result.is_error is False
        data = json.loads(result.content[0].text)
        assert len(data["notes"]) == 2

    def test_note_list_kind_filter(self):
        mock_repo = MagicMock()
        mock_repo.list_all_sync.return_value = [
            {"id": 1, "source": "note", "text": "a"},
            {"id": 2, "source": "todo", "text": "b"},
        ]
        with patch("storage.DocumentRepository", return_value=mock_repo):
            result = self._dispatch("note_list", {"kind": "todo"})
        assert result.is_error is False
        data = json.loads(result.content[0].text)
        assert len(data["notes"]) == 1
        assert data["notes"][0]["source"] == "todo"

    def test_note_create_ok(self):
        mock_repo = MagicMock()
        mock_repo.insert_sync.return_value = 99
        with patch("storage.DocumentRepository", return_value=mock_repo):
            result = self._dispatch("note_create", {"text": "buy milk", "kind": "todo"})
        assert result.is_error is False
        data = json.loads(result.content[0].text)
        assert data["id"] == 99
        assert data["kind"] == "todo"

    def test_note_create_requires_text(self):
        result = self._dispatch("note_create", {"text": "", "kind": "note"})
        assert result.is_error is True

    def test_note_create_invalid_kind(self):
        result = self._dispatch("note_create", {"text": "x", "kind": "invalid"})
        assert result.is_error is True
        assert "kind" in result.content[0].text

    def test_search_ok(self):
        mock_mem = MagicMock()
        mock_mem.search.return_value = [{"id": 1, "text": "found"}]
        mock_doc = MagicMock()
        mock_doc.search_sync.return_value = []
        with (
            patch("storage.MemoryRepository", return_value=mock_mem),
            patch("storage.DocumentRepository", return_value=mock_doc),
        ):
            result = self._dispatch("search", {"q": "found"})
        assert result.is_error is False
        data = json.loads(result.content[0].text)
        assert data["query"] == "found"
        assert len(data["memories"]) == 1

    def test_search_requires_q(self):
        result = self._dispatch("search", {"q": ""})
        assert result.is_error is True
        assert "required" in result.content[0].text

    def test_daemon_status_ok(self):
        mock_daemon = MagicMock()
        mock_daemon.status.return_value = {"running": False, "pid": None}
        with patch("runtime.daemon.FlowCoreDaemon", return_value=mock_daemon):
            result = self._dispatch("daemon_status")
        assert result.is_error is False
        data = json.loads(result.content[0].text)
        assert "running" in data


# ── Tool list tests ────────────────────────────────────────────────────────────

class TestToolList:
    def test_all_tools_have_names(self):
        from flowcore_mcp.tools import FLOWCORE_TOOLS
        names = [t.name for t in FLOWCORE_TOOLS]
        assert len(names) >= 9

    def test_expected_tools_present(self):
        from flowcore_mcp.tools import FLOWCORE_TOOLS
        names = {t.name for t in FLOWCORE_TOOLS}
        for expected in (
            "capability_list", "doctor_run", "passport_issue",
            "memory_list", "memory_save", "note_list", "note_create",
            "search", "daemon_status",
        ):
            assert expected in names, f"Missing tool: {expected}"

    def test_tools_have_input_schema(self):
        from flowcore_mcp.tools import FLOWCORE_TOOLS
        for t in FLOWCORE_TOOLS:
            assert isinstance(t.input_schema, dict)
            assert t.input_schema.get("type") == "object"


# ── Server construction tests ─────────────────────────────────────────────────

class TestFlowCoreMCPServer:
    def test_instantiation(self):
        from flowcore_mcp.server import FlowCoreMCPServer
        srv = FlowCoreMCPServer(version="1.2.3")
        assert srv._version == "1.2.3"
        assert srv._server is not None

    def test_server_name(self):
        from flowcore_mcp.server import FlowCoreMCPServer
        srv = FlowCoreMCPServer()
        assert srv._server.name == "flowcore"

    def test_list_tools_async(self):
        import asyncio
        from flowcore_mcp.server import FlowCoreMCPServer
        srv = FlowCoreMCPServer()
        result = asyncio.run(srv._list_tools(None, None))
        assert len(result.tools) >= 9
