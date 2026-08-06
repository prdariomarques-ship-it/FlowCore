"""FlowCore — descoberta automática do endpoint e modelo do Ollama.

Remove a suposição de que o Ollama está sempre em 127.0.0.1:11434. As
variáveis de ambiente FLOWCORE_OLLAMA / FLOWCORE_MODEL, quando definidas,
sempre têm prioridade absoluta. Caso contrário, sondamos uma lista curta
de candidatos plausíveis por plataforma (localhost, host Docker, gateway
WSL2, gateway de rede local) chamando /api/tags e aceitando o primeiro
que responder HTTP 200.

Usado por flowcore.py e mcp_server.py — implementação única, sem
duplicação (ver requisito de reuso).
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from functools import lru_cache

PROBE_TIMEOUT = 1.5  # segundos por candidato

# Timeout de geração configurável via FLOWCORE_OLLAMA_TIMEOUT (padrão 180s —
# modelos grandes podem levar minutos para carregar em memória na primeira
# chamada, então 30s era curto demais).
DEFAULT_GENERATE_TIMEOUT = float(os.getenv("FLOWCORE_OLLAMA_TIMEOUT", "180"))

WARMUP_POLL_INTERVAL = 2  # segundos entre checagens de /api/ps durante o warm-up

# Ordem de preferência ao escolher automaticamente um modelo instalado.
MODEL_PRIORITY = ["gpt-oss", "glm", "qwen", "deepseek", "llama", "mistral", "phi", "gemma"]


class OllamaError(RuntimeError):
    """Classe base para todos os erros relacionados ao Ollama levantados pelo FlowCore."""


class OllamaDiscoveryError(OllamaError):
    """Nenhum endpoint Ollama alcançável (ou nenhum modelo utilizável) foi encontrado."""


class OllamaUnreachableError(OllamaError):
    """O Ollama parou de responder durante uma chamada (após a descoberta ter funcionado)."""


class OllamaModelNotInstalledError(OllamaError):
    """O modelo selecionado não está instalado no servidor Ollama (HTTP 404)."""


class OllamaSubscriptionRequiredError(OllamaError):
    """O modelo selecionado é um modelo Ollama Cloud que exige assinatura paga (HTTP 403)."""


class OllamaModelLoadTimeoutError(OllamaError):
    """O modelo não terminou de carregar em memória dentro do tempo limite."""


def _is_wsl() -> bool:
    """Detecta se o processo atual está rodando dentro do WSL (WSL1 ou WSL2)."""
    if os.environ.get("WSL_DISTRO_NAME"):
        return True
    try:
        with open("/proc/version") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False


def _default_route_gateway() -> str | None:
    """Retorna o IP do gateway da rota padrão (via `ip route`), se resolvível.

    Dentro do WSL2 esse gateway é o próprio host Windows — é assim que
    alcançamos o Ollama rodando nativamente no Windows a partir do WSL2.
    Em Termux/Linux genérico, é o gateway de rede local (ex.: roteador,
    ou o PC quando o telefone está em tethering USB).
    """
    try:
        result = subprocess.run(
            ["ip", "route", "show", "default"],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    parts = result.stdout.split()
    if "via" in parts:
        return parts[parts.index("via") + 1]
    return None


def _candidate_urls() -> list[str]:
    """Monta a lista ordenada e deduplicada de endpoints candidatos.

    O gateway da rota padrão é incluído sempre que resolvível: no WSL2
    ele aponta para o host Windows; em Termux/Linux genérico, para o
    gateway de rede local (roteador, ou o PC em tethering USB).
    """
    candidates = ["http://127.0.0.1:11434", "http://host.docker.internal:11434"]

    gateway = _default_route_gateway()
    if gateway:
        candidates.append(f"http://{gateway}:11434")

    seen: set[str] = set()
    ordered: list[str] = []
    for url in candidates:
        if url not in seen:
            seen.add(url)
            ordered.append(url)
    return ordered


def probe_endpoint(base_url: str, timeout: float = PROBE_TIMEOUT) -> bool:
    """Retorna True se `base_url/api/tags` responder HTTP 200."""
    try:
        request = urllib.request.Request(f"{base_url.rstrip('/')}/api/tags")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status == 200
    except (urllib.error.URLError, ConnectionRefusedError, TimeoutError, OSError):
        return False


@lru_cache(maxsize=1)
def discover_ollama_endpoint() -> str:
    """Resolve a URL base de um servidor Ollama alcançável.

    FLOWCORE_OLLAMA sempre vence, se definida. Caso contrário, sonda os
    candidatos de `_candidate_urls()` em ordem e retorna o primeiro que
    responder HTTP 200 em /api/tags. Levanta OllamaDiscoveryError com o
    diagnóstico completo se nenhum candidato responder.

    Resultado é cacheado por processo (uma falha nunca é cacheada — a
    próxima chamada tenta de novo, permitindo auto-recuperação se o
    Ollama subir depois).
    """
    env_url = os.getenv("FLOWCORE_OLLAMA")
    if env_url:
        return env_url.rstrip("/")

    attempted = []
    for url in _candidate_urls():
        attempted.append(url)
        if probe_endpoint(url):
            return url

    hint = (
        "Rodando dentro do WSL: o Ollama do Windows não é alcançável em "
        "127.0.0.1 a menos que o .wslconfig use networkingMode=mirrored."
        if _is_wsl()
        else "Se o Ollama roda em outra máquina (ex.: Termux acessando um PC), "
        "informe o endereço alcançável (IP de LAN, VPN ou túnel)."
    )
    raise OllamaDiscoveryError(
        "Nenhum endpoint Ollama alcançável foi encontrado. Tentativas: "
        + ", ".join(attempted)
        + f". {hint} Defina FLOWCORE_OLLAMA para configurar explicitamente "
        "(ex.: http://<host>:11434)."
    )


@lru_cache(maxsize=1)
def discover_default_model() -> str:
    """Resolve qual modelo usar no endpoint descoberto automaticamente.

    FLOWCORE_MODEL sempre vence, se definida. Caso contrário, consulta
    /api/tags no endpoint resolvido por discover_ollama_endpoint() e
    escolhe o primeiro modelo local (não hospedado na nuvem) que casar
    com MODEL_PRIORITY, nessa ordem de preferência. Sem nenhum casamento,
    usa o primeiro modelo local disponível. Nunca retorna um nome de
    modelo fixo no código.

    Modelos Ollama Cloud (tag ":cloud" ou com "remote_host" no /api/tags)
    são ignorados pelo auto-picker: exigem assinatura paga e falham com
    HTTP 403 sem ela, então nunca são um bom padrão automático — só são
    usados se explicitamente pedidos via FLOWCORE_MODEL.
    """
    env_model = os.getenv("FLOWCORE_MODEL")
    if env_model:
        return env_model

    base_url = discover_ollama_endpoint()

    try:
        request = urllib.request.Request(f"{base_url}/api/tags")
        with urllib.request.urlopen(request, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, ConnectionRefusedError, TimeoutError, OSError) as e:
        raise OllamaDiscoveryError(f"Falha ao consultar modelos em {base_url}: {e}") from e

    models = data.get("models", [])
    if not models:
        raise OllamaDiscoveryError(f"Nenhum modelo instalado no Ollama em {base_url}")

    local_models = [m for m in models if not m.get("remote_host") and not (m.get("name") or "").endswith(":cloud")]
    if not local_models:
        raise OllamaDiscoveryError(
            f"Só há modelos Ollama Cloud instalados em {base_url} (exigem assinatura paga). "
            "Defina FLOWCORE_MODEL explicitamente para usar um deles, ou instale um modelo local."
        )

    names = [m.get("name") or m.get("model", "") for m in local_models]

    for keyword in MODEL_PRIORITY:
        for name in names:
            if keyword in name.lower():
                return name

    return names[0]


# ---------------------------------------------------------------------------
# Pipeline de geração: garante o modelo carregado, chama /api/generate, e
# classifica erros em tipos distintos (inacessível, não instalado, exige
# assinatura, timeout de carregamento) em vez de um genérico "falhou".
# ---------------------------------------------------------------------------


def list_loaded_models(base_url: str, timeout: float = 5) -> list[str]:
    """Retorna os nomes dos modelos atualmente carregados em memória (via /api/ps)."""
    try:
        request = urllib.request.Request(f"{base_url.rstrip('/')}/api/ps")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, ConnectionRefusedError, TimeoutError, OSError) as e:
        raise OllamaUnreachableError(f"Falha ao consultar /api/ps em {base_url}: {e}") from e
    return [m.get("name") or m.get("model", "") for m in data.get("models", [])]


def _classify_http_error(e: urllib.error.HTTPError, base_url: str, model: str) -> OllamaError:
    """Traduz um HTTPError de /api/generate num tipo de erro específico."""
    try:
        body = e.read().decode("utf-8", errors="replace")
    except Exception:
        body = ""

    if e.code == 403:
        return OllamaSubscriptionRequiredError(
            f"O modelo '{model}' exige assinatura Ollama Cloud (HTTP 403) em {base_url}. "
            f"Defina FLOWCORE_MODEL para um modelo local instalado. Detalhe: {body}"
        )
    if e.code == 404:
        return OllamaModelNotInstalledError(
            f"Modelo '{model}' não está instalado em {base_url} (HTTP 404). Rode: ollama pull {model}. Detalhe: {body}"
        )
    return OllamaError(f"Erro HTTP {e.code} ao chamar {base_url}: {body or e.reason}")


def _is_cloud_model(model: str) -> bool:
    """Heurística: modelos Ollama Cloud usam a tag ':cloud' (mesmo critério de discover_default_model)."""
    return model.endswith(":cloud")


def _trigger_warmup(base_url: str, model: str, timeout: float) -> None:
    """Dispara /api/generate sem prompt — o Ollama apenas carrega o modelo em
    memória e responde assim que terminar, sem gerar texto.

    Um TimeoutError aqui não significa que o Ollama está inacessível: já
    confirmamos isso via /api/ps em ensure_model_loaded logo antes desta
    chamada. O /api/generate só responde depois que o modelo termina de
    carregar, então um timeout de leitura aqui é sinal de "ainda
    carregando", não de "servidor sumiu" — nesse caso não levantamos nada,
    deixando o loop de polling em ensure_model_loaded decidir (e classificar
    como OllamaModelLoadTimeoutError se o prazo total esgotar). Falhas de
    conexão de verdade (recusada, DNS, etc.) continuam sendo
    OllamaUnreachableError.
    """
    payload = json.dumps({"model": model})
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/generate",
        data=payload.encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read()
    except urllib.error.HTTPError as e:
        raise _classify_http_error(e, base_url, model) from e
    except TimeoutError:
        return
    except (urllib.error.URLError, ConnectionRefusedError, OSError) as e:
        raise OllamaUnreachableError(f"Ollama inacessível em {base_url} durante warm-up: {e}") from e


def ensure_model_loaded(base_url: str, model: str, timeout: float = DEFAULT_GENERATE_TIMEOUT) -> None:
    """Garante que `model` está carregado em memória antes de gerar.

    Consulta /api/ps primeiro; se o modelo já estiver carregado, retorna
    imediatamente. Caso contrário, dispara um warm-up (/api/generate sem
    prompt) e aguarda até `timeout` segundos, reconsultando /api/ps
    periodicamente, até o modelo aparecer carregado. Levanta
    OllamaModelLoadTimeoutError se o prazo esgotar.

    Modelos Ollama Cloud (ver _is_cloud_model) nunca aparecem em /api/ps —
    são passthroughs remotos, não algo "carregado em memória" localmente.
    O warm-up sem prompt também não dispara a checagem de assinatura no
    backend remoto (retorna 200 mesmo sem assinatura válida), então essa
    função é pulada por completo para eles: o erro real (403 exigindo
    assinatura, se for o caso) só surge na chamada de generate() de
    verdade, com prompt.
    """
    if _is_cloud_model(model):
        return

    if model in list_loaded_models(base_url):
        return

    _trigger_warmup(base_url, model, timeout)

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if model in list_loaded_models(base_url):
            return
        time.sleep(WARMUP_POLL_INTERVAL)

    raise OllamaModelLoadTimeoutError(
        f"O modelo '{model}' não terminou de carregar em {base_url} dentro de {timeout:.0f}s."
    )


def generate(base_url: str, model: str, prompt: str, timeout: float = DEFAULT_GENERATE_TIMEOUT) -> str:
    """Executa uma chamada de geração completa: garante o modelo carregado
    (ver ensure_model_loaded) e então chama /api/generate.

    Timeout é configurável (padrão DEFAULT_GENERATE_TIMEOUT, ajustável via
    FLOWCORE_OLLAMA_TIMEOUT). Erros são classificados em subclasses de
    OllamaError — OllamaUnreachableError, OllamaModelNotInstalledError,
    OllamaSubscriptionRequiredError, OllamaModelLoadTimeoutError — em vez
    de um genérico "Ollama unavailable".
    """
    ensure_model_loaded(base_url, model, timeout=timeout)

    payload = json.dumps({"model": model, "prompt": prompt, "stream": False})
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/generate",
        data=payload.encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
            return data.get("response", "").strip()
    except urllib.error.HTTPError as e:
        raise _classify_http_error(e, base_url, model) from e
    except (urllib.error.URLError, ConnectionRefusedError, TimeoutError, OSError) as e:
        raise OllamaUnreachableError(f"Ollama inacessível em {base_url}: {e}") from e
