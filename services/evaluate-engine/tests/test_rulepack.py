"""Regulatory checks on a draft tender (F23).

The rules themselves are data and a procurement-legal reviewer still has to confirm their
citations. What these tests pin is the ENGINE's behaviour, and one property above all:
**nothing is ever reported as satisfied that was not actually checked.** A draft that acquires
a clean bill of health it never earned is worse than no checking at all, because the officer
stops looking.
"""

import json

import pytest

from evaluate.deterministic.rulepack import (
    RulepackError,
    blocking_findings,
    check_draft,
    load_rulepack,
)

PACK_PATH = "rulepacks/gfr-2017-manuals-2022.v1.json"


@pytest.fixture(scope="module")
def pack():
    return load_rulepack(PACK_PATH)


def _crit(text, **kw):
    return {"id": kw.get("id", "c1"), "text": text, "kind": kw.get("kind", "pq"),
            "max_marks": kw.get("max_marks", 0),
            "compare_field": kw.get("compare_field"),
            "compare_value": kw.get("compare_value"),
            "evaluation_method": kw.get("evaluation_method", "")}


def _findings(pack, draft, criteria, rule_id):
    return [f for f in check_draft(pack, draft, criteria) if f.rule_id == rule_id]


# ── loading ────────────────────────────────────────────────────────────────────
def test_the_shipped_rulepack_loads_and_declares_rules(pack):
    assert pack["version"].startswith("gfr-2017")
    assert len(pack["rules"]) >= 10


def test_a_missing_rulepack_fails_loudly_rather_than_running_with_no_rules():
    """F23-ERR1. A silently rule-less draft workspace looks like it is checking and is not."""
    with pytest.raises(RulepackError, match="not found"):
        load_rulepack("rulepacks/does-not-exist.json")


def test_a_malformed_rulepack_fails_loudly(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    with pytest.raises(RulepackError, match="not valid JSON"):
        load_rulepack(bad)


def test_a_rulepack_with_no_rules_is_refused(tmp_path):
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"version": "x", "rules": []}))
    with pytest.raises(RulepackError, match="no rules"):
        load_rulepack(empty)


# ── R1: the turnover ceiling — the headline check ──────────────────────────────
def test_r1_flags_a_turnover_bar_above_twice_the_estimated_value(pack):
    draft = {"category": "goods", "estimated_annual_value": 120000000}
    crits = [_crit("Average annual turnover of at least Rs 40 Crore",
                   compare_field="annual_turnover", compare_value=400000000)]
    got = _findings(pack, draft, crits, "R1")
    assert len(got) == 1
    assert got[0].state == "open" and got[0].severity == "blocking"
    # The finding must name what would satisfy it, or it is not actionable.
    assert "24,00,00,000" in got[0].expected


def test_r1_accepts_a_proportionate_turnover_bar(pack):
    draft = {"category": "goods", "estimated_annual_value": 120000000}
    crits = [_crit("Average annual turnover of at least Rs 20 Crore",
                   compare_field="annual_turnover", compare_value=200000000)]
    assert _findings(pack, draft, crits, "R1") == []


def test_r1_cannot_evaluate_without_the_estimated_value_and_says_so(pack):
    """F23-ERR2. Reporting 'fine' here would be a lie about the one thing the rule catches."""
    crits = [_crit("turnover", compare_field="annual_turnover", compare_value=400000000)]
    got = _findings(pack, {"category": "goods"}, crits, "R1")
    assert got and got[0].state == "not_evaluated"
    assert "estimated annual value" in got[0].reason


# ── R2 / R3: window and envelope structure ─────────────────────────────────────
def test_r2_flags_a_short_submission_window(pack):
    got = _findings(pack, {"category": "goods", "submission_window_days": 10}, [], "R2")
    assert got and got[0].state == "open"


def test_r2_accepts_an_adequate_window(pack):
    assert _findings(pack, {"category": "goods", "submission_window_days": 28}, [], "R2") == []


def test_r3_flags_a_single_envelope_above_the_threshold(pack):
    draft = {"category": "goods", "estimated_value": 50000000, "bid_structure": "single"}
    got = _findings(pack, draft, [], "R3")
    assert got and got[0].state == "open"


def test_r3_accepts_two_envelope(pack):
    draft = {"category": "goods", "estimated_value": 50000000, "bid_structure": "two_envelope"}
    assert _findings(pack, draft, [], "R3") == []


# ── R4: brand names ────────────────────────────────────────────────────────────
def test_r4_flags_a_brand_name_with_no_or_equivalent(pack):
    crits = [_crit("Core switches shall be Cisco Catalyst 9300", kind="technical")]
    got = _findings(pack, {"category": "goods"}, crits, "R4")
    assert got and "Cisco" in got[0].observed


def test_r4_accepts_a_brand_name_qualified_with_or_equivalent(pack):
    crits = [_crit("Core switches shall be Cisco Catalyst 9300 or equivalent", kind="technical")]
    assert _findings(pack, {"category": "goods"}, crits, "R4") == []


