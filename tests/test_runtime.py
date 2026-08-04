from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from flowcore.runtime import (
    RuntimeManager,
    RuntimeState,
    RuntimeContext,
    RuntimeBootloader,
    RuntimeHealthChecker,
)
from flowcore.runtime.runtime_logger import RuntimeLogger
from flowcore.runtime.android.battery import AndroidBatteryProvider
from flowcore.runtime.android.wifi import AndroidWifiProvider
from flowcore.runtime.android.clipboard import AndroidClipboardProvider
from flowcore.runtime.termux.termux_api import TermuxApiProvider
from flowcore.runtime.termux.shell import TermuxShellProvider
from flowcore.runtime.termux.python import TermuxPythonProvider


class TestFlowCoreRuntime(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name).resolve()

    def test_runtime_states(self):
        self.assertEqual(RuntimeState.NOT_READY.value, "NOT_READY")
        self.assertEqual(RuntimeState.BOOTING.value, "BOOTING")
        self.assertEqual(RuntimeState.READY.value, "READY")

    def test_runtime_context_and_passport(self):
        context = RuntimeContext(self.temp_path)
        self.assertEqual(context.platform, "Android/Termux")
        self.assertEqual(context.status, "NOT_READY")

        passport_path = context.write_passport()
        self.assertTrue(passport_path.exists())

        with open(passport_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(data["runtime_id"], "termux_runtime_01")
        self.assertEqual(data["status"], "NOT_READY")
        self.assertIn("battery", data["providers"])

    def test_runtime_logger(self):
        logger = RuntimeLogger()
        entry = logger.log_execution("getBattery", {"percentage": 88}, None)

        self.assertEqual(entry["capability"], "getBattery")
        self.assertEqual(entry["rollback_status"], "NONE")
        self.assertEqual(len(logger.logs), 1)

    def test_runtime_health_checker(self):
        checker = RuntimeHealthChecker()
        health = checker.check_health()
        self.assertEqual(health["status"], "HEALTHY")
        self.assertEqual(health["disk"], "OK")

    def test_runtime_manager_and_capability_execution(self):
        manager = RuntimeManager(self.temp_path)

        # Check automatic selection
        best_runtime = manager.get_active_runtime()
        self.assertIsNotNone(best_runtime)

        # Test switching
        manager.switch_runtime("android")
        active = manager.get_active_runtime()
        self.assertEqual(active.platform, "Android")

        # Since we are in a headless sandbox, termux-battery-status does not exist in the path.
        # It must successfully auto-detect this and return status NOT_IMPLEMENTED!
        res_battery = active.execute_capability("getBattery")
        self.assertEqual(res_battery["status"], "NOT_IMPLEMENTED")

        # Switch to termux
        manager.switch_runtime("termux")
        active = manager.get_active_runtime()
        self.assertEqual(active.platform, "Termux")

        # Test termux execution (returns NOT_IMPLEMENTED because of missing binaries on sandbox container)
        res_pkg = active.execute_capability("getBattery")
        self.assertEqual(res_pkg["status"], "NOT_IMPLEMENTED")

    def test_runtime_boot_sequence(self):
        bootloader = RuntimeBootloader(self.temp_path)
        context = bootloader.boot()

        self.assertEqual(bootloader.state, RuntimeState.READY)
        self.assertEqual(context.status, "READY")

        # Verify physical passport creation on root
        passport_file = self.temp_path / "flowcore.runtime.passport.json"
        self.assertTrue(passport_file.exists())

        with open(passport_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["status"], "READY")

    def test_individual_providers(self):
        # Android providers
        bat = AndroidBatteryProvider().get_battery()
        self.assertEqual(bat["source"], "Android SDK BatteryManager")
        wifi = AndroidWifiProvider().get_wifi()
        self.assertEqual(wifi["source"], "Android SDK WifiManager")
        clip = AndroidClipboardProvider().get_clipboard()
        self.assertIn("Android SDK", clip)

        # Termux providers (real binaries missing on container, must return NOT_IMPLEMENTED)
        t_api = TermuxApiProvider().get_battery()
        self.assertEqual(t_api["status"], "NOT_IMPLEMENTED")

        t_shell = TermuxShellProvider().run_command("ls")
        self.assertIn("ls", t_shell)
        t_py = TermuxPythonProvider().install_package("numpy")
        self.assertEqual(t_py["source"], "pip")


if __name__ == "__main__":
    unittest.main()
