# FlowCore — Market Radar & Personal Agent

**Local-first AI financial operating system.** Real-market intelligence, deterministic macro regime detection, an explainable decision engine, and a personal agent — running on your own hardware, with web, mobile, and messaging channels in one ecosystem.

![Version](https://img.shields.io/badge/version-1.5.0-blue)
![Python](https://img.shields.io/badge/python-3.11+-34d399)

> **Disclaimer:** FlowCore is an educational and research tool. It does not constitute investment advice. Numbers are code-calculated; narratives are LLM-assisted; every output is provenance-tracked to its data source.

---

## 1. What it is

FlowCore is a **unified AI platform** that turns a local machine into a full market radar and personal agent. It watches global markets (B3, US equities, FX, rates, commodities), classifies the macro regime deterministically, scores decisions with a reasoning chain, executes a **persistent decision ledger** that tracks realised returns against a benchmark, and delivers everything through a Material 3 dark web dashboard, an Android app, Telegram broadcasts, WhatsApp (Evolution API), and Outlook.

```text
┌─────────────────────────────────────────────────────────────┐
│                      FlowCore Ecosystem                     │
├──────────────┬──────────────┬───────────────┬──────────────┤
│  Web Panel   │  Android App │   Telegram     │   WhatsApp   │
│ (browser)    │  (APK v12+)  │  (3 bots)      │ (Evolution)  │
├──────────────┴──────────────┴───────────────┴──────────────┤
│              FastAPI · Cloudflare Tunnel · Token auth       │
├─────────────────────────────────────────────────────────────┤
│  Decision Engine │ Risk & Exposure │ AI Runtime (local first)│
│  Macro Score     │ Rebalancing     │ LocalFirstPolicy LLM    │
│  Observers       │ Portfolio       │ Memory + Flows          │
└─────────────────────────────────────────────────────────────┘
```

## 2. Architecture — "the iceberg"

The UI you see is only the tip. Below the waterline:

| Layer | Module | Responsibility |
|---|---|---|
| **Presentation** | `web/index.html` | Material 3 dark dashboard, 13 tabs, served by the API itself |
| **Presentation** | `android/app` (Kotlin/WebView) | APK mirroring the panel; native bridge for token storage |
| **Decisions** | `runtime/decisions/` | Ordered decision queue, readiness score, reason chain, **persistent decision ledger with realised α vs benchmark** |
| **Market intelligence** | `runtime/market_intelligence/`, `observers/` | SCPX macro score engine, regime classifier (elevated/neutral/depressed), 7+ observers (Treasury, VIX, oil, gold, dollar) |
| **Portfolio** | `runtime/portfolio/` | Holdings, live valuation, exposure (asset class / sector / country / currency), HHI concentration, impact engine |
| **LLM runtime** | `runtime/agent/`, `llm/` | LocalFirstPolicy — Ollama primary (qwen3/gemma3/deepseek-r1 local), OpenRouter cloud fallback with per-call timeouts |
| **Channels** | `runtime/telegram.py`, `whatsapp/`, `outlook/` | Telegram bots (broadcasts + daily close summary 18h BRT), Evolution WhatsApp, Azure AD Outlook |
| **Resilience** | `api/router.py`, `observers/providers/alt_provider.py` | yfinance primary + Trading Economics & Frankfurter fallback sources |

## 3. Key differentiators (vs. state of the art)

We benchmarked against the leading open-source financial agent systems ([TradingAgents](https://github.com/TradingAgents-ai/TradingAgents), [FinRobot](https://github.com/AI4Finance-Foundation/FinRobot), [ai-hedge-fund](https://github.com/virattt/ai-hedge-fund)). FlowCore's unique position:

| Capability | TradingAgents | FinRobot | ai-hedge-fund | **FlowCore** |
|---|---|---|---|---|
| Local-first LLM (Ollama) | cloud-only | hybrid | cloud-only | **yes, with LocalFirstPolicy** |
| Deterministic macro regime (not LLM-guessed) | mixed | no | no | **yes — SCPX engine** |
| Persistent decision ledger with realised α | yes | no | backtest only | **yes + benchmark ^BVSP/^GSPC** |
| Mobile app (APK) | no | desktop only | no | **yes — Material 3** |
| Telegram/WhatsApp/Outlook channels | no | no | no | **yes — 3 bots + Evolution + Azure AD** |
| Brazilian market depth (B3, NTN curve, BRL regime) | US-centric | US-centric | US-centric | **yes — BRL-first** |
| Self-hosted web panel over Cloudflare tunnel | no | no | no | **yes** |

## 4. Getting started

### Prerequisites

Python 3.11+, miniconda (optional), Ollama (for local LLM), cloudflared binary (for external access).

### Run the API

```bash
git clone https://github.com/prdariomarques-ship-it/FlowCore.git
cd FlowCore
cp .env.example .env            # set FLOWCORE_API_TOKEN, FLOWCORE_OLLAMA=..., TELEGRAM tokens
python3 flowcore.py serve       # binds 127.0.0.1:8090
```

### Connect external access

```bash
cloudflared tunnel --url http://127.0.0.1:8090 > ~/tunnel.log 2>&1 &
URL=$(grep -Eo 'https://[a-z0-9-]+\.trycloudflare\.com' ~/tunnel.log | tail -1)
curl -H "X-FlowCore-Token: $TOKEN" $URL/api/health
```

### Production persistence (systemd --user)

Unit files and a self-healing watchdog script are documented in `docs/operations.md`. The FlowCore service restarts automatically on crash and after machine reboot; the watchdog probes `/api/health` every 5 minutes and restarts the stack on failure.

### Mobile

Build with Android Studio or Gradle (`cd android && ./gradlew assembleDebug`). On first launch, open **⚙ Config** and set the tunnel URL + token.

## 5. API highlights

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | health (no token) |
| `GET /api/macro-score/scores` | per-dimension macro scores (yfinance, 30d window) |
| `GET /api/regime/signals` | deterministic regime per dimension |
| `GET /api/market/alt` | fallback sources: Trading Economics + Frankfurter |
| `GET /api/portfolios/{id}/decision` | full decision report (queue, score, reasons) |
| `GET /api/decision-log` | persistent ledger: realised return & α vs benchmark |
| `POST /api/ask` | agent chat (local-first LLM with cloud fallback) |
| `GET /api/integrations/status` | live status: Telegram bots, Ollama, Evolution, Outlook |
| `GET /api/logs` | remote log tail (supports nohup log path) |

All endpoints except market radar require `X-FlowCore-Token` header. The API binds to localhost only; external access goes through the authenticated tunnel.

## 6. Roadmap

| Horizon | Milestone |
|---|---|
| Now | Decision ledger UI parity (web + APK), systemd persistence, cloudflared auto-heal |
| Near | GPU-accelerated local LLM (32GB RAM + NVIDIA RTX tier), larger models (Qwen3.5 32B, Llama 3 70B-Q4) |
| Next | Managed hosting (remove always-on machine dependency), signature-scoped tokens, Outlook deep integration |
| Vision | Fund-as-entity with YAML mandates, backtesting harness, multi-tenant signal marketplace |

## 7. Credits & influences

Design and validation patterns influenced by [TradingAgents](https://github.com/TradingAgents-ai/TradingAgents) (persistent decision ledgers, retry budgets), [FinRobot](https://github.com/AI4Finance-Foundation/FinRobot) (provenance tracking, multi-provider failover), and [ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) (educational disclaimers, roadmap transparency).
