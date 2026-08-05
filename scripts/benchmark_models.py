#!/usr/bin/env python3
"""FlowCore — Ollama Model Benchmark.

Auto-detects every installed (non-cloud) model on the discovered Ollama
endpoint and runs a fixed suite of prompts across six categories:
reasoning, coding, RAG grounding, agent/tool-use (structured output),
Portuguese, and speed/memory. Produces a comparison table and a
per-category recommendation.

Usage:
    python3 scripts/benchmark_models.py [--timeout SECONDS] [--out FILE.json]
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
import time
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.ollama import (  # noqa: E402
    OllamaError,
    discover_ollama_endpoint,
    generate,
)

GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"
BOLD = "\033[1m"
NC = "\033[0m"


# ---------------------------------------------------------------------------
# Test suite — each check returns (passed: bool | None, detail: str).
# None means "not automatically verifiable", the raw response is kept anyway.
# ---------------------------------------------------------------------------

def _check_reasoning(response: str) -> tuple[bool, str]:
    ok = "40" in response
    return ok, "expected '40'"


def _check_coding(response: str) -> tuple[bool, str]:
    code = response
    if "```" in code:
        parts = code.split("```")
        code = parts[1] if len(parts) > 1 else code
        code = code.removeprefix("python").strip()
    try:
        tree = ast.parse(code)
        has_def = any(isinstance(n, ast.FunctionDef) for n in ast.walk(tree))
        if not has_def:
            return False, "no function definition found"
        namespace: dict = {}
        exec(compile(tree, "<benchmark>", "exec"), namespace)
        fn = next(v for v in namespace.values() if callable(v))
        ok = fn(5) == 120
        return ok, "factorial(5) should be 120"
    except Exception as e:
        return False, f"invalid/non-executable code: {e}"


def _check_rag(response: str) -> tuple[bool, str]:
    ok = "XJ-4471" in response
    return ok, "expected the injected fact 'XJ-4471'"


def _check_agent(response: str) -> tuple[bool, str]:
    text = response.strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return False, "no JSON object found in response"
    try:
        data = json.loads(text[start:end + 1])
        ok = data.get("action") == "add" and data.get("a") == 3 and data.get("b") == 5
        return ok, "expected {'action':'add','a':3,'b':5}"
    except json.JSONDecodeError as e:
        return False, f"invalid JSON: {e}"


def _check_portuguese(response: str) -> tuple[bool, str]:
    ok = "brasília" in response.lower() or "brasilia" in response.lower()
    return ok, "expected 'Brasília'"


CATEGORIES = [
    {
        "key": "reasoning",
        "prompt": "A train travels 60 miles in 1.5 hours. What is its average speed in mph? Reply with just the number.",
        "check": _check_reasoning,
    },
    {
        "key": "coding",
        "prompt": "Write a Python function `factorial(n)` that returns n!. Output ONLY the code, no explanation, no markdown.",
        "check": _check_coding,
    },
    {
        "key": "rag",
        "prompt": (
            "Context:\nThe secret access code for Project Aurora is XJ-4471.\n\n"
            "Question: What is the secret access code for Project Aurora?\nAnswer:"
        ),
        "check": _check_rag,
    },
    {
        "key": "agent_tool_use",
        "prompt": (
            'Respond with ONLY a valid JSON object, no other text, matching exactly: '
            '{"action": "add", "a": 3, "b": 5}'
        ),
        "check": _check_agent,
    },
    {
        "key": "portuguese",
        "prompt": "Qual é a capital do Brasil? Responda em uma palavra.",
        "check": _check_portuguese,
    },
]


@dataclass
class CategoryResult:
    passed: bool | None
    detail: str
    elapsed_s: float
    response: str = ""
    error: str = ""


@dataclass
class ModelResult:
    model: str
    skipped: bool = False
    skip_reason: str = ""
    categories: dict[str, CategoryResult] = field(default_factory=dict)
    total_elapsed_s: float = 0.0
    vram_bytes: int | None = None


def _is_cloud_tagged(model_entry: dict) -> bool:
    name = model_entry.get("name") or model_entry.get("model", "")
    return bool(model_entry.get("remote_host")) or name.endswith(":cloud")


def discover_local_models(base_url: str) -> list[str]:
    """List every installed, non-cloud model at base_url (dynamic, no hardcoding)."""
    request = urllib.request.Request(f"{base_url}/api/tags")
    with urllib.request.urlopen(request, timeout=10) as response:
        data = json.loads(response.read().decode("utf-8"))
    models = data.get("models", [])
    return [m.get("name") or m.get("model", "") for m in models if not _is_cloud_tagged(m)]


def benchmark_model(base_url: str, model: str, timeout: float) -> ModelResult:
    result = ModelResult(model=model)
    t0 = time.monotonic()

    for cat in CATEGORIES:
        cat_t0 = time.monotonic()
        try:
            response = generate(base_url, model, cat["prompt"], timeout=timeout)
            elapsed = time.monotonic() - cat_t0
            passed, detail = cat["check"](response)
            result.categories[cat["key"]] = CategoryResult(
                passed=passed, detail=detail, elapsed_s=elapsed, response=response[:300]
            )
        except OllamaError as e:
            elapsed = time.monotonic() - cat_t0
            result.categories[cat["key"]] = CategoryResult(
                passed=False, detail="error", elapsed_s=elapsed, error=str(e)
            )

    result.total_elapsed_s = time.monotonic() - t0

    try:
        request = urllib.request.Request(f"{base_url}/api/ps")
        with urllib.request.urlopen(request, timeout=5) as response:
            ps_data = json.loads(response.read().decode("utf-8"))
        for m in ps_data.get("models", []):
            if (m.get("name") or m.get("model")) == model:
                result.vram_bytes = m.get("size_vram") or m.get("size")
    except Exception:
        pass

    return result


def run_benchmark(timeout: float) -> list[ModelResult]:
    base_url = discover_ollama_endpoint()
    models = discover_local_models(base_url)

    if not models:
        print(f"{RED}No local (non-cloud) models found at {base_url}{NC}")
        return []

    print(f"{BOLD}{CYAN}FlowCore Model Benchmark{NC}")
    print(f"Endpoint: {base_url}")
    print(f"Models ({len(models)}): {', '.join(models)}\n")

    results = []
    for model in models:
        print(f"{YELLOW}--> {model}{NC}", flush=True)
        result = benchmark_model(base_url, model, timeout)
        results.append(result)
        for key, cat in result.categories.items():
            mark = f"{GREEN}PASS{NC}" if cat.passed else f"{RED}FAIL{NC}"
            print(f"    {mark}  {key:<15} {cat.elapsed_s:>6.1f}s  {cat.detail}")
        print(f"    total: {result.total_elapsed_s:.1f}s\n")

    return results


def print_summary(results: list[ModelResult]) -> None:
    print(f"\n{BOLD}{CYAN}=== Summary ==={NC}\n")

    header = f"{'model':<20}" + "".join(f"{c['key']:<16}" for c in CATEGORIES) + f"{'total_s':<10}{'vram_mb':<10}"
    print(header)
    print("-" * len(header))
    for r in results:
        row = f"{r.model:<20}"
        for cat in CATEGORIES:
            cr = r.categories.get(cat["key"])
            cell = "PASS" if cr and cr.passed else "FAIL"
            row += f"{cell:<16}"
        row += f"{r.total_elapsed_s:<10.1f}"
        row += f"{(r.vram_bytes or 0) / (1024**2):<10.0f}"
        print(row)

    print(f"\n{BOLD}Recommendations{NC}")
    for cat in CATEGORIES:
        passing = [r for r in results if (r.categories.get(cat["key"]) or CategoryResult(False, "", 0)).passed]
        if not passing:
            print(f"  {cat['key']:<15} no model passed")
            continue
        best = min(passing, key=lambda r: r.categories[cat["key"]].elapsed_s)
        print(f"  {cat['key']:<15} {best.model} ({best.categories[cat['key']].elapsed_s:.1f}s)")

    fastest = min(results, key=lambda r: r.total_elapsed_s, default=None)
    if fastest:
        print(f"  {'speed':<15} {fastest.model} ({fastest.total_elapsed_s:.1f}s total)")

    with_vram = [r for r in results if r.vram_bytes]
    if with_vram:
        leanest = min(with_vram, key=lambda r: r.vram_bytes)
        print(f"  {'memory':<15} {leanest.model} ({leanest.vram_bytes / (1024**2):.0f} MB)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark every installed local Ollama model")
    parser.add_argument("--timeout", type=float, default=180, help="Per-call timeout in seconds (default: 180)")
    parser.add_argument("--out", type=str, default="", help="Write full JSON results to this file")
    args = parser.parse_args()

    results = run_benchmark(args.timeout)
    if not results:
        sys.exit(1)

    print_summary(results)

    if args.out:
        payload = [asdict(r) for r in results]
        Path(args.out).write_text(json.dumps(payload, indent=2))
        print(f"\n{GREEN}Full results written to {args.out}{NC}")


if __name__ == "__main__":
    main()
