"""Benchmark Engine — measures and compares model performance.

Runs a fixed task set and records latency, tokens/sec, quality score and
cost. Results are persisted to ~/.flowcore/benchmark_results.json.
Only promotes model changes to the registry after a full benchmark run —
never from a single isolated call.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from .model_registry import get_registry, ModelEntry

_RESULTS_FILE = Path.home() / ".flowcore" / "benchmark_results.json"

# Reference task set — versionado para comparações reproduzíveis
BENCHMARK_TASKS: list[dict[str, Any]] = [
    {
        "id": "t01_chat_simple",
        "type": "chat",
        "prompt": "Responda em uma frase: qual é a capital do Brasil?",
        "expected_keywords": ["brasília"],
    },
    {
        "id": "t02_market_brief",
        "type": "market_brief",
        "prompt": "Em duas frases, descreva o ambiente atual de juros globais.",
        "expected_keywords": ["juros", "taxa", "fed", "banco"],
    },
    {
        "id": "t03_analysis",
        "type": "analysis",
        "prompt": "Quais são os principais riscos de concentração em uma carteira 100% em renda variável brasileira?",
        "expected_keywords": ["risco", "ibovespa", "diversif", "volat"],
    },
    {
        "id": "t04_classification",
        "type": "classification",
        "prompt": 'Classifique como POSITIVO, NEGATIVO ou NEUTRO: "O Fed manteve os juros estáveis e sinalizou cautela."',
        "expected_keywords": ["neutro", "positivo", "negativo"],
    },
    {
        "id": "t05_summarization",
        "type": "summarization",
        "prompt": "Resuma em uma frase: 'O índice de inflação IPCA registrou alta de 0,38% em julho, abaixo das expectativas do mercado de 0,45%, puxado pela queda nos preços de alimentos e energia.'",
        "expected_keywords": ["ipca", "inflação", "julho"],
    },
]


@dataclass
class TaskResult:
    task_id: str
    task_type: str
    model_id: str
    latency_ms: float
    tokens_per_sec: float
    response_text: str
    quality_score: float   # 0.0–1.0, keyword hit rate
    success: bool
    error: str = ""
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["timestamp"] = self.timestamp or time.time()
        return d


@dataclass
class BenchmarkRun:
    model_id: str
    started_at: float
    finished_at: float
    results: list[TaskResult]
    avg_latency_ms: float
    avg_quality: float
    overall_success_rate: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_s": round(self.finished_at - self.started_at, 2),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "avg_quality": round(self.avg_quality, 3),
            "overall_success_rate": round(self.overall_success_rate, 3),
            "results": [r.to_dict() for r in self.results],
        }


def _score_response(text: str, keywords: list[str]) -> float:
    lower = text.lower()
    if not keywords:
        return 1.0
    hits = sum(1 for kw in keywords if kw in lower)
    return hits / len(keywords)


def _call_ollama(model_id: str, prompt: str, ollama_url: str, timeout: int = 60) -> tuple[str, float, float]:
    """Call Ollama and return (response_text, latency_ms, tokens_per_sec)."""
    import urllib.request
    payload = json.dumps({
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }).encode()
    t0 = time.perf_counter()
    req = urllib.request.Request(
        f"{ollama_url.rstrip('/')}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())
    elapsed_ms = (time.perf_counter() - t0) * 1000
    text = data.get("message", {}).get("content", "")
    eval_count = data.get("eval_count", 0)
    eval_duration_ns = data.get("eval_duration", 1)
    tps = eval_count / (eval_duration_ns / 1e9) if eval_duration_ns else 0.0
    return text, elapsed_ms, tps


class BenchmarkEngine:
    """Runs the reference task set against a model and persists results."""

    def __init__(self, results_file: Path = _RESULTS_FILE) -> None:
        self._path = results_file
        self._runs: list[dict] = []
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                self._runs = json.loads(self._path.read_text())
            except Exception:
                self._runs = []

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._runs, indent=2, ensure_ascii=False))

    def run(self, model_id: str, *, ollama_url: str, task_ids: list[str] | None = None) -> BenchmarkRun:
        """Run benchmark tasks against a model. Updates registry stats on completion."""
        tasks = BENCHMARK_TASKS
        if task_ids:
            tasks = [t for t in BENCHMARK_TASKS if t["id"] in task_ids]

        started_at = time.time()
        results: list[TaskResult] = []

        for task in tasks:
            try:
                text, latency_ms, tps = _call_ollama(model_id, task["prompt"], ollama_url)
                quality = _score_response(text, task.get("expected_keywords", []))
                results.append(TaskResult(
                    task_id=task["id"],
                    task_type=task["type"],
                    model_id=model_id,
                    latency_ms=latency_ms,
                    tokens_per_sec=tps,
                    response_text=text[:500],
                    quality_score=quality,
                    success=True,
                    timestamp=time.time(),
                ))
            except Exception as exc:
                results.append(TaskResult(
                    task_id=task["id"],
                    task_type=task["type"],
                    model_id=model_id,
                    latency_ms=0.0,
                    tokens_per_sec=0.0,
                    response_text="",
                    quality_score=0.0,
                    success=False,
                    error=str(exc),
                    timestamp=time.time(),
                ))

        finished_at = time.time()
        successes = [r for r in results if r.success]
        avg_latency = sum(r.latency_ms for r in successes) / max(1, len(successes))
        avg_quality = sum(r.quality_score for r in successes) / max(1, len(successes))
        success_rate = len(successes) / max(1, len(results))

        run = BenchmarkRun(
            model_id=model_id,
            started_at=started_at,
            finished_at=finished_at,
            results=results,
            avg_latency_ms=avg_latency,
            avg_quality=avg_quality,
            overall_success_rate=success_rate,
        )

        # Update registry stats from benchmark (only after full run)
        registry = get_registry()
        for r in results:
            registry.update_stats(
                model_id,
                latency_ms=r.latency_ms,
                tokens_per_sec=r.tokens_per_sec,
                success=r.success,
            )

        self._runs.append(run.to_dict())
        # Keep last 50 runs
        self._runs = self._runs[-50:]
        self._save()
        return run

    def history(self, model_id: str | None = None, limit: int = 10) -> list[dict]:
        runs = self._runs
        if model_id:
            runs = [r for r in runs if r["model_id"] == model_id]
        return runs[-limit:]

    def compare(self, model_a: str, model_b: str) -> dict[str, Any]:
        """Return a side-by-side comparison of the latest runs for two models."""
        def _latest(mid: str) -> dict | None:
            runs = [r for r in self._runs if r["model_id"] == mid]
            return runs[-1] if runs else None

        a, b = _latest(model_a), _latest(model_b)
        if not a or not b:
            return {"error": "One or both models have no benchmark results."}
        return {
            "model_a": {"id": model_a, "avg_latency_ms": a["avg_latency_ms"], "avg_quality": a["avg_quality"], "success_rate": a["overall_success_rate"]},
            "model_b": {"id": model_b, "avg_latency_ms": b["avg_latency_ms"], "avg_quality": b["avg_quality"], "success_rate": b["overall_success_rate"]},
            "winner_latency": model_a if a["avg_latency_ms"] < b["avg_latency_ms"] else model_b,
            "winner_quality": model_a if a["avg_quality"] > b["avg_quality"] else model_b,
        }


_benchmark: BenchmarkEngine | None = None


def get_benchmark() -> BenchmarkEngine:
    global _benchmark
    if _benchmark is None:
        _benchmark = BenchmarkEngine()
    return _benchmark
