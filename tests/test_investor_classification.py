"""Tests for config/investor_classification.py -- the pure CVM Resolução
30/2021 classification function (suggest_investor_category). Storage-level
persistence (set_investor_classification, including the attestation
timestamp) is covered in tests/test_client_repo.py; the HTTP endpoints in
tests/test_client_outreach_api.py-style API tests live in
tests/test_dashboard_routes.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.investor_classification import (  # noqa: E402
    ACCEPTED_CERTIFICATIONS,
    PROFESSIONAL_INVESTOR_THRESHOLD,
    QUALIFIED_INVESTOR_THRESHOLD,
    suggest_investor_category,
)


class TestSuggestInvestorCategory:
    def test_no_investments_and_no_certification_is_geral(self):
        assert suggest_investor_category(None, None) == "geral"

    def test_below_qualified_threshold_is_geral(self):
        assert suggest_investor_category(QUALIFIED_INVESTOR_THRESHOLD - 1, None) == "geral"

    def test_at_qualified_threshold_is_qualificado(self):
        assert suggest_investor_category(QUALIFIED_INVESTOR_THRESHOLD, None) == "qualificado"

    def test_between_thresholds_is_qualificado(self):
        assert suggest_investor_category(5_000_000.0, None) == "qualificado"

    def test_at_professional_threshold_is_profissional(self):
        assert suggest_investor_category(PROFESSIONAL_INVESTOR_THRESHOLD, None) == "profissional"

    def test_above_professional_threshold_is_profissional(self):
        assert suggest_investor_category(50_000_000.0, None) == "profissional"

    def test_valid_certification_alone_grants_qualificado_regardless_of_wealth(self):
        cert = ACCEPTED_CERTIFICATIONS[0]
        assert suggest_investor_category(None, cert) == "qualificado"
        assert suggest_investor_category(0.0, cert) == "qualificado"

    def test_certification_lookup_is_case_and_whitespace_insensitive(self):
        cert = ACCEPTED_CERTIFICATIONS[0]
        assert suggest_investor_category(None, f"  {cert.lower()}  ") == "qualificado"

    def test_unknown_certification_string_falls_back_to_wealth_only(self):
        assert suggest_investor_category(None, "NOT_A_REAL_CERTIFICATION") == "geral"
        assert suggest_investor_category(5_000_000.0, "NOT_A_REAL_CERTIFICATION") == "qualificado"

    def test_certification_never_upgrades_to_profissional_on_its_own(self):
        # Art. 12, III only reaches "qualificado" -- a certification with
        # no wealth declared must never resolve to "profissional".
        cert = ACCEPTED_CERTIFICATIONS[0]
        assert suggest_investor_category(None, cert) == "qualificado"

    def test_professional_wealth_wins_even_with_a_certification_present(self):
        cert = ACCEPTED_CERTIFICATIONS[0]
        assert suggest_investor_category(PROFESSIONAL_INVESTOR_THRESHOLD, cert) == "profissional"

    def test_every_accepted_certification_is_uppercase_in_the_catalog(self):
        # suggest_investor_category() normalizes the *input* to uppercase
        # before comparing -- this just guards against silently adding a
        # lowercase entry to the catalog that a case-insensitive lookup
        # would then never match.
        for cert in ACCEPTED_CERTIFICATIONS:
            assert cert == cert.upper()
