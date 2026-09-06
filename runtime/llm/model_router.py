"""Unified Model Router & Provider Abstraction layer for FlowCore.

Provides a clean ModelRouter interface decoupling agents from specific LLM providers
(DeepSeek, OpenAI, Anthropic, Ollama), with DeepSeek as the default.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
import urllib.error
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from runtime.llm.cost_tracker import get_cost_tracker


class ModelProvider(ABC):
    name: str

    @abstractmethod
    def is_available(self) -> bool:
        """Check availability (e.g. valid API key or endpoint)."""
        pass

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        agent_id: str = "general",
    ) -> Dict[str, Any]:
        """Execute LLM call returning normalized output."""
        pass


class DeepSeekProvider(ModelProvider):
    name = "deepseek"

    def __init__(self, api_key: Optional[str] = None, base_url: str = "https://api.deepseek.com/v1") -> None:
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        self.base_url = base_url.rstrip("/")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        agent_id: str = "general",
    ) -> Dict[str, Any]:
        if not self.is_available():
            raise RuntimeError("DeepSeek API key is missing.")

        model_name = model or "deepseek-chat"
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        start_time = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
        except Exception as e:
            raise RuntimeError(f"DeepSeek provider call failed: {e}")

        elapsed_ms = (time.monotonic() - start_time) * 1000.0

        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        usage = result.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", len(prompt) // 4)
        completion_tokens = usage.get("completion_tokens", len(content) // 4)

        # Record token cost
        tracker = get_cost_tracker()
        cost_entry = tracker.record_call(
            agent_id=agent_id,
            provider=self.name,
            model=model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=elapsed_ms,
        )

        return {
            "provider": self.name,
            "model": model_name,
            "content": content,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "cost_usd": cost_entry["cost_usd"],
            "latency_ms": elapsed_ms,
        }


class OllamaFallbackProvider(ModelProvider):
    name = "ollama"

    def __init__(self, base_url: str = "http://127.0.0.1:11434") -> None:
        self.base_url = base_url.rstrip("/")

    def is_available(self) -> bool:
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=2) as resp:
                return resp.status == 200
        except Exception:
            return False

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        agent_id: str = "general",
    ) -> Dict[str, Any]:
        model_name = model or "llama3:latest"
        full_prompt = f"System: {system_prompt}\nUser: {prompt}" if system_prompt else prompt

        payload = {
            "model": model_name,
            "prompt": full_prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }

        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        start_time = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
        except Exception as e:
            raise RuntimeError(f"Ollama provider call failed: {e}")

        elapsed_ms = (time.monotonic() - start_time) * 1000.0
        content = result.get("response", "")

        tracker = get_cost_tracker()
        cost_entry = tracker.record_call(
            agent_id=agent_id,
            provider=self.name,
            model=model_name,
            prompt_tokens=len(full_prompt) // 4,
            completion_tokens=len(content) // 4,
            latency_ms=elapsed_ms,
        )

        return {
            "provider": self.name,
            "model": model_name,
            "content": content,
            "prompt_tokens": len(full_prompt) // 4,
            "completion_tokens": len(content) // 4,
            "total_tokens": (len(full_prompt) + len(content)) // 4,
            "cost_usd": cost_entry["cost_usd"],
            "latency_ms": elapsed_ms,
        }


class ModelRouter:
    """Model Router that routes calls to primary provider (DeepSeek) with automatic fallbacks."""

    def __init__(self) -> None:
        self.providers: Dict[str, ModelProvider] = {
            "deepseek": DeepSeekProvider(),
            "ollama": OllamaFallbackProvider(),
        }

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        provider_preference: Optional[List[str]] = None,
        temperature: float = 0.7,
        agent_id: str = "general",
    ) -> Dict[str, Any]:
        preferences = provider_preference or ["deepseek", "ollama"]

        last_error = None
        for prov_name in preferences:
            provider = self.providers.get(prov_name)
            if provider and provider.is_available():
                try:
                    return provider.generate(
                        prompt=prompt,
                        system_prompt=system_prompt,
                        model=model,
                        temperature=temperature,
                        agent_id=agent_id,
                    )
                except Exception as e:
                    last_error = e
                    continue

        # Deterministic local fallback if no remote LLM available
        return {
            "provider": "deterministic-fallback",
            "model": "rule-based",
            "content": f"[Aviso: LLM indisponível. Resposta determinística de contingência para o agente '{agent_id}']",
            "prompt_tokens": len(prompt) // 4,
            "completion_tokens": 10,
            "total_tokens": (len(prompt) // 4) + 10,
            "cost_usd": 0.0,
            "latency_ms": 1.0,
        }


_router_instance = ModelRouter()

def get_model_router() -> ModelRouter:
    return _router_instance
