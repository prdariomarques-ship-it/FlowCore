from __future__ import annotations

import json
from pathlib import Path
from .context_engine import BaseContextComponent, ContextFrame


class SerializationError(Exception):
    """Exception raised when context serialization fails."""
    pass


class ContextSerializer(BaseContextComponent):
    """Component to serialize the ContextFrame into a flowcore.context.json file."""

    def run(self, frame: ContextFrame) -> ContextFrame:
        if not frame.workspace_root:
            raise SerializationError("Cannot serialize: workspace_root is not set on ContextFrame.")

        file_path = frame.workspace_root / "flowcore.context.json"

        try:
            data = frame.to_dict()
            # Write with nice formatting
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            raise SerializationError(f"Failed to write flowcore.context.json: {e}") from e

        return frame
