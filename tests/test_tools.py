"""Tests for system tools execution and tool registry governance."""

import pytest
from runtime.tools.registry import get_tool_registry, ToolRegistry
from runtime.tools.system_tools import register_system_tools

def test_system_tools_registration():
    register_system_tools()
    registry = get_tool_registry()
    tools = registry.list_tools()
    tool_names = [t["name"] for t in tools]

    assert "search_client" in tool_names
    assert "get_portfolio" in tool_names
    assert "create_task" in tool_names
    assert "create_alert" in tool_names
    assert "send_telegram" in tool_names
    assert "prepare_whatsapp_message" in tool_names

def test_search_client_execution():
    registry = get_tool_registry()
    res = registry.execute("search_client", {"query": "Moderada"}, agent_id="test_agent")
    assert res["count"] >= 1

def test_create_task_and_permission_check():
    registry = get_tool_registry()
    res = registry.execute("create_task", {"title": "Revisar Carteira", "client_id": "cli_001"}, agent_id="test_agent")
    assert res["status"] == "CREATED"
    assert "task_id" in res

    with pytest.raises(PermissionError):
        registry.execute("create_task", {"title": "Test"}, agent_id="unauthorized_agent", granted_permissions=["other:permission"])
