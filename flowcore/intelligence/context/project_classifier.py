from __future__ import annotations

import sys
from pathlib import Path
from .context_engine import BaseContextComponent, ContextFrame


class ProjectClassifier(BaseContextComponent):
    """Component to automatically classify project language, runtime, and type based on workspace files."""

    def run(self, frame: ContextFrame) -> ContextFrame:
        root = frame.workspace_root or Path.cwd().resolve()

        types = []
        languages = []
        runtimes = []

        # 1. Look for Python indicators
        has_python = False
        if (root / "requirements.txt").exists() or (root / "pyproject.toml").exists() or any(root.glob("*.py")):
            has_python = True
            languages.append("Python")
            # Set python runtime
            py_ver = f"Python {sys.version_info.major}.{sys.version_info.minor}"
            runtimes.append(py_ver)

            # Check if CLI
            if (root / "flowcore.py").exists() or (root / "daemon.py").exists():
                types.append("CLI")
                types.append("Service")

            # Check if Backend (e.g. contains fastapi/uvicorn or api directory)
            if (root / "api").exists() or (root / "requirements-api.txt").exists():
                types.append("Backend")

        # 2. Look for Node/JS/TS indicators
        if (root / "package.json").exists():
            languages.append("JavaScript/TypeScript")
            runtimes.append("Node.js")
            types.append("Service")

            # Check Next.js / React
            package_content = ""
            try:
                with open(root / "package.json", "r", encoding="utf-8") as f:
                    package_content = f.read()
            except Exception:
                pass

            if "next" in package_content:
                types.append("Frontend")
                types.append("Next.js")
            elif "react" in package_content:
                types.append("Frontend")
                types.append("React")

        # 3. Look for Go indicators
        if (root / "go.mod").exists():
            languages.append("Go")
            types.append("Backend")

        # 4. Look for Rust indicators
        if (root / "Cargo.toml").exists():
            languages.append("Rust")
            types.append("Library")

        # 5. Look for Android indicators
        if (root / "AndroidManifest.xml").exists() or (root / "build.gradle").exists() or any(root.glob("**/*.kt")):
            languages.append("Kotlin/Java")
            types.append("Mobile")
            types.append("Android")

        # De-duplicate lists
        languages = sorted(list(set(languages)))
        types = sorted(list(set(types)))
        runtimes = sorted(list(set(runtimes)))

        # Populate frame values
        if languages:
            frame.language = languages[0] # Primary language
        if runtimes:
            frame.runtime = runtimes[0] # Primary runtime

        frame.type = types
        frame.project = root.name if root else "Unknown"

        return frame
