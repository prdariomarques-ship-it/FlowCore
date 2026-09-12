"""Tests for Protocol compliance and Pydantic validation across darius.interfaces."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

pytest.importorskip("pydantic")
from pydantic import ValidationError

from darius.interfaces.llm import LLMAdapter, LLMMessage, LLMResponse
from darius.interfaces.mcp import (
    MCPAdapter,
    MCPPrompt,
    MCPPromptArgument,
    MCPResource,
)
from darius.interfaces.memory import MemoryAdapter, MemoryEntry, MemorySearchResult
from darius.interfaces.notifications import (
    NotificationChannelAdapter,
    NotificationDeliveryResult,
    NotificationMessage,
)
from darius.interfaces.skills import SkillAdapter, SkillManifest
from darius.interfaces.tools import (
    ToolAdapter,
    ToolDefinition,
    ToolExecutionResult,
    ToolParameter,
)


class TestLLMContracts:
    def test_llm_message_validation(self):
        msg = LLMMessage(role="user", content="Hello world")
        assert msg.role == "user"
        assert msg.content == "Hello world"
        assert msg.tool_calls is None

        with pytest.raises(ValidationError):
            LLMMessage(role="invalid_role", content="Fail")

    def test_llm_response_and_usage(self):
        resp = LLMResponse(
            content="Computed response",
            model="qwen3:4b",
            provider="ollama",
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
            latency_ms=120,
        )
        assert resp.content == "Computed response"
        assert resp.model == "qwen3:4b"
        assert resp.latency_ms == 120

    def test_llm_adapter_protocol_compliance(self):
        class ValidLLMAdapter:
            async def generate(self, messages: list[LLMMessage], **kwargs: Any) -> LLMResponse:
                return LLMResponse(content="", model="", provider="")

            async def stream(self, messages: list[LLMMessage], **kwargs: Any) -> AsyncIterator[str]:
                yield ""

            async def health(self) -> dict[str, Any]:
                return {"status": "ok"}

        adapter = ValidLLMAdapter()
        assert isinstance(adapter, LLMAdapter)

        class IncompleteLLMAdapter:
            async def generate(self, messages: list[LLMMessage], **kwargs: Any) -> LLMResponse:
                return LLMResponse(content="", model="", provider="")

        assert not isinstance(IncompleteLLMAdapter(), LLMAdapter)


class TestToolContracts:
    def test_tool_definition_and_parameters(self):
        param = ToolParameter(
            name="ticker",
            type="string",
            description="Stock symbol",
            required=True,
        )
        defn = ToolDefinition(
            name="get_stock_quote",
            description="Fetches live stock price",
            parameters=[param],
            permission_level="read",
        )
        assert defn.name == "get_stock_quote"
        assert len(defn.parameters) == 1
        assert defn.permission_level == "read"

    def test_tool_adapter_protocol_compliance(self):
        class ValidToolAdapter:
            @property
            def definition(self) -> ToolDefinition:
                return ToolDefinition(name="echo", description="Echoes input")

            async def execute(
                self, params: dict[str, Any], context: dict[str, Any] | None = None
            ) -> ToolExecutionResult:
                return ToolExecutionResult(success=True, output=params)

        adapter = ValidToolAdapter()
        assert isinstance(adapter, ToolAdapter)


class TestMCPContracts:
    def test_mcp_resource_and_prompt(self):
        res = MCPResource(uri="file:///portfolio.json", name="Portfolio")
        assert res.mime_type == "text/plain"

        prompt = MCPPrompt(
            name="market_summary",
            arguments=[MCPPromptArgument(name="date", required=True)],
        )
        assert prompt.name == "market_summary"

    def test_mcp_adapter_protocol_compliance(self):
        class ValidMCPAdapter:
            async def list_tools(self) -> list[ToolDefinition]:
                return []

            async def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolExecutionResult:
                return ToolExecutionResult(success=True, output={})

            async def list_resources(self) -> list[MCPResource]:
                return []

            async def read_resource(self, uri: str) -> str:
                return ""

            async def health(self) -> dict[str, Any]:
                return {"ok": True}

        assert isinstance(ValidMCPAdapter(), MCPAdapter)


class TestMemoryContracts:
    def test_memory_entry_validation(self):
        entry = MemoryEntry(
            id="mem-1",
            content="Client prefers conservative assets",
            category="semantic",
            metadata={"client_id": "c1"},
        )
        assert entry.category == "semantic"
        assert entry.metadata["client_id"] == "c1"

        with pytest.raises(ValidationError):
            MemoryEntry(id="mem-2", content="test", category="invalid_cat")

    def test_memory_adapter_protocol_compliance(self):
        class ValidMemoryAdapter:
            async def store(self, entry: MemoryEntry) -> bool:
                return True

            async def retrieve(self, query: str, limit: int = 5, **kwargs: Any) -> list[MemoryEntry]:
                return []

            async def search_semantic(self, query: str, limit: int = 5, **kwargs: Any) -> list[MemorySearchResult]:
                return []

            async def clear_working_memory(self, session_id: str) -> None:
                pass

            async def delete(self, entry_id: str) -> bool:
                return True

        assert isinstance(ValidMemoryAdapter(), MemoryAdapter)


class TestSkillContracts:
    def test_skill_manifest_validation(self):
        manifest = SkillManifest(
            id="market-scanner",
            name="Market Scanner",
            description="Scans B3 anomalies",
            required_tools=["yfinance_quote"],
        )
        assert manifest.enabled is True
        assert manifest.version == "1.0.0"

    def test_skill_adapter_protocol_compliance(self):
        class ValidSkillAdapter:
            @property
            def manifest(self) -> SkillManifest:
                return SkillManifest(id="s1", name="Test Skill", description="")

            async def activate(self, context: dict[str, Any]) -> bool:
                return True

            async def deactivate(self, context: dict[str, Any]) -> bool:
                return True

        assert isinstance(ValidSkillAdapter(), SkillAdapter)


class TestNotificationContracts:
    def test_notification_message_validation(self):
        msg = NotificationMessage(
            title="Portfolio Rebalance Alert",
            body="Asset drifted beyond target bounds.",
            level="WARNING",
            recipient="chat_123",
        )
        assert msg.level == "WARNING"
        assert msg.recipient == "chat_123"

        with pytest.raises(ValidationError):
            NotificationMessage(title="Test", body="Body", level="INVALID_LEVEL")

    def test_notification_delivery_result(self):
        res = NotificationDeliveryResult(
            success=True,
            channel="telegram",
            message_id="1010",
        )
        assert res.success is True
        assert res.channel == "telegram"
        assert res.error is None

    def test_notification_channel_adapter_protocol_compliance(self):
        class ValidChannelAdapter:
            @property
            def channel_name(self) -> str:
                return "webhook"

            async def send(self, message: NotificationMessage) -> NotificationDeliveryResult:
                return NotificationDeliveryResult(success=True, channel="webhook")

            async def is_available(self) -> bool:
                return True

        assert isinstance(ValidChannelAdapter(), NotificationChannelAdapter)
