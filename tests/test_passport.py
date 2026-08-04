"""Tests for passport — Passport, PassportGenerator, PassportValidator."""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ── Schema tests ──────────────────────────────────────────────────────────────

class TestAgentIdentity:
    def test_basic_fields(self):
        from passport.schema import AgentIdentity
        a = AgentIdentity(name="test_agent", version="1.2.3")
        assert a.name == "test_agent"
        assert a.version == "1.2.3"

    def test_to_dict_round_trip(self):
        from passport.schema import AgentIdentity
        a = AgentIdentity(name="agent", version="0.1.0", description="desc")
        d = a.to_dict()
        a2 = AgentIdentity.from_dict(d)
        assert a2.name == a.name
        assert a2.version == a.version
        assert a2.description == a.description


class TestRuntimeInfo:
    def test_fields(self):
        from passport.schema import RuntimeInfo
        r = RuntimeInfo(
            platform="linux", is_android=False, is_termux=False,
            has_internet=True, python_version="3.11.0",
            capabilities=["runPython"],
        )
        assert r.platform == "linux"
        assert r.capabilities == ["runPython"]

    def test_to_dict_round_trip(self):
        from passport.schema import RuntimeInfo
        r = RuntimeInfo(
            platform="termux", is_android=True, is_termux=True,
            has_internet=False, python_version="3.12.0",
        )
        d = r.to_dict()
        r2 = RuntimeInfo.from_dict(d)
        assert r2.platform == r.platform
        assert r2.is_android == r.is_android


class TestPassport:
    def _make(self, **kw):
        from passport.schema import AgentIdentity, RuntimeInfo, Passport
        agent = AgentIdentity(name="test")
        runtime = RuntimeInfo(
            platform="linux", is_android=False, is_termux=False,
            has_internet=True, python_version="3.11",
        )
        return Passport(
            agent=agent, runtime=runtime,
            capabilities=["runPython"], permissions=["runPython"],
            health_status="ok", **kw,
        )

    def test_hash_computed_on_init(self):
        p = self._make()
        assert len(p.hash) == 64  # sha256 hex

    def test_expires_at_set_on_init(self):
        p = self._make()
        assert p.expires_at != ""

    def test_not_expired_fresh(self):
        p = self._make()
        assert p.is_expired() is False

    def test_expired_when_past_date(self):
        past = "2000-01-01T00:00:00+00:00"
        p = self._make(expires_at=past)
        assert p.is_expired() is True

    def test_to_dict_has_all_keys(self):
        p = self._make()
        d = p.to_dict()
        for key in ("agent", "runtime", "capabilities", "permissions",
                    "health_status", "issued_at", "expires_at", "hash"):
            assert key in d

    def test_to_json_is_valid_json(self):
        import json
        p = self._make()
        parsed = json.loads(p.to_json())
        assert parsed["agent"]["name"] == "test"

    def test_from_dict_round_trip(self):
        from passport.schema import Passport
        p = self._make()
        d = p.to_dict()
        p2 = Passport.from_dict(d)
        assert p2.agent.name == p.agent.name
        assert p2.hash == p.hash
        assert p2.capabilities == p.capabilities

    def test_hash_changes_with_different_caps(self):
        from passport.schema import AgentIdentity, RuntimeInfo, Passport
        agent = AgentIdentity(name="a")
        rt = RuntimeInfo(platform="linux", is_android=False, is_termux=False,
                         has_internet=True, python_version="3.11")
        p1 = Passport(agent=agent, runtime=rt, capabilities=["runPython"],
                      permissions=[], health_status="ok")
        p2 = Passport(agent=agent, runtime=rt, capabilities=["runGit"],
                      permissions=[], health_status="ok")
        assert p1.hash != p2.hash


# ── Generator tests ───────────────────────────────────────────────────────────