def test_r4_ignores_a_generic_specification(pack):
    crits = [_crit("Core switches shall support 48 ports at 10G", kind="technical")]
    assert _findings(pack, {"category": "goods"}, crits, "R4") == []


# ── R8: framework arithmetic ───────────────────────────────────────────────────
def test_r8_flags_technical_marks_that_do_not_total_100(pack):
    draft = {"category": "goods", "qualifying_marks": 60, "technical_weight": 70}
    crits = [_crit("a", kind="technical", max_marks=40, id="t1"),
             _crit("b", kind="technical", max_marks=40, id="t2")]
    got = _findings(pack, draft, crits, "R8")
    assert any("80" in (f.observed or "") for f in got)


def test_r8_flags_a_missing_qualifying_mark(pack):
    draft = {"category": "goods", "technical_weight": 70}
    crits = [_crit("a", kind="technical", max_marks=100, id="t1")]
    got = _findings(pack, draft, crits, "R8")
    assert any("qualifying marks" in (f.observed or "") for f in got)


def test_r8_flags_a_qcbs_weight_outside_the_permitted_band(pack):
    draft = {"category": "goods", "qualifying_marks": 60, "technical_weight": 95}
    crits = [_crit("a", kind="technical", max_marks=100, id="t1")]
    got = _findings(pack, draft, crits, "R8")
    assert any("95" in (f.observed or "") for f in got)


# ── R9: every criterion states how it is marked ────────────────────────────────
def test_r9_flags_a_technical_criterion_with_no_evaluation_method(pack):
    crits = [_crit("Solution architecture", kind="technical", max_marks=20, id="t1")]
    got = _findings(pack, {"category": "goods"}, crits, "R9")
    assert got and got[0].target_id == "t1"


def test_r9_accepts_a_criterion_that_states_its_method(pack):
    crits = [_crit("Solution architecture", kind="technical", max_marks=20, id="t1",
                   evaluation_method="0-20 by panel against the stated sub-criteria")]
    assert _findings(pack, {"category": "goods"}, crits, "R9") == []


# ── the property that matters most ─────────────────────────────────────────────
def test_an_unimplemented_check_kind_is_reported_not_silently_passed():
    """A rulepack that gains a rule this build cannot run must make that visible."""
    pack = {"version": "t", "rules": [{
        "id": "RX", "title": "future rule", "severity": "blocking",
        "citation": "somewhere", "check": {"kind": "telepathy"}}]}
    got = check_draft(pack, {"category": "goods"}, [])
    assert len(got) == 1
    assert got[0].state == "not_evaluated"
    assert "not implemented" in got[0].reason


def test_not_evaluated_never_blocks_publication():
    """It is a gap in our checking, not a defect in the draft. Blocking on it would make a
    missing field unfixable — the officer could never publish and never know why."""
    pack = {"version": "t", "rules": [{
        "id": "RX", "title": "future rule", "severity": "blocking",
        "citation": "x", "check": {"kind": "telepathy"}}]}
    findings = check_draft(pack, {"category": "goods"}, [])
    assert blocking_findings(findings) == ()


def test_blocking_findings_selects_only_open_blocking_ones(pack):
    draft = {"category": "goods", "estimated_annual_value": 120000000,
             "submission_window_days": 5}
    crits = [_crit("turnover", compare_field="annual_turnover", compare_value=400000000)]
    blocking = blocking_findings(check_draft(pack, draft, crits))
    assert {f.rule_id for f in blocking} >= {"R1", "R2"}
    assert all(f.severity == "blocking" and f.state == "open" for f in blocking)


def test_rules_are_filtered_by_category(pack):
    """A works-only rule must not fire on a goods tender."""
    goods = {f.rule_id for f in check_draft(pack, {"category": "goods"}, [])}
    works = {f.rule_id for f in check_draft(pack, {"category": "works"}, [])}
    assert "R5" in works and "R5" not in goods


# ── R6: EMD band and the exemption clause ──────────────────────────────────────
def test_r6_flags_an_emd_above_the_permitted_band(pack):
    draft = {"category": "goods", "estimated_value": 10000000, "emd_amount": 900000,
             "emd_exemption_stated": True}
    got = _findings(pack, draft, [], "R6")
    assert got and "9.00%" in got[0].observed


def test_r6_flags_a_missing_mse_exemption_clause(pack):
    """The clause whose absence only ever surfaces as a complaint from a small bidder."""
    draft = {"category": "goods", "estimated_value": 10000000, "emd_amount": 200000,
             "emd_exemption_stated": False}
    got = _findings(pack, draft, [], "R6")
    assert got and "exemption" in got[0].observed


def test_r6_accepts_an_emd_in_band_with_the_exemption_stated(pack):
    draft = {"category": "goods", "estimated_value": 10000000, "emd_amount": 200000,
             "emd_exemption_stated": True}
    assert _findings(pack, draft, [], "R6") == []


def test_r6_cannot_evaluate_without_the_figures(pack):
    got = _findings(pack, {"category": "goods"}, [], "R6")
    assert got and got[0].state == "not_evaluated"


