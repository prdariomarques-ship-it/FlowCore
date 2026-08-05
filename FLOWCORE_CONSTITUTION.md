# FlowCore Constitution v1.0

> This document is the standing reference for FlowCore's product vision, architecture
> principles, and design philosophy. It is not a disposable prompt — it is the
> constitution the project is built against.
>
> **At the start of any new session:** read this file before proposing or making any
> architecture, product, or UI decision. When a request conflicts with this document,
> say so explicitly rather than silently complying or silently overriding it.

---

## Mission

FlowCore is not another AI assistant.

FlowCore is a **Personal Execution Operating System**.

Its purpose is to observe, understand, decide, and execute.

The long-term goal is to become the daily operating system for professionals,
investors, wealth managers, entrepreneurs, and knowledge workers.

The user should spend less time operating software and more time making decisions.

Every feature must move the product toward this objective.

---

## Product Philosophy

Never build isolated features. Build a coherent platform.

Every module must integrate naturally with every other module.

Every new capability should become available through:

- Web UI
- CLI
- MCP
- Runtime
- Service Layer
- Future Desktop Application
- Future Android Application

Never create parallel implementations.

---

## Long-Term Vision

FlowCore evolves toward six major domains.

### Productivity
Notes, Calendar, Email, Tasks, Knowledge Base, Automation, Execution.

### Intelligence
Chat, Memory, RAG, Search, Agents, Reasoning, Planning, Decision Support.

### Market Intelligence
SCPX, Macro Monitor, Portfolio Intelligence, Macro Score Engine, Risk Engine,
Recommendation Engine, Investment Committee, Watchlists, Alerts.

### Integrations
Outlook, WhatsApp, Android, Open Finance, Broker APIs, Calendar, Email, Cloud Storage.

### Automation
Flows, Execution Engine, Scheduler, Notifications, Rules, Actions.

### Platform
CLI, FastAPI, Web UI, MCP, Desktop, Android.

---

## Architecture Principles

- Never duplicate logic.
- Service Layer is the single source of truth.
- Runtime communicates with providers.
- Storage owns persistence.
- FastAPI only exposes endpoints.
- CLI only orchestrates.
- MCP only exposes tools.
- Web UI only consumes services.
- No business logic inside routes.
- No business logic inside UI.
- No business logic inside CLI.

---

## Code Quality

Every implementation must:

- Reuse existing services.
- Avoid abstractions without consumers.
- Avoid speculative engineering.
- Keep architecture simple.
- Prefer deletion over duplication.
- Prefer composition over inheritance.
- Preserve backward compatibility.

---

## Testing

Every implementation must pass:

- ruff
- pytest
- Playwright
- Manual browser validation

No console errors. No network errors. CI must remain green.

---

## User Experience

Frontend quality is a first-class requirement, not a finishing touch.

FlowCore must feel like a premium commercial application.

References: Linear, Notion, Cursor, Raycast, Arc, Perplexity, ChatGPT Desktop,
Superhuman, Vercel, Apple Human Interface Guidelines, Material 3.

The user must never feel they are using an internal dashboard. They must feel they
are using a finished commercial product.

Do not build generic developer dashboards. Avoid placeholder dashboards and
generic admin templates.

**Never stop at "functional."** Evaluate your own UI critically. If the result
looks like an internal developer tool, redesign it. Iterate until it reaches
production-grade quality — "it works" is not the finish line.

---

## Design System

- Single Design System.
- Dark Theme.
- Zinc / Deep Slate.
- Rounded corners.
- Soft shadows.
- Large spacing.
- Minimal typography.
- Component reuse.
- No duplicated CSS.
- No isolated styles.
- No inconsistent colors.

Prefer specialized design tools over handwritten HTML/CSS whenever they produce
a better result while preserving compatibility with the existing backend. If a
specialized tool, MCP server, or connected design application (Figma, Canva,
Lovable, Adobe Express, or another UI-focused environment) can materially
improve interface quality, use it instead of hand-rolling markup. The backend
architecture is already consolidated — the open problem is visual/experience
quality, and that is what specialized tools exist to solve.

---

## Responsive Design

Every screen must work perfectly on: Desktop, Tablet, Android, Portrait, Landscape,
and the future Desktop Client.

Never create Desktop-only layouts. Never create Mobile-only layouts.

One product. One experience.

---

## Interaction Design

Every interaction should provide feedback: hover, focus, touch, loading, skeleton,
progress, success, failure, empty state.

Animations must be subtle.

---

## Dashboard Philosophy

The Dashboard is not a page. The Dashboard is the operating center.

When the application opens, the user should immediately understand:

System Health, AI Status, Integrations, Market, Portfolio, Agenda, Tasks, Flows,
Alerts, Recommendations.

---

## SCPX Vision

FlowCore will include SCPX. SCPX is not a news reader — it is a financial
interpretation engine.

Pipeline:

```
Market Data
    ↓
Macro Score Engine
    ↓
Regime Engine
    ↓
Impact Engine
    ↓
Portfolio Engine
    ↓
Recommendation Engine
    ↓
LLM Explanation
    ↓
Push Notifications
```

The LLM explains. It does not decide.

---

## AI Philosophy

LLMs are language layers. Decision engines belong to FlowCore.

Never delegate deterministic business logic to an LLM.

Every recommendation should be explainable.

---

## Integrations

All integrations must expose: Health, Capabilities, Latency, Configuration, Errors,
Availability.

Never expose secrets.

---

## Future Modules

Portfolio, Investment Committee, Macro Dashboard, Execution Center, Risk Dashboard,
CRM, Open Finance, Knowledge Graph, Memory Graph.

---

## Performance

Prefer fast responses. Avoid sequential I/O. Use concurrency where appropriate.
Avoid unnecessary network requests.

---

## Security

Never log secrets. Never expose credentials. Mask tokens. Respect least privilege.

---

## Documentation

Every architectural decision must be documented. Architecture evolves with code.
Documentation must never drift.

---

## Agent Responsibilities

**Claude Code** is:
- **System Architect** — architecture, engineering, refactoring, code
  review, testing strategy, long-term consistency, product decisions,
  sprint planning, technical documentation.
- **Product Designer / UX Architect** — owns UI architecture. For every
  major UI sprint: produce a high-quality visual mockup using the
  available design MCPs (Figma, Adobe, Canva, or equivalent); define the
  design system, layout, spacing, typography, components, interaction
  patterns, responsiveness, and accessibility; deliver the mockup
  together with a detailed implementation specification. **The mockup is
  the source of truth**, not a text description of the intended look.

**Jules** is:
- **Frontend Engineer / Backend Engineer / Testing / Integration / CI** —
  implementation only. Faithfully reproduces the approved design (the
  mockup) while preserving the existing backend architecture and APIs.
  Does not make visual-design decisions of its own.

Rule of thumb for scoping design work: small UI adjustments only need a
textual specification. Medium or large interface changes always get a
visual reference (mockup) produced before implementation starts.

Never change architecture without explicit approval.

---

## Golden Rule

Every pull request should answer:

> **Why does this make FlowCore a better operating system?**

If the answer is unclear, rethink the implementation.