class TestPassportGenerator:
    def _gen(self, **kw):
        from passport.generator import PassportGenerator
        return PassportGenerator(**kw)

    def test_issue_returns_passport(self):
        from passport.schema import AgentIdentity
        gen = self._gen()
        with (
            patch("passport.generator.PassportGenerator._available_capabilities",
                  return_value=["runPython"]),
            patch("passport.generator.PassportGenerator._check_internet",
                  return_value=False),
            patch("passport.generator.PassportGenerator._health_status",
                  return_value="ok"),
        ):
            p = gen.issue(AgentIdentity(name="ci_agent"))
        assert p.agent.name == "ci_agent"
        assert "runPython" in p.capabilities

    def test_requested_caps_subset(self):
        from passport.schema import AgentIdentity
        gen = self._gen()
        with (
            patch("passport.generator.PassportGenerator._available_capabilities",
                  return_value=["runPython", "runGit", "httpRequest"]),
            patch("passport.generator.PassportGenerator._check_internet",
                  return_value=True),
            patch("passport.generator.PassportGenerator._health_status",
                  return_value="ok"),
        ):
            p = gen.issue(AgentIdentity(name="a"), requested_capabilities=["runPython"])
        assert p.capabilities == ["runPython"]
        assert "runGit" not in p.capabilities

    def test_requested_unavailable_cap_excluded(self):
        from passport.schema import AgentIdentity
        gen = self._gen()
        with (
            patch("passport.generator.PassportGenerator._available_capabilities",
                  return_value=["runPython"]),
            patch("passport.generator.PassportGenerator._check_internet",
                  return_value=False),
            patch("passport.generator.PassportGenerator._health_status",
                  return_value="ok"),
        ):
            p = gen.issue(AgentIdentity(name="a"), requested_capabilities=["getBattery"])
        assert "getBattery" not in p.capabilities

    def test_ttl_sets_expiry(self):
        from passport.schema import AgentIdentity
        gen = self._gen(ttl=7200)
        with (
            patch("passport.generator.PassportGenerator._available_capabilities",
                  return_value=[]),
            patch("passport.generator.PassportGenerator._check_internet",
                  return_value=False),
            patch("passport.generator.PassportGenerator._health_status",
                  return_value="ok"),
        ):
            p = gen.issue(AgentIdentity(name="a"))
        exp = datetime.fromisoformat(p.expires_at)
        now = datetime.now(timezone.utc)
        diff = (exp - now).total_seconds()
        assert 7100 < diff <= 7200


# ── Validator tests ───────────────────────────────────────────────────────────

class TestPassportValidator:
    def _passport(self, expired=False, bad_hash=False):
        from passport.schema import AgentIdentity, RuntimeInfo, Passport
        past = "2000-01-01T00:00:00+00:00"
        agent = AgentIdentity(name="v_agent")
        rt = RuntimeInfo(platform="linux", is_android=False, is_termux=False,
                         has_internet=True, python_version="3.11")
        p = Passport(agent=agent, runtime=rt,
                     capabilities=["runPython"], permissions=["runPython"],
                     health_status="ok")
        if expired:
            p.expires_at = past
        if bad_hash:
            p.hash = "deadbeef" * 8
        return p

    def test_valid_passport(self):
        from passport.validator import PassportValidator
        v = PassportValidator()
        result = v.validate(self._passport())
        assert result.valid is True
        assert bool(result) is True

    def test_expired_fails(self):
        from passport.validator import PassportValidator
        v = PassportValidator()
        result = v.validate(self._passport(expired=True))
        assert result.valid is False
        assert "expired" in result.reason

    def test_bad_hash_fails(self):
        from passport.validator import PassportValidator
        v = PassportValidator()
        result = v.validate(self._passport(bad_hash=True))
        assert result.valid is False
        assert "hash" in result.reason

    def test_require_capability_granted(self):
        from passport.validator import PassportValidator
        v = PassportValidator()
        result = v.require_capability(self._passport(), "runPython")
        assert result.valid is True

    def test_require_capability_not_granted(self):
        from passport.validator import PassportValidator
        v = PassportValidator()
        result = v.require_capability(self._passport(), "getBattery")
        assert result.valid is False
        assert "getBattery" in result.reason

    def test_require_permission_granted(self):
        from passport.validator import PassportValidator
        v = PassportValidator()
        result = v.require_permission(self._passport(), "runPython")
        assert result.valid is True

    def test_require_permission_not_granted(self):
        from passport.validator import PassportValidator
        v = PassportValidator()
        result = v.require_permission(self._passport(), "sendSMS")
        assert result.valid is False

    def test_validation_result_bool(self):
        from passport.validator import ValidationResult
        assert bool(ValidationResult(valid=True)) is True
        assert bool(ValidationResult(valid=False)) is False
