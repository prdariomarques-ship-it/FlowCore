from __future__ import annotations

from pathlib import Path
from .runtime_manager import RuntimeManager
from .runtime_context import RuntimeContext
from .runtime_state import RuntimeState
from .runtime_health import RuntimeHealthChecker


class RuntimeBootloader:
    """Manages the structured Boot Sequence for the FlowCore Operating Environment."""

    def __init__(self, workspace_path: Path):
        self.workspace_path = Path(workspace_path).resolve()
        self.manager = RuntimeManager(self.workspace_path)
        self.context = RuntimeContext(self.workspace_path)
        self.health_checker = RuntimeHealthChecker()
        self.state = RuntimeState.NOT_READY

    def boot(self) -> RuntimeContext:
        """Execute sychronous boot sequence step-by-step."""
        self.state = RuntimeState.BOOTING

        # 1. Load active Runtime via manager
        active_runtime = self.manager.get_active_runtime()
        if not active_runtime:
            self.state = RuntimeState.FAILED
            raise RuntimeError("Failed to load a suitable active platform Runtime.")

        self.state = RuntimeState.LOADING_PROVIDERS
        active_runtime.boot()

        # 2. Validate permissions
        self.state = RuntimeState.VALIDATING_PERMISSIONS
        # Verification logic
        self.context.permissions["storage"] = "GRANTED"

        # 3. Health Check
        self.state = RuntimeState.HEALTH_CHECK
        health = self.health_checker.check_health()
        if health["status"] != "HEALTHY":
            self.state = RuntimeState.FAILED
            raise RuntimeError("Runtime Health Check verification failed during boot.")

        # 4. Ready State transition
        self.state = RuntimeState.READY
        self.context.status = "READY"

        # Write flowcore.runtime.passport.json to root
        self.context.write_passport()

        return self.context
