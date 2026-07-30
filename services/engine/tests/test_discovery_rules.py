"""F-AC6 — nothing leaves the primary feed except by a named, user-authored rule.

Required to exist by tools/check-discovery-guardrails.sh, following the sealed-bid precedent: a
green suite that never exercised the catastrophic gate is worse than a red one. The gate here is
ET-7, the discovery miss — the only failure in this product with no natural feedback signal.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.deterministic.discovery import (
    RULE_KINDS,
    EligibilityResult,
    Rule,
    evaluate_eligibility,
    evaluate_gate,
)

NOW = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)


def record(**overrides):
    base = {
        "portal_ref_no": "GEM/2026/R/706528",
        "title": "Stationary Valve Regulated Lead Acid Batteries",
        "authority": "Ministry of Defence · Department of Military Affairs",
        "category_codes": ["home_powe_batt_batt_st87064165"],
        "closing_at": (NOW + timedelta(days=30)).isoformat(),
        "estimated_value": None,
        "geography": None,
    }
    return base | overrides


class TestNothingIsHiddenWithoutANamedRule:
    def test_no_rules_means_everything_is_in_scope(self):
        result = evaluate_gate(record(), [], now=NOW)
        assert result.in_scope is True
        assert result.excluded_by_rule is None

    def test_an_exclusion_always_names_its_rule(self):
        rule = Rule(name="Defence only", kind="authority_not_contains",
                    spec={"needles": ["Ministry of Railways"]})
        result = evaluate_gate(record(), [rule], now=NOW)
        assert result.in_scope is False
        assert result.excluded_by_rule == "Defence only"

    def test_a_disabled_rule_cannot_exclude(self):
        rule = Rule(name="off", kind="category_prefix_not_in",
                    spec={"prefixes": ["nothing_matches_"]}, enabled=False)
        assert evaluate_gate(record(), [rule], now=NOW).in_scope is True

    def test_an_unknown_rule_kind_is_inert_rather_than_excluding(self):
        # A rule kind this build does not understand — e.g. written by a newer UI — must not
        # remove tenders from someone's world on the way to being ignored.
        rule = Rule(name="from the future", kind="semantic_similarity", spec={"q": "batteries"})
        assert evaluate_gate(record(), [rule], now=NOW).in_scope is True

    def test_a_malformed_spec_is_inert(self):
        for kind in sorted(RULE_KINDS):
            rule = Rule(name=f"empty {kind}", kind=kind, spec={})
            assert evaluate_gate(record(), [rule], now=NOW).in_scope is True, kind

    def test_the_first_firing_rule_is_the_one_reported(self):
        rules = [
            Rule(name="A", kind="authority_contains", spec={"needles": ["Defence"]}),
            Rule(name="B", kind="authority_contains", spec={"needles": ["Ministry"]}),
        ]
        assert evaluate_gate(record(), rules, now=NOW).excluded_by_rule == "A"


class TestMissingDataNeverCausesAnExclusion:
    """Absence must stay absence. Every one of these would be a tender hidden by a rule the user
    did not write, which is F-AC6's definition of a breach."""

    def test_no_closing_date_is_not_treated_as_closing_today(self):
        rule = Rule(name="7+ days", kind="min_days_to_close", spec={"days": 7})
        assert evaluate_gate(record(closing_at=None), [rule], now=NOW).in_scope is True

    def test_an_unparseable_closing_date_does_not_exclude(self):
        rule = Rule(name="7+ days", kind="min_days_to_close", spec={"days": 7})
        assert evaluate_gate(record(closing_at="not a date"), [rule], now=NOW).in_scope is True

    def test_an_absent_estimated_value_does_not_exclude(self):
        # GeM omits estimated value on most listings — it is in the document, not the feed. A
        # value rule that excluded on absence would hide most of the feed.
        rule = Rule(name="₹1L+", kind="value_between", spec={"min": 100_000})
        assert evaluate_gate(record(estimated_value=None), [rule], now=NOW).in_scope is True

    def test_an_empty_authority_does_not_match_a_contains_rule(self):
        rule = Rule(name="defence", kind="authority_contains", spec={"needles": ["Defence"]})
        assert evaluate_gate(record(authority=None), [rule], now=NOW).in_scope is True


