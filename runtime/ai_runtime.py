"""AI Runtime -- camada de inferência local-first do FlowCore.

Esta camada NÃO duplica o LLMRouter/AgentEngine: ela é a superfície de
status e controle exposta para a interface Web (IA Local), o app mobile
(192.168.1.66/flowcore/) e o agente pessoal -- exatamente a divisão
FLOWCORE_CONSTITUTION.md:

  FLOWCORE       = sistema de execução (motores determinísticos + tools)
  AI RUNTIME     = camada de inteligência (o que este módulo expõe)
  OLLAMA         = infraestrutura local de modelos
  OPENROUTER     = fallback (LocalFirstPolicy já decide quando)
  TOOLS          = acesso aos dados e ações do FlowCore (service.py)

Responsabilidades deste módulo:
  1. Modelos: listar os instalados no Ollama com tamanho (GB) e qual está
     carregado em memória, com o modelo ativo padrão (discover_default_model).
  2. Memória: carregar (warm-up) e liberar modelo explicitamente
     (POST /api/generate com keep_alive=0), com status.
  3. Chat com contexto: reutiliza service.agent_ask() -- que já aplica o
     AgentEngine com 18 tools reais (mercado, portfólio, memória, notas...)
     sobre o LLMRouter local-first com fallback OpenRouter quando
     metadata.allow_cloud=true. A IA nunca inventa dado: tool execution é
     código FlowCore real; quando nenhuma tool se aplica, a resposta vem do
     mesmo contexto RAG do ask().
  4. Telemetria: /api/llm/status já registra provider, latência, fallbacks
     usados (last_used_provider, errors, cloud_fallback_count) -- este
     módulo consolida em um health check único do AI Runtime.

Nenhuma dependência nova: só urllib stdlib + os módulos runtime já existentes.
"""
from __future__ import annotations

import time
from config.loader import get_config
from runtime.ollama import (
    OllamaError,
    OllamaUnreachableError,
    discover_default_model,
    discover_ollama_endpoint,
    ensure_model_loaded,
    list_loaded_models,
)
from runtime.llm.registry import ProviderRegistry

__all__ = [
    "model_list",
    "memory_status",
    "load_model",
    "unload_model",
    "ai_runtime_health",
    "RuntimeError",
]


def _ollama_base_url() -> str:
    """Endpoint Ollama resolvido pela mesma lógica do restante do FlowCore."""
    env_url = get_config().get("ollama.url") or get_config().get("ollama.base_url")
    if env_url:
        return str(env_url).rstrip("/")
    return discover_ollama_endpoint()


def _tags(timeout: float = 5) -> list:
    """GET /api/tags do Ollama -- modelos instalados com tamanho e detalhes."""
    import json
    import urllib.request

    request = urllib.request.Request(f"{_ollama_base_url()}/api/tags")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    return data.get("models", [])


def _gb(size_bytes: int | None) -> str:
    """Formata bytes -> string com 2 casas decimais em GB."""
    if not size_bytes:
        return "?"
    return f"{size_bytes / (1024 ** 3):.2f}"


def _ram_gb(used: int | None) -> str:
    """Formata bytes de VRAM/RAM usados -> string em GB."""
    if not used:
        return "0.00"
    return f"{used / (1024 ** 3):.2f}"


def model_list() -> dict:
    """Lista os modelos instalados no Ollama com tamanho estimado e marca
    qual está carregado em memória e qual é o ativo padrão do FlowCore.

    Formato: {"ollama_available": bool, "active_model": str,
              "loaded": [str], "models": [{"name", "size_gb", "loaded", "family", "parameters"}]}
    """
    loaded: list[str] = []
    try:
        loaded = list_loaded_models(_ollama_base_url())
    except OllamaError:
        return {
            "ollama_available": False,
            "active_model": None,
            "loaded": [],
            "models": [],
            "message": "Ollama inacessível em " + _ollama_base_url(),
        }

    active = None
    try:
        active = discover_default_model()
    except OllamaError:
        pass

    models = []
    for m in _tags():
        name = m.get("name") or m.get("model", "")
        details = m.get("details") or {}
        families = details.get("families") or []
        models.append(
            {
                "name": name,
                "size_gb": _gb(m.get("size")),
                "size_bytes": m.get("size"),
                "parameters": details.get("parameter_size", "?"),
                "family": ", ".join(families),
                "loaded": name in loaded,
            }
        )
    models.sort(key=lambda x: x["name"])
    return {
        "ollama_available": True,
        "active_model": active,
        "loaded": loaded,
        "models": models,
        "message": "ok",
    }


