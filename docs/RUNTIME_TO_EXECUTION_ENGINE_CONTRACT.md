# Runtime → Execution Engine Contract — Doctor Flow (Sprint 25)

**From:** Claude Code, Runtime / Capability Registry / Doctor integration
**To:** Codex, Execution Engine
**Baseline this contract was audited against:** `e48851fe5f1e4bca5db1f8b88415195d04f6970f`
**Status:** Runtime side complete and stable. One small, evidence-driven fix was made in this pass (see §5 — a real History-write error-propagation bug, reproduced and corrected) plus its tests; no Execution Engine code was touched. Everything remains local — not committed, not pushed, per this gate's explicit instruction.

This is a narrow, purpose-built contract document (not a full architecture tour — see `docs/HANDOFF_CODEX.md` for that). It exists so Codex does not have to infer any of the following from the code.

---

## 1. What already works today, with no Execution Engine stage

The Doctor Flow is real and fully traverses the Runtime **today**, end to end, without any `runtime/executor.py` involvement:

```
flowcore.py:747 cmd_doctor()
  -> runtime/core.py:89 FlowCoreRuntime.run_doctor()
       -> capability/resolver.py:32 ProviderResolver.resolve("getCpuInfo"|"getMemoryInfo"|"getDiskUsage")
            -> capability/registry.py:26 _CAPABILITY_METHOD lookup
                 -> capability/adapters/linux.py get_cpu_info() / get_memory_info() / get_disk_usage()
       -> doctor/service.py:195 DoctorService.run()  (35 component checks)
```

