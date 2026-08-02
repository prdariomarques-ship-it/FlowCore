from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from flowcore.intelligence.context import (
    ContextEngine,
    ContextFrame,
    InvalidWorkspaceError,
    PermissionDeniedError,
    Status,
    ContextVersion,
    SchemaValidator,
    CapabilityRegistry,
    CapabilityNotFoundError,
    RuntimeSerializer,
    PassportBuilder,
    TripleContractManager,
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

    # =========================================================================
    # SPRINT 2 EVOLUTION TESTS
    # =========================================================================

    def test_status_enum_values(self):
        self.assertEqual(Status.NOT_READY.value, "NOT_READY")
        self.assertEqual(Status.SCANNING.value, "SCANNING")
        self.assertEqual(Status.READY.value, "READY")
        self.assertEqual(Status.FAILED.value, "FAILED")

    def test_context_version_constants(self):
        self.assertEqual(ContextVersion.SCHEMA_VERSION, "1.0")
        self.assertEqual(ContextVersion.ARCHITECTURE_VERSION, "3.0")

    def test_capability_registry_resolution(self):
        registry = CapabilityRegistry(self.temp_path)

        # Test valid resolution
        battery_cap = registry.resolve("battery")
        self.assertTrue(battery_cap["android_api"])
        self.assertTrue(battery_cap["termux_api"])
        self.assertTrue(battery_cap["shell"])

        # Test invalid resolution
        with self.assertRaises(CapabilityNotFoundError):
            registry.resolve("non_existent_capability_123")

    def test_runtime_serializer(self):
        serializer = RuntimeSerializer()
        telemetry = serializer.serialize(self.temp_path)

        self.assertTrue(telemetry["boot_status"])
        self.assertEqual(telemetry["doctor_status"], "OK")
        self.assertEqual(telemetry["runtime_status"], "READY")
        self.assertIn("disk", telemetry)
        self.assertIn("memory", telemetry)

        # Verify physical file creation
        runtime_file = self.temp_path / "flowcore.runtime.json"
        self.assertTrue(runtime_file.exists())

    def test_passport_builder_integrity_hashes(self):
        frame = ContextFrame()
        frame.workspace_root = self.temp_path
        frame.project = "CoreProject"
        frame.language = "Python"
        frame.type = ["CLI", "Service"]
        frame.status = "READY"
        frame.validated = True

        builder = PassportBuilder()
        passport = builder.build_passport(frame)
        passport_dict = passport.to_dict()

        # Schema and Arch versions
        self.assertEqual(passport_dict["schema_version"], "1.0")
        self.assertEqual(passport_dict["architecture_version"], "3.0")

        # Verify hashes exist and are valid SHA-256 (64 characters hex)
        self.assertEqual(len(passport_dict["workspace_hash"]), 64)
        self.assertEqual(len(passport_dict["context_hash"]), 64)
        self.assertEqual(len(passport_dict["runtime_hash"]), 64)

        # Verifying JSON output serialization
        passport_json = passport.to_json()
        self.assertIn("CoreProject", passport_json)

    def test_triple_contract_manager_generation(self):
        frame = ContextFrame()
        frame.workspace_root = self.temp_path
        frame.project = "TripleThreat"
        frame.language = "Python"
        frame.type = ["CLI"]
        frame.status = "READY"
        frame.validated = True

        manager = TripleContractManager(self.temp_path)
        paths = manager.generate_all_contracts(frame)

        self.assertTrue(paths["context"].exists())
        self.assertTrue(paths["runtime"].exists())
        self.assertTrue(paths["capabilities"].exists())

        # Validate schemas of generated contracts
        with open(paths["context"], "r", encoding="utf-8") as f:
            context_data = json.load(f)
            self.assertTrue(SchemaValidator.validate_context(context_data))
            self.assertEqual(context_data["project"]["name"], "TripleThreat")

        with open(paths["runtime"], "r", encoding="utf-8") as f:
            runtime_data = json.load(f)
            self.assertTrue(SchemaValidator.validate_runtime(runtime_data))

        with open(paths["capabilities"], "r", encoding="utf-8") as f:
            capabilities_data = json.load(f)
            self.assertTrue(SchemaValidator.validate_capabilities(capabilities_data))


if __name__ == "__main__":
    unittest.main()
