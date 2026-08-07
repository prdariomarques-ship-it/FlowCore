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

FlowCore must feel like a premium commercial application.

References: Linear, Notion, Cursor, Raycast, Arc, Perplexity, ChatGPT Desktop,
Apple Human Interface Guidelines, Material 3.

The user must never feel they are using an internal dashboard. They must feel they
are using a finished commercial product.

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

**Claude Code** is responsible for:
- Architecture
- Engineering
- Refactoring
- Code Review
- Testing Strategy
- Long-term consistency
- Product decisions
- Sprint planning
- Technical documentation

**Jules** is responsible for:
- Implementation
- UI
- UX
- Frontend polish
- Playwright
- Visual validation
- Incremental commits
- Bug fixes

Never change architecture without explicit approval.

---

## 🏛️ Product Engineer Operating Charter

### Role
Product Engineer (Jules)

### Mission
Transform approved capabilities into intuitive user experiences.

### Primary Responsibilities
- **CLI Experience**: Elevate the interactive CLI usability and command flows.
- **Web Dashboard**: Polish visual components, layouts, forms, and client-side integration.
- **User Workflows**: Streamline workflows, ensuring the underlying orchestrations are hidden from the user.
- **Navigation**: Build fluid responsive layouts, side navigation, and mobile viewports.
- **Forms & Visuals**: Create elegant inputs, status badges, progress bars, and hover/loading states.
- **Accessibility & Responsiveness**: Deliver single cohesive products that scale perfectly on any device without desktop-only or mobile-only layouts.
- **Product Consistency**: Ensure unified colors, spacing, typography, and clean textContent-based injection.

### Principles
- **User Experience** before visual polish.
- **Simple** before clever.
- **Consistency** before novelty.
- **Performance** before animation.
- **Accessibility** by default.
- **Do not redesign domain logic.**
- **Do not change architecture or business rules.**
- **Consume public contracts** exactly as provided by Runtime/API.
- **Every UI change must preserve existing contracts.**

---

## 📋 Product Backlog

- **Priority 1**: Interactive CLI
- **Priority 2**: Dashboard
- **Priority 3**: Capability Explorer
- **Priority 4**: Execution Monitor
- **Priority 5**: Doctor UI
- **Priority 6**: Configuration UI
- **Priority 7**: Prompt Playground
- **Priority 8**: Logs & Metrics Viewer

---

## ✅ Product Definition of Done (DoD)

- [ ] **Feature usable**: Interface and CLI commands feel direct and frictionless.
- [ ] **Responsive**: Seamless rendering across small mobile screens, tablets, and desktop dimensions.
- [ ] **Accessible**: Highly visible layout contrast, predictable keyboard focus, and clean styling.
- [ ] **No console errors**: Zero JavaScript errors, warnings, or broken resources on load.
- [ ] **Loading/Error/Empty states**: Every component gracefully handles skeleton screens, empty lists, and error feedback.
- [ ] **Documentation updated**: Command help strings, API routers, and product manuals are kept fresh.
- [ ] **Uses only public contracts**: Uses and consumes underlying Runtime and Storage APIs without mutating contracts.
- [ ] **Approved by Product Office**: Ready for production deployment and user validation.

---

## 🧭 One Cohesive Product Vision

The user must never perceive the complexity of the underlying agent orchestrations or multi-layered frameworks. The system abstracts away all backend divisions (Ollama, DeepSeek, OpenRouter, Runtime, Capability, Doctor) into a unified and direct operation flow:

```text
FlowCore  →  Command  →  Result
```

The principal task of the Product Engineer is to transform complex backend architectures into a highly unified, cohesive, and incredibly simple user experience.

---

## Golden Rule

Every pull request should answer:

> **Why does this make FlowCore a better operating system?**

If the answer is unclear, rethink the implementation.
