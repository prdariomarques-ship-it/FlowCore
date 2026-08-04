from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, List, Optional
import datetime

class InvalidWorkspaceError(Exception):
    """Exception raised when the workspace path is invalid or inaccessible."""
    pass

class ScannerTimeoutError(Exception):
    """Exception raised when a scanning operation times out."""
    pass

class PermissionDeniedError(Exception):
    """Exception raised when accessing a directory violates sandbox permissions."""
    pass


class ContextFrame:
    """Immutability-favoring state frame for the Context Engine pipeline."""

    def __init__(self):
        self.workspace_root: Optional[Path] = None
        self.current_dir: Optional[Path] = None
        self.project: str = "Unknown"
        self.language: str = "Unknown"
        self.runtime: str = "Unknown"
        self.type: List[str] = []
        self.capabilities: List[str] = []
        self.artifacts: List[str] = []
        self.status: str = "NOT_READY"
        self.validated: bool = False
        self.timestamp: str = datetime.datetime.utcnow().isoformat() + "Z"

    def to_dict(self) -> Dict[str, Any]:
        """Convert ContextFrame to a dictionary matching flowcore.context.json specification."""
        return {
            "$schema": "https://flowcore.io/schemas/context.v1.json",
            "schema_version": "1.0.0",
            "validated": self.validated,
            "project": self.project,
            "language": self.language,
            "runtime": self.runtime,
            "type": self.type,
            "capabilities": self.capabilities,
            "workspace": str(self.workspace_root) if self.workspace_root else "",
            "status": self.status,
            "timestamp": self.timestamp,
            "artifacts": self.artifacts,
        }


class BaseContextComponent:
    """Base class for all Context Engine pipeline steps."""

    def run(self, frame: ContextFrame) -> ContextFrame:
        """Run the component logic on the frame, returning the updated frame."""
        raise NotImplementedError("Component must implement the 'run' method.")


class ContextEngine:
    """Orchestrator for FlowCore Context Engine (Phase 1)."""

    def __init__(self, workspace_path: Path):
        self.workspace_path = Path(workspace_path).resolve()
        self.frame = ContextFrame()
        self.frame.current_dir = self.workspace_path

        # Lazy imports to avoid circular dependencies
        from .workspace_scanner import WorkspaceScanner
        from .project_classifier import ProjectClassifier
        from .artifact_detector import ArtifactDetector
        from .context_serializer import ContextSerializer

        # Pipeline execution order for Phase 1
        self._pipeline: List[BaseContextComponent] = [
            WorkspaceScanner(),
            ProjectClassifier(),
            ArtifactDetector(),
            ContextSerializer()
        ]

    def validate(self, force_refresh: bool = False) -> ContextFrame:
        """Execute the pipeline sequentially."""
        self.frame.status = "SCANNING"
        try:
            for component in self._pipeline:
                self.frame = component.run(self.frame)

            # If we reached the end of Phase 1 successfully, transition to READY
            self.frame.status = "READY"
            self.frame.validated = True
            self.frame.timestamp = datetime.datetime.utcnow().isoformat() + "Z"

            # Re-serialize to update final status/timestamp in the written file
            from .context_serializer import ContextSerializer
            self.frame = ContextSerializer().run(self.frame)

        except (InvalidWorkspaceError, PermissionDeniedError) as e:
            self.frame.status = "BLOCKED"
            self.frame.validated = False
            raise e
        except Exception as e:
            self.frame.status = "FAILED"
            self.frame.validated = False
            raise e

        return self.frame