def memory_status() -> dict:
    """Status de memória do Ollama: modelos carregados, RAM/VRAM usada e
    uptime estimado do processo (quando disponível)."""
    base_url = _ollama_base_url()
    try:
        loaded = list_loaded_models(base_url)
    except OllamaUnreachableError as e:
        return {"ollama_available": False, "loaded": [], "ram_used_gb": None, "message": str(e)}

    import json
    import urllib.request

    models = []
    total_ram = 0
    try:
        request = urllib.request.Request(f"{base_url}/api/ps")
        with urllib.request.urlopen(request, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
        for m in data.get("models", []):
            details = m.get("details") or {}
            models.append(
                {
                    "name": m.get("name") or m.get("model", ""),
                    "parameters": details.get("parameter_size", "?"),
                    "ram_used_gb": _ram_gb(m.get("size_vram", 0) or m.get("size")),
                    "expires_at": m.get("expires_at"),
                }
            )
            total_ram += m.get("size_vram", 0) or m.get("size", 0)
    except (OllamaError, Exception):
        pass

    return {
        "ollama_available": True,
        "loaded": models if models else loaded,
        "total_ram_used_gb": _ram_gb(total_ram),
        "message": "ok",
    }


def load_model(model: str, timeout: float = 300) -> dict:
    """Carrega explicitamente um modelo em memória (warm-up com polling).
    Reusa a mesma garantia já usada em generate(): timeout de carregamento
    vira erro claro, não uma resposta corrompida."""
    base_url = _ollama_base_url()
    try:
        tags = [m.get("name") or m.get("model", "") for m in _tags()]
    except OllamaError:
        return {"ok": False, "error": "ollama_unreachable", "message": "Ollama inacessível"}

    if model not in tags:
        return {
            "ok": False,
            "error": "model_not_installed",
            "message": f"Modelo '{model}' não instalado. Instale com: ollama pull {model}",
        }

    start = time.monotonic()
    try:
        ensure_model_loaded(base_url, model, timeout=timeout)
    except OllamaError as e:
        return {"ok": False, "error": "load_failed", "message": str(e)}

    elapsed = time.monotonic() - start
    return {
        "ok": True,
        "model": model,
        "loaded": True,
        "load_seconds": round(elapsed, 1),
        "message": f"Modelo '{model}' carregado em {elapsed:.1f}s",
    }


def unload_model(model: str) -> dict:
    """Libera um modelo da memória do Ollama (keep_alive=0 no /api/generate).
    Sem gerar texto -- apenas descarrega."""
    import json
    import urllib.request

    base_url = _ollama_base_url()
    payload = json.dumps({"model": model, "keep_alive": 0})
    request = urllib.request.Request(
        f"{base_url}/api/generate",
        data=payload.encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            response.read()
    except (urllib.error.URLError, ConnectionRefusedError, TimeoutError, OSError) as e:
        return {"ok": False, "error": "ollama_unreachable", "message": str(e)}

    # Confirma: o modelo não deve mais aparecer em /api/ps
    remaining = list_loaded_models(base_url)
    return {
        "ok": True,
        "model": model,
        "loaded": model in remaining,
        "remaining_loaded": remaining,
        "message": "ok" if model not in remaining else f"Modelo ainda presente: {remaining}",
    }


def ai_runtime_health() -> dict:
    """Health check único do AI Runtime: Ollama disponível, modelo padrão
    instalado, modelo carregado em memória, provedores LLM registrados e
    disponibilidade (local-first + cloud)."""
    base_url = _ollama_base_url()
    ollama_ok = False
    default_model = None
    loaded: list[str] = []
    try:
        ollama_ok = True
        default_model = discover_default_model()
        loaded = list_loaded_models(base_url)
    except OllamaError:
        pass


    registry = get_config().get("_llm_registry") if isinstance(get_config(), dict) else None
    # O registry real vive em service.py (_llm_registry); aqui aceitamos um
    # snapshot opcional injetado via parâmetro ou usamos um registro mínimo.
    providers: list[dict] = []
    if registry and isinstance(registry, ProviderRegistry):
        for provider in registry.all():
            providers.append({"name": provider.name, "available": provider.is_available()})

    active_in_memory = bool(default_model and default_model in loaded)
    return {
        "ai_runtime": True,
        "ollama_available": ollama_ok,
        "ollama_endpoint": base_url,
        "default_model": default_model,
        "model_loaded_in_memory": active_in_memory,
        "loaded_models": loaded,
        "providers": providers,
        "local_first": True,
        "cloud_fallback": bool(get_config().get("agent.allow_cloud")),
        "message": "ok" if ollama_ok and active_in_memory else "degraded",
    }
