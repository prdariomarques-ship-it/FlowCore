from __future__ import annotations

import os
from pathlib import Path
from .context_engine import BaseContextComponent, ContextFrame, InvalidWorkspaceError, PermissionDeniedError


class WorkspaceScanner(BaseContextComponent):
    """Component to map current directory, identify workspace root, and validate sandbox permissions."""

    def run(self, frame: ContextFrame) -> ContextFrame:
        # Determine the initial probe path
        probe_path = frame.current_dir or Path.cwd().resolve()

        if not probe_path.exists():
            raise InvalidWorkspaceError(f"Workspace probe path does not exist: {probe_path}")

        # Verify basic read/write access to ensure safe sandbox
        if not os.access(probe_path, os.R_OK):
            raise PermissionDeniedError(f"Read permission denied on workspace path: {probe_path}")
        if not os.access(probe_path, os.W_OK):
            # In some sandboxes write access might be restricted, but we want write permission for outputting context JSON
            # However, we only raise if we can't write to the workspace
            pass

        # Traverse upwards to find workspace root (looking for .git directory or README.md as anchor)
        workspace_root = None
        current = probe_path

        # Up to 10 levels of hierarchy to avoid infinite loops
        for _ in range(10):
            if (current / ".git").exists() or (current / "flowcore.py").exists() or (current / "requirements.txt").exists():
                workspace_root = current
                break
            if current.parent == current: # Reached partition/filesystem root
                break
            current = current.parent

        # Fallback to probe path if no .git or flowcore.py anchor found
        if not workspace_root:
            workspace_root = probe_path

        frame.workspace_root = workspace_root
        frame.current_dir = probe_path
        frame.status = "VALIDATING"

        return frame
