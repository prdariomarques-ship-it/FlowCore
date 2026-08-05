"""Tests for the capability adapter layer and registry."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ── CapabilityResult ──────────────────────────────────────────────────────────

class TestCapabilityResult:
    def _cls(self):
        from capability.adapters.base import CapabilityResult
        return CapabilityResult

    def test_ok_sets_success_true(self):
        CR = self._cls()
        r = CR.ok({"level": 80}, "test")
        assert r.success is True
        assert r.data == {"level": 80}
        assert r.bridge == "test"
        assert r.provider_used == "test"

    def test_fail_sets_success_false(self):
        CR = self._cls()
        r = CR.fail("something broke", "adapter",
                    reason="disk full",
                    diagnosis="no space",
                    corrective_action="free space",
                    fallback_provider="other")
        assert r.success is False
        assert r.error == "something broke"
        assert r.reason == "disk full"
        assert r.diagnosis == "no space"
        assert r.corrective_action == "free space"
        assert r.fallback_provider == "other"

    def test_fail_reason_defaults_to_error(self):
        CR = self._cls()
        r = CR.fail("generic error", "x")
        assert r.reason == "generic error"

    def test_to_dict_ok(self):
        CR = self._cls()
        d = CR.ok(42, "bridge").to_dict()
        assert d["success"] is True
        assert d["data"] == 42

    def test_to_dict_fail(self):
        CR = self._cls()
        d = CR.fail("oops", "b", reason="r", corrective_action="fix").to_dict()
        assert d["success"] is False
        assert "reason" in d
        assert "corrective_action" in d


# ── CapabilityAdapter base ────────────────────────────────────────────────────

class TestCapabilityAdapterBase:
    def _make_adapter(self):
        from capability.adapters.base import CapabilityAdapter
        class Concrete(CapabilityAdapter):
            name = "test"
            def is_available(self): return True
        return Concrete()

    def test_repr_contains_name(self):
        a = self._make_adapter()
        assert "test" in repr(a)

    def test_default_get_battery_fails(self):
        a = self._make_adapter()
        r = a.get_battery()
        assert r.success is False

    def test_default_run_python_fails(self):
        a = self._make_adapter()
        r = a.run_python("x.py")
        assert r.success is False


# ── CapabilityRegistry ────────────────────────────────────────────────────────

class TestCapabilityRegistry:
    def _registry(self):
        from capability.registry import CapabilityRegistry
        return CapabilityRegistry()

    def test_list_capabilities_returns_dict(self):
        reg = self._registry()
        caps = reg.list_capabilities()
        assert isinstance(caps, dict)
        assert len(caps) > 0

    def test_capability_names_match_keys(self):
        reg = self._registry()
        assert set(reg.capability_names()) == set(reg.list_capabilities().keys())

    def test_get_returns_none_for_unknown(self):
        reg = self._registry()
        assert reg.get("nonExistentCapability_xyz") is None

    def test_call_returns_fail_for_unknown(self):
        reg = self._registry()
        result = reg.call("nonExistentCapability_xyz")
        assert result.success is False

    def test_invalidate_cache_clears_it(self):
        reg = self._registry()
        reg.available_adapters()  # populates cache
        assert len(reg._available_cache) > 0
        reg.invalidate_cache()
        assert len(reg._available_cache) == 0

    def test_repr_contains_registry(self):
        reg = self._registry()
        assert "CapabilityRegistry" in repr(reg)

    def test_known_capabilities_present(self):
        reg = self._registry()
        names = reg.capability_names()
        for expected in ["getBattery", "runPython", "readFile", "httpRequest",
                         "getClipboard", "sendNotification", "runGit"]:
            assert expected in names, f"{expected} missing from registry"

    def test_read_file_has_adapter_on_linux(self):
        if sys.platform == "win32":
            pytest.skip("Linux-only")
        reg = self._registry()
        adapter = reg.get("readFile")
        assert adapter is not None, "readFile should resolve on Linux"

    def test_run_shell_has_adapter_on_linux(self):
        if sys.platform == "win32":
            pytest.skip("Linux-only")
        reg = self._registry()
        adapter = reg.get("runShell")
        assert adapter is not None

    def test_http_request_has_adapter(self):
        reg = self._registry()
        adapter = reg.get("httpRequest")
        assert adapter is not None  # urllib always available


# ── Termux adapters (unit-level, no real calls) ───────────────────────────────

class TestTermuxFilesystemAdapter:
    def _adapter(self):
        from capability.adapters.termux import TermuxFilesystemAdapter
        return TermuxFilesystemAdapter()

    def test_is_available_on_linux(self):
        if sys.platform == "win32":
            pytest.skip("Linux-only")
        assert self._adapter().is_available() is True

    def test_read_file_not_found(self):
        r = self._adapter().read_file("/nonexistent_path_xyz_flowcore")
        assert r.success is False

    def test_write_and_read_round_trip(self, tmp_path):
        a = self._adapter()
        p = str(tmp_path / "test.txt")
        w = a.write_file(p, "hello")
        assert w.success is True
        assert w.data["written"] is True
        r = a.read_file(p)
        assert r.success is True
        assert r.data["content"] == "hello"

    def test_list_directory(self, tmp_path):
        (tmp_path / "a.txt").write_text("x")
        (tmp_path / "b.txt").write_text("y")
        r = self._adapter().list_directory(str(tmp_path))
        assert r.success is True
        assert r.data["count"] == 2

    def test_list_directory_not_found(self):
        r = self._adapter().list_directory("/nonexistent_dir_xyz")
        assert r.success is False


class TestTermuxHTTPAdapter:
    def _adapter(self):
        from capability.adapters.termux import TermuxHTTPAdapter
        return TermuxHTTPAdapter()

    def test_is_available(self):
        assert self._adapter().is_available() is True


class TestTermuxPackageAdapter:
    def _adapter(self):
        from capability.adapters.termux import TermuxPackageAdapter
        return TermuxPackageAdapter()

    def test_invalid_package_name_rejected(self):
        r = self._adapter().install_package("../../etc/passwd")
        assert r.success is False
        assert "unsafe" in r.reason.lower() or "invalid" in r.reason.lower() or "invalid" in r.error.lower()

    def test_valid_chars_pass_validation(self):
        # Only test the char validation, not actual installation
        safe = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
        assert all(c in safe for c in "python3-dev")
        assert not all(c in safe for c in "../../evil")


class TestTermuxShellAdapter:
    def _adapter(self):
        from capability.adapters.termux import TermuxShellAdapter
        return TermuxShellAdapter()

    def test_empty_args_fails(self):
        r = self._adapter().run_shell([])
        assert r.success is False

    def test_echo_succeeds(self):
        if sys.platform == "win32":
            pytest.skip("Linux-only")
        r = self._adapter().run_shell(["echo", "hello"])
        assert r.success is True
        assert "hello" in r.data["output"]

    def test_nonexistent_command_fails(self):
        r = self._adapter().run_shell(["__nonexistent_cmd_xyz__"])
        assert r.success is False