def test_r6_treats_a_zero_estimated_value_as_unevaluable_rather_than_dividing_by_it(pack):
    draft = {"category": "goods", "estimated_value": 0, "emd_amount": 200000}
    got = _findings(pack, draft, [], "R6")
    assert got and got[0].state == "not_evaluated"


# ── R7: pre-bid meeting margin (advisory) ──────────────────────────────────────
def test_r7_flags_no_pre_bid_meeting_on_a_works_tender(pack):
    got = _findings(pack, {"category": "works"}, [], "R7")
    assert got and "no pre-bid meeting" in got[0].observed
    assert got[0].severity == "advisory"


def test_r7_flags_a_meeting_too_close_to_the_deadline(pack):
    """A meeting held too late cannot change the document — which is the point of holding it."""
    draft = {"category": "works", "pre_bid_meeting_at": "2026-09-01",
             "pre_bid_days_before_deadline": 2}
    got = _findings(pack, draft, [], "R7")
    assert got and "2 days" in got[0].observed


def test_r7_accepts_a_meeting_with_adequate_margin(pack):
    draft = {"category": "works", "pre_bid_meeting_at": "2026-09-01",
             "pre_bid_days_before_deadline": 14}
    assert _findings(pack, draft, [], "R7") == []


def test_r7_cannot_evaluate_a_meeting_with_no_known_date_offset(pack):
    draft = {"category": "works", "pre_bid_meeting_at": "2026-09-01"}
    got = _findings(pack, draft, [], "R7")
    assert got and got[0].state == "not_evaluated"


# ── input robustness ───────────────────────────────────────────────────────────
def test_a_non_numeric_criterion_value_is_reported_not_crashed_on(pack):
    """An extractor can and will produce 'as per Annexure III' where a number was expected."""
    draft = {"category": "goods", "estimated_annual_value": 120000000}
    crits = [_crit("turnover", compare_field="annual_turnover",
                   compare_value="as per Annexure III")]
    got = _findings(pack, draft, crits, "R1")
    assert got and got[0].state == "not_evaluated"


def test_r3_ignores_a_tender_below_the_two_envelope_threshold(pack):
    draft = {"category": "goods", "estimated_value": 0, "bid_structure": "single"}
    assert _findings(pack, draft, [], "R3") == []


def test_a_ratio_rule_ignores_criteria_about_a_different_field(pack):
    """R5 measures similar-work value; a turnover criterion is not its business. Without the
    skip, every ratio rule would fire on every numeric criterion in the tender."""
    draft = {"category": "works", "estimated_value": 10000000,
             "estimated_annual_value": 10000000}
    crits = [_crit("Average annual turnover of at least Rs 4 Crore",
                   compare_field="annual_turnover", compare_value=40000000)]
    assert _findings(pack, draft, crits, "R5") == []
    assert _findings(pack, draft, crits, "R1")          # R1 does own that field


def test_indian_grouping_in_findings_across_magnitudes(pack):
    """A finding that misformats the number the officer typed reads as a different number."""
    for value, expected in [(240000000, "24,00,00,000"), (1200000, "12,00,000"),
                            (100000, "1,00,000"), (999, "999")]:
        draft = {"category": "goods", "estimated_annual_value": value / 2}
        crits = [_crit("turnover", compare_field="annual_turnover",
                       compare_value=value * 10)]
        got = _findings(pack, draft, crits, "R1")
        assert expected in got[0].expected, f"{value} rendered wrong"


# ── R4 also reads the scope, not only the criteria ─────────────────────────────
def test_r4_flags_a_brand_named_in_the_scope(pack):
    """The rule read criteria only, so a brand-locked line in the tender's scope — the box an
    officer actually writes a specification into — produced no finding. Found while seeding a
    demo draft whose scope said "Core switches shall be Cisco Catalyst 9300" and watching R4
    stay silent."""
    draft = {"category": "goods",
             "scope": "Core switches shall be Cisco Catalyst 9300 series."}
    got = _findings(pack, draft, [], "R4")
    assert len(got) == 1
    assert "cisco" in got[0].observed.lower()
    assert got[0].target_kind == "draft"


def test_r4_accepts_a_scope_that_says_or_equivalent(pack):
    draft = {"category": "goods",
             "scope": "Core switches shall be Cisco Catalyst 9300 series or equivalent."}
    assert _findings(pack, draft, [], "R4") == []


def test_r4_reports_the_scope_and_a_criterion_separately(pack):
    """Two clauses, two findings: fixing one must not silence the other."""
    draft = {"category": "goods", "scope": "Firewalls shall be Fortinet FortiGate."}
    crits = [{"id": "c1", "text": "Access points shall be Cisco Meraki", "kind": "technical"}]
    got = _findings(pack, draft, crits, "R4")
    assert len(got) == 2
    assert {f.target_kind for f in got} == {"draft", "criterion"}


def test_r4_is_silent_on_a_scope_with_no_brand(pack):
    draft = {"category": "goods", "scope": "Core switches shall support 48 ports at 1 Gbps."}
    assert _findings(pack, draft, [], "R4") == []