`runtime/executor.py` (Codex's `ACTIONS` dispatch table, used today only by Flows: `note`/`todo`/`agenda`/`ask`/`search`/`import_markdown`) is **not part of this path** and was not touched. This contract exists in case Codex's Execution Engine work for this sprint means formally routing Doctor invocation through that same dispatch mechanism — see §10 for the one open question this raises.

---

## 2. Capability identifier & payload

Doctor is not itself one capability — it is an aggregate of three individual capability calls plus one pre-existing service (`DoctorService`). The three capabilities, already registered and resolvable:

| Capability identifier | Adapter method | Payload (positional args) |
|---|---|---|
| `"getCpuInfo"` | `get_cpu_info(self)` | none |
| `"getMemoryInfo"` | `get_memory_info(self)` | none |
| `"getDiskUsage"` | `get_disk_usage(self, path: str = "/")` | one positional `str` path (Doctor calls it with `str(runtime.root)`) |

Identifiers are plain strings, resolved via `capability/registry.py:26`'s `_CAPABILITY_METHOD` dict — this is the **only** place capability names are declared. No enum, no registry-of-registries. If Codex needs to invoke a capability directly (bypassing `run_doctor()`), the call shape is:

```python
from capability.resolver import ProviderResolver
result = ProviderResolver().resolve("getCpuInfo")   # or getMemoryInfo / getDiskUsage(path)
```

---

## 3. Execution contract — `CapabilityResult` (`capability/adapters/base.py:18`)

Every capability call — success or failure — returns this dataclass, never raises for a "capability not supported" or "no adapter" condition:

```python
CapabilityResult(
    success: bool,
    data: Any = None,                 # present only when success=True
    error: str | None = None,         # present only when success=False
    bridge: str = "",                 # which adapter handled it, e.g. "linux"
    reason: str = "",                 # WHY it failed, one sentence
    diagnosis: str = "",              # extra technical context
    corrective_action: str = "",      # what to do about it
    provider_used: str = "",
    fallback_provider: str = "",
)
```

`.to_dict()` (`capability/adapters/base.py:62`) serializes it to exactly:
- success case: `{"success": True, "data": ..., "bridge": ...}`
- failure case: `{"success": False, "error": ..., "reason": ..., "diagnosis": ..., "corrective_action": ..., "provider_used": ..., "fallback_provider": ...}`

This is a stable, existing contract used by every capability in the registry (battery, clipboard, disk, network, ...) — **reuse it, do not invent a new result envelope for Doctor.**

---

## 4. Doctor aggregate contract — `FlowCoreRuntime.run_doctor()` (`runtime/core.py:89`)

```python
from runtime.core import FlowCoreRuntime
report: dict = FlowCoreRuntime().run_doctor()
```

Returns, always JSON-serializable:

```python
{
    "generated_at": "<ISO-8601 UTC>",
    "environment": {"termux": bool, "android": bool, "python_version": str, "os_name": str, "prefix": str},
    "cpu":    <CapabilityResult.to_dict()>,
    "memory": <CapabilityResult.to_dict()>,
    "disk":   <CapabilityResult.to_dict()>,
    "components": <DoctorReport.to_dict()>,   # doctor/service.py:62
}
```

`components` shape (`doctor/service.py:81`, `DoctorReport.to_dict()`):
```python
{"passed": int, "warned": int, "failed": int, "healthy": bool,
 "checks": [{"name": str, "status": "ok"|"warn"|"fail"|"skip", "message": str, "fix": str}, ...]}
```

This is the one call Codex needs if the Execution Engine is meant to run Doctor as a unit rather than orchestrating the three capabilities itself.

---

## 5. Errors — how they propagate

- **Capability-level failure** (no adapter, adapter raised, platform unsupported): never an exception. Always `CapabilityResult(success=False, ...)`, folded into the report via `.to_dict()`. A caller must check `report["cpu"]["success"]` etc. — a failed reading is real signal ("this platform can't read memory this way"), not something to paper over.
- **Component-check failure**: `DoctorService.run()` (`doctor/service.py:195-210`) catches exceptions **per check** and converts them to `CheckResult(status=FAIL, message=f"Check raised exception: {exc}")` — one bad check never aborts the other 34.
- **`run_doctor()` no longer raises for a History-write failure.** `_write_doctor_history()` (`runtime/core.py:132`) previously did an unguarded `path.parent.mkdir()` + `open(path, "w")`; if `~/.flowcore` was not writable (permissions, read-only FS, disk full — realistic on Termux/Android, exactly what `doctor/service.py`'s `termux_storage` check exists to detect), the exception propagated out of `run_doctor()` uncaught, and `flowcore.py:757`'s `try/except Exception` reported the **entire** Doctor run as failed — even though CPU/memory/disk/components had already been computed successfully. Reproduced (chmod a temp `.flowcore` to `0o500`, confirmed `PermissionError` escaping `run_doctor()`), then fixed in this gate: the write is now wrapped in `try/except OSError`, logging a `logger.warning(...)` and returning normally — mirrors the exact same degrade-gracefully convention already used by `api/router.py:317-318`'s `/api/status` Doctor section. Covered by `tests/test_runtime_core.py::TestRunDoctor::test_unwritable_history_does_not_fail_the_diagnostic` (confirmed failing against the pre-fix code, per this gate's reverse-test). The report shape is unaffected either way — Execution Engine callers can rely on `run_doctor()` never raising for a persistence-only problem.

---

## 6. Context required to call `run_doctor()`

None beyond a normal Python process on the FlowCore repo root: `FlowCoreRuntime()`'s constructor reads `config/default.json` (via `config.loader.load_config()`) and computes `platform_info` — no arguments, no prior boot step, no dependency on `RuntimeKernel.boot()` having run. It is safe to call cold.

Note the naming collision this audit re-confirms: `runtime/kernel.py`'s `RuntimeKernel.boot()` has its own, much smaller "Doctor" step (`_quick_health()`, 4 heuristic checks, non-blocking, part of the boot sequence) — this is **not** the same thing as `DoctorService`/`run_doctor()`. Do not conflate the two when wiring anything.

---

## 7. Observability

Existing convention only, nothing new: `loguru`'s `logger`, already imported and used identically throughout `runtime/`, `doctor/`, `capability/`. `run_doctor()` logs one `logger.info(...)` summary line per call (`runtime/core.py:121`) with `cpu`/`memory`/`disk` success booleans and the components pass/total count. If the Execution Engine wraps this in a task/step abstraction, it should log through the same `loguru` logger, not a parallel system.

---

## 8. History

`run_doctor()` persists its own return value, verbatim, to `~/.flowcore/flowcore.doctor.json` after every call (`runtime/core.py:132`), mirroring `RuntimeKernel`'s pre-existing convention for `~/.flowcore/flowcore.runtime.json`. This is a **last-run snapshot, overwritten every call** — not a time series. If the Execution Engine needs a history *log* (multiple runs, queryable over time), that is new persistence and out of this gate's scope — flag it as a decision for ChatGPT rather than building it silently into either side.

---

## 9. Invariants (do not break these)

1. `CapabilityResult`/`.to_dict()` is the only result envelope for capability calls — do not wrap it in another envelope.
2. Capability identifiers are the string keys in `capability/registry.py`'s `_CAPABILITY_METHOD` — the only place new ones are declared.
3. No capability call raises for "unsupported here" — that's `success=False`, always.
4. `run_doctor()` never fabricates a result: a platform that can't provide a reading reports `success=False`, not a placeholder value. Do not "smooth over" a failure into a synthetic success anywhere downstream.
5. `runtime/executor.py`'s `ACTIONS` are `Callable[[dict], Awaitable[Any]]` wrapping `service.py` functions only (`runtime/executor.py:17-27`) — `run_doctor()` itself is **synchronous**. If Doctor is wired into `ACTIONS`, it needs an `async` shim; the natural place for it, following the existing convention exactly, is a one-line `service.py` wrapper (e.g. `async def run_doctor() -> dict: return FlowCoreRuntime().run_doctor()`), not a change to `run_doctor()`'s own signature.

---

## 10. (a) vs (b) — investigated with evidence, not preference

Today, `flowcore.py doctor` calls `FlowCoreRuntime.run_doctor()` **directly** — there is no Execution Engine stage in the shipped, tested implementation, and the flow works correctly without one (463 passing tests, real CPU/memory/disk/component data).

The Sprint 25 pipeline diagram names an explicit `Capability Registry → Execution Engine → Doctor` stage. Two readings were possible:

- **(a)** `ProviderResolver.resolve()` (and `CapabilityRegistry.call()`) already *is* "execution" for every capability's purposes — Codex's Execution Engine is a separate, orthogonal concern (Flow steps: queuing/planning/retries for user-authored automations), not something every capability call must route through.
- **(b)** Doctor must be formally registered as a `runtime/executor.py` `ACTIONS` entry so every invocation — CLI included — goes through the same Execution Engine as Flows do.

**Evidence gathered (grep against the actual repo, not assumption):**

1. **Every existing capability already resolves-and-executes in one step, repo-wide, not just for Doctor.** `service.py:230-259` has seven async wrappers (`get_battery`, `get_disk_usage`, `get_clipboard`, `send_notification`, `list_installed_apps`, `get_android_info`, `get_wifi_info`) that all follow the identical pattern `(await asyncio.to_thread(_registry.call, "<Capability>", ...)).to_dict()`. This is the established, repo-wide convention `run_doctor()` follows — Doctor is not inventing a new pattern by resolving-and-executing directly.
2. **None of those seven pre-existing capabilities are registered in `runtime/executor.py`'s `ACTIONS`** (`grep -n "ACTIONS" runtime/executor.py` → only `note/todo/agenda/ask/search/import_markdown`, all `service.py` functions unrelated to capabilities). If "every capability call must go through the Execution Engine" were already this codebase's rule, at least one of the seven would already be wired in. None are.
3. **Zero references to `"doctor"` as a Flow action anywhere** — `grep -rn '"doctor"'` across `flowcore.py`, `mcp_server.py`, `storage/flow_repo.py`, and every test returns only the unrelated `/api/status` `"doctor"` key (`api/router.py:287,314,318` — DoctorService's *own* result field name, not a Flow-executor action). No Flow schema, CLI help text, or test ever proposes `{"action": "doctor", ...}`.
4. **`DoctorService` already has three independent real consumers today** (`flowcore.py:870` in `cmd_status`, `api/router.py:313` in `/api/status`, `installer/setup.py:237,386`, `passport/generator.py:97`) — none of them route through `runtime/executor.py` either. Wiring Doctor into `ACTIONS` would make the CLI's *fourth* consumer inconsistent with the other three, not more consistent.
5. **`runtime/executor.py`'s own docstring** states its `ACTIONS` contract is deliberately minimal by design ("no queue, no worker pool, ... that machinery was removed as unused complexity in Sprint 14") — it exists specifically for sequential, user-authored Flow steps, not as a universal capability-invocation gateway.

**Conclusion: (a).** This is not a preference call — every one of the 10 investigation questions resolves the same direction: no real consumer for a `"doctor"` `ACTIONS` entry exists this sprint (Q9), registering one would be an abstraction with zero consumers (Q10 — directly forbidden by this gate's own scope rules), and `ProviderResolver`/`CapabilityRegistry` resolving-and-executing is the pre-existing, repo-wide norm for every capability, not a shortcut specific to Doctor (Q8). No wiring change was made. If a concrete need for Doctor-as-a-Flow-step emerges later, the minimal path (§9.5: one `service.py` async shim + one `ACTIONS` entry) remains a five-minute change, not a redesign — but it should wait for that real consumer to exist.
