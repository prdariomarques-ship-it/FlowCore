"""FlowCore Provider Resolver — selects the right adapter for a capability call.

Resolution order (highest priority first):
    Android (100) → Termux (80) → Linux (50)

The resolver wraps CapabilityRegistry and adds:
- Automatic fallback: if the primary adapter fails, try the next available one
- Diagnostics: records which adapter was used and why fallback occurred
"""
from __future__ import annotations

from loguru import logger

from capability.adapters.base import CapabilityAdapter, CapabilityResult
from capability.registry import CapabilityRegistry, _CAPABILITY_METHOD


class ProviderResolver:
    """Resolves a capability to the best available adapter, with automatic fallback.

    Usage::

        resolver = ProviderResolver()
        result = resolver.resolve("getBattery")
        # result.bridge tells you which adapter handled it
    """

    def __init__(self, registry: CapabilityRegistry | None = None) -> None:
        self._registry = registry or CapabilityRegistry()

    def resolve(self, capability: str, *args, **kwargs) -> CapabilityResult:
        """Call *capability* on the best adapter, falling back on failure.

        Unlike CapabilityRegistry.call(), this tries each available adapter in
        priority order and returns the first successful result.  If all fail,
        it returns the last error with full context.
        """
        method_name = _CAPABILITY_METHOD.get(capability)
        if method_name is None:
            return CapabilityResult.fail(
                f"Unknown capability: '{capability}'", "resolver"
            )

        candidates = self._candidates(capability, method_name)
        if not candidates:
            return CapabilityResult.fail(
                f"No adapter supports '{capability}' on this platform", "resolver"
            )

        last_result: CapabilityResult | None = None
        for adapter in candidates:
            method = getattr(adapter, method_name)
            result: CapabilityResult = method(*args, **kwargs)
            if result.success:
                if last_result is not None:
                    # We fell back — log it so diagnostics can surface this
                    logger.debug(
                        "resolver: '{}' fell back to '{}' (primary failed)",
                        capability, adapter.name,
                    )
                return result
            last_result = result
            logger.debug(
                "resolver: adapter '{}' failed for '{}': {}",
                adapter.name, capability, result.error,
            )

        # All adapters failed
        assert last_result is not None
        return CapabilityResult.fail(
            f"All adapters failed for '{capability}': {last_result.error}",
            "resolver",
        )

    def preferred_adapter(self, capability: str) -> CapabilityAdapter | None:
        """Return the highest-priority adapter that supports *capability*."""
        method_name = _CAPABILITY_METHOD.get(capability)
        if method_name is None:
            return None
        candidates = self._candidates(capability, method_name)
        return candidates[0] if candidates else None

    def capabilities_map(self) -> dict[str, str | None]:
        """Return {capability: preferred_adapter_name | None} for all capabilities."""
        return self._registry.list_capabilities()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _candidates(
        self, capability: str, method_name: str
    ) -> list[CapabilityAdapter]:
        """All available adapters that override *method_name*, in priority order."""
        from capability.registry import _is_base_stub
        result = []
        for adapter in self._registry.available_adapters():
            if not _is_base_stub(adapter, method_name):
                result.append(adapter)
        return result

    def __repr__(self) -> str:
        return f"<ProviderResolver registry={self._registry}>"