class TestRulesThatShouldFire:
    def test_min_days_to_close_excludes_a_deadline_that_is_too_soon(self):
        rule = Rule(name="7+ days", kind="min_days_to_close", spec={"days": 7})
        soon = record(closing_at=(NOW + timedelta(days=2)).isoformat())
        assert evaluate_gate(soon, [rule], now=NOW).excluded_by_rule == "7+ days"

    def test_category_prefix_not_in_keeps_only_wanted_categories(self):
        rule = Rule(name="Services only", kind="category_prefix_not_in",
                    spec={"prefixes": ["services_"]})
        assert evaluate_gate(record(), [rule], now=NOW).in_scope is False
        services = record(category_codes=["services_home_cust"])
        assert evaluate_gate(services, [rule], now=NOW).in_scope is True

    def test_value_between_bounds(self):
        rule = Rule(name="₹1L–₹1Cr", kind="value_between",
                    spec={"min": 100_000, "max": 10_000_000})
        assert evaluate_gate(record(estimated_value=50_000), [rule], now=NOW).in_scope is False
        assert evaluate_gate(record(estimated_value=5_000_000), [rule], now=NOW).in_scope is True
        assert evaluate_gate(record(estimated_value=20_000_000), [rule], now=NOW).in_scope is False


class TestDepth1Eligibility:
    """C-AC8: a fuzzy or unknown criterion is never auto-passed at Depth 1."""

    def test_no_document_read_yet_is_unknown(self):
        assert evaluate_eligibility(None, {"avg_annual_turnover_inr": 82_000_000}).signal == "unknown"

    def test_no_turnover_requirement_is_unknown_not_eligible(self):
        result = evaluate_eligibility({"min_avg_annual_turnover_inr": None},
                                      {"avg_annual_turnover_inr": 82_000_000})
        assert result.signal == "unknown"

    def test_no_profile_turnover_is_unknown_not_ineligible(self):
        result = evaluate_eligibility({"min_avg_annual_turnover_inr": 500_000}, {})
        assert result.signal == "unknown"
        assert "no turnover on record" in result.reason

    def test_meeting_the_threshold_is_likely_eligible(self):
        result = evaluate_eligibility({"min_avg_annual_turnover_inr": 500_000},
                                      {"avg_annual_turnover_inr": 82_000_000})
        assert result.signal == "likely_eligible"

    def test_missing_the_threshold_is_likely_ineligible(self):
        result = evaluate_eligibility({"min_avg_annual_turnover_inr": 2_500_000_000},
                                      {"avg_annual_turnover_inr": 82_000_000})
        assert result.signal == "likely_ineligible"

    def test_an_mse_relaxation_is_surfaced_rather_than_silently_ignored(self):
        # A bidder who skips a tender they were actually relaxed into has lost it to a UI detail.
        result = evaluate_eligibility(
            {"min_avg_annual_turnover_inr": 2_500_000_000,
             "mse_turnover_relaxation": "Yes | Partial"},
            {"avg_annual_turnover_inr": 82_000_000},
        )
        assert result.signal == "likely_ineligible"
        assert "MSE turnover relaxation" in result.reason

    @pytest.mark.parametrize(
        ("fields", "profile"),
        [
            (None, None),
            ({}, {}),
            ({"min_avg_annual_turnover_inr": 500_000}, None),
        ],
    )
    def test_every_verdict_carries_a_reason(self, fields, profile):
        # C-AC9: a Depth-1 verdict with no deciding criterion is unexplainable and unactionable.
        result = evaluate_eligibility(fields, profile)
        assert isinstance(result, EligibilityResult)
        assert result.reason.strip()

    def test_eligibility_never_returns_an_exclusion(self):
        # Depth-1 ranks; it does not hide (C-FR9 / F-FR12). The signal vocabulary has no
        # 'excluded' member at all, and this pins that.
        for fields in ({"min_avg_annual_turnover_inr": 10**12}, {}, None):
            assert evaluate_eligibility(fields, {"avg_annual_turnover_inr": 1}).signal in {
                "likely_eligible", "likely_ineligible", "unknown",
            }
