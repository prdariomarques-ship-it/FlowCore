from __future__ import annotations

from pathlib import Path
from .context_engine import BaseContextComponent, ContextFrame


class ArtifactDetector(BaseContextComponent):
    """Component to detect specific key artifacts and manifest files in the workspace."""

    # List of key artifacts we look for
    KNOWN_ARTIFACTS = [
        "requirements.txt",
        "requirements-core.txt",
        "requirements-api.txt",
        "pyproject.toml",
        "package.json",
        "bun.lock",
        "Cargo.toml",
        "go.mod",
        "Dockerfile",
        "docker-compose.yml",
        "AndroidManifest.xml",
        "build.gradle",
        "settings.gradle",
        "gradlew"
    ]

    def run(self, frame: ContextFrame) -> ContextFrame:
        root = frame.workspace_root or Path.cwd().resolve()

        found_artifacts = []
        for artifact_name in self.KNOWN_ARTIFACTS:
            # Check direct root and look slightly deeper if needed (e.g. within subdirs)
            # For Phase 1, check root level and common subdirectories for safety
            if (root / artifact_name).exists():
                found_artifacts.append(artifact_name)
            else:
                # Optional: quick search for non-root artifacts (e.g. nested settings.gradle or package.json)
                # But keep it fast and non-recursive beyond 2 levels
                for path in root.glob(f"*/{artifact_name}"):
                    found_artifacts.append(f"{path.parent.name}/{artifact_name}")

        frame.artifacts = sorted(list(set(found_artifacts)))
        return frame
