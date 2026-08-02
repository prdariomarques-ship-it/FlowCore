from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from flowcore.intelligence.context.context_engine import (
    ContextEngine,
    ContextFrame,
    InvalidWorkspaceError,
    PermissionDeniedError,
)
from flowcore.intelligence.context.workspace_scanner import WorkspaceScanner
from flowcore.intelligence.context.project_classifier import ProjectClassifier
from flowcore.intelligence.context.artifact_detector import ArtifactDetector
from flowcore.intelligence.context.context_serializer import ContextSerializer, SerializationError


class TestContextEngine(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name).resolve()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_workspace_scanner_resolves_root(self):
        # Create mock git repo
        (self.temp_path / ".git").mkdir()
        (self.temp_path / "flowcore.py").touch()

        frame = ContextFrame()
        frame.current_dir = self.temp_path

        scanner = WorkspaceScanner()
        frame = scanner.run(frame)

        self.assertEqual(frame.workspace_root, self.temp_path)
        self.assertEqual(frame.status, "VALIDATING")

    def test_workspace_scanner_fallback(self):
        # No git repo anchor
        frame = ContextFrame()
        frame.current_dir = self.temp_path

        scanner = WorkspaceScanner()
        frame = scanner.run(frame)

        self.assertEqual(frame.workspace_root, self.temp_path)

    def test_project_classifier_python(self):
        (self.temp_path / "requirements.txt").touch()
        (self.temp_path / "flowcore.py").touch()
        (self.temp_path / "api").mkdir()

        frame = ContextFrame()
        frame.workspace_root = self.temp_path

        classifier = ProjectClassifier()
        frame = classifier.run(frame)

        self.assertEqual(frame.language, "Python")
        self.assertIn("Python", frame.runtime)
        self.assertIn("CLI", frame.type)
        self.assertIn("Backend", frame.type)

    def test_project_classifier_node_nextjs(self):
        (self.temp_path / "package.json").write_text('{"dependencies": {"next": "14.0.0"}}', encoding="utf-8")

        frame = ContextFrame()
        frame.workspace_root = self.temp_path

        classifier = ProjectClassifier()
        frame = classifier.run(frame)

        self.assertEqual(frame.language, "JavaScript/TypeScript")
        self.assertEqual(frame.runtime, "Node.js")
        self.assertIn("Frontend", frame.type)
        self.assertIn("Next.js", frame.type)

    def test_artifact_detector(self):
        (self.temp_path / "requirements.txt").touch()
        (self.temp_path / "Dockerfile").touch()
        (self.temp_path / "random-file.txt").touch()

        frame = ContextFrame()
        frame.workspace_root = self.temp_path

        detector = ArtifactDetector()
        frame = detector.run(frame)

        self.assertIn("requirements.txt", frame.artifacts)
        self.assertIn("Dockerfile", frame.artifacts)
        self.assertNotIn("random-file.txt", frame.artifacts)

    def test_context_serializer(self):
        frame = ContextFrame()
        frame.workspace_root = self.temp_path
        frame.project = "MockProject"
        frame.language = "Python"
        frame.status = "READY"
        frame.validated = True

        serializer = ContextSerializer()
        serializer.run(frame)

        json_file = self.temp_path / "flowcore.context.json"
        self.assertTrue(json_file.exists())

        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(data["project"], "MockProject")
        self.assertEqual(data["language"], "Python")
        self.assertEqual(data["status"], "READY")
        self.assertTrue(data["validated"])

    def test_context_engine_orchestration(self):
        # Setup mock workspace
        (self.temp_path / "requirements.txt").touch()
        (self.temp_path / "flowcore.py").touch()

        engine = ContextEngine(self.temp_path)
        # Mock frame's current directory to the temp_path
        engine.frame.current_dir = self.temp_path

        frame = engine.validate()

        self.assertEqual(frame.status, "READY")
        self.assertTrue(frame.validated)
        self.assertEqual(frame.project, self.temp_path.name)
        self.assertIn("requirements.txt", frame.artifacts)

        # Verify flowcore.context.json was written to the temp workspace
        json_file = self.temp_path / "flowcore.context.json"
        self.assertTrue(json_file.exists())


if __name__ == "__main__":
    unittest.main()
