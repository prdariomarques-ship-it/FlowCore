# FlowCore Platform Constitution (PRINCIPLES.md)

This document represents the immutable constitution of the FlowCore platform. Every architectural decision, service evolution, and agent implementation must rigidly comply with the core principles defined herein.

---

## 1. Core Platform Principles

*   **Android First:** The primary, native production platform of the FlowCore runtime is a mobile smartphone environment running Android via Termux. Every optimization, memory management design, and resource query must prioritize mobile battery, CPU, and disk efficiency.
*   **Runtime First:** Real-world execution boundaries (Runtimes) dictate the capabilities of the system. The platform must know exactly what physical environment is running before any workflow or agent task starts execution.
*   **Capability First:** Intention is the only interface exposed to AI agents. Raw terminal shell commands are completely abstracted behind standardized, secure, and declarative Capabilities.
*   **Zero Raw Commands:** Execution of raw, bare-metal bash or CLI scripts directly from LLMs is strictly prohibited. Commands must always be mapped and resolved through verified Capability Adapters.
*   **Everything is a Capability:** Any platform action (filesystem, network, power check, install) is modeled, logged, and resolved as a structured capability.
*   **Kernel Must Stay Small:** The FlowCore Kernel acts as a minimal Microkernel, delegating all operations (telemetry, boot, health, scheduler) to independent Kernel Services and dynamic modules.
*   **Providers Are Replaceable:** Low-level execution drivers (Providers) are interchangeable. A capability must resolve transparently whether it runs via Android APIs, Termux CLI, local python, or fallback bridges.
*   **Adapters Hide Implementation:** Platform adapters encapsulate and completely hide operating system complexities (Android, Termux, Linux, Windows) from reasoning engines and AI agents.
*   **Registries Are Single Source of Truth:** System states, available runtimes, capabilities, and active plugins are stored in secure, read-only Registries acting as the single source of truth.
*   **Every Runtime Must Be Discoverable:** Runtimes must register dynamically and declare their priorities, health, and list of supported capabilities.
*   **Every Capability Must Have Fallback:** Critical capabilities (such as power, networking, and storage) must specify secure fallback routes (ex: TermuxAPI -> AndroidAPI -> Fallback Mock) to prevent catastrophic execution crashes.
*   **Every Agent Must Use Passport:** No agent or sub-agent (Jules, Qwen, GLM, Claude Code, Codex, Manus, Gemini) is authorized to perform implementations without first reading and validating the current, unexpired sessional `FlowCorePassport` and `Runtime Session`.
*   **No Direct Shell Execution:** The shell is a low-level implementation detail of a Capability Provider; it is completely invisible to higher-level reasoning engines.

---

## 2. Platform Architecture Layers
The platform execution flow must strictly map to the following decoupled stack:

```
FlowCore Brain (Agente AI)
       ↓
Intent Engine
       ↓
Reasoning Engine (Reasoner)
       ↓
Execution Engine
       ↓
Runtime Manager (Registry & Selector)
       ↓
Runtime Kernel (Orchestrator)
       ↓
Android / Termux Runtime
       ↓
Capability Adapters (Android APIs / Linux APIs / Termux API)
       ↓
Hardware (Battery, Network, Disk)
```
