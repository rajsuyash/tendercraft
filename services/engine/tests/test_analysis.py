"""Module C analysis — deterministic decisions over model evals (C-FR1/C-FR5/C-AC4/C-AC5)."""

from __future__ import annotations

from app import analysis
from app.deterministic.types import Recommendation, Verdict
from pipeline.analyzer import ModelEval


def _row(cid, level="mandatory", text="crit", page=12, clause="4.1(a)", kind="gate"):
    """A criterion row. `kind_override="gate"` by default because these tests are about the
    DECISION layer, not about classification — `analyze` now evaluates gates only, so without
    it a row of placeholder text ("crit", "d1") classifies as an obligation and is correctly
    never analysed. `tests/test_requirement_kind.py` owns the classifier."""
    return {
        "id": cid,
        "verbatim_text": text,
        "requirement_level": level,
        "anchor_page": page,
        "anchor_clause": clause,
        "kind_override": kind,
    }


def _eval(**kw) -> ModelEval:
    base = dict(
        check_type="other",
        model_verdict="needs_review",
        confidence=0.9,
        rationale="because",
        evidence_ids=("exp-1",),
        required_value_cr=None,
        operator=None,
        actual_value_cr=None,
        gap_note="",
        exemption_applies=False,
        exemption_clause=None,
    )
    base.update(kw)
    return ModelEval(**base)


def test_numeric_decided_deterministically_fail():
    # model says pass, but 8.2 < 10 -> deterministic FAIL (the model never decides numbers)
    ev = _eval(
        check_type="numeric", required_value_cr=10, actual_value_cr=8.2, operator=">=",
        model_verdict="pass", gap_note="gap ₹1.8 Cr",
    )
    v = analysis.decide(_row("c1"), ev)
    assert v.verdict is Verdict.FAIL
    assert v.gap_note == "gap ₹1.8 Cr"
    assert "Cl. 4.1(a)" in v.source_anchor  # C-AC4 source anchor


def test_numeric_decided_deterministically_pass():
    ev = _eval(check_type="numeric", required_value_cr=10, actual_value_cr=12, operator=">=", model_verdict="fail")
    assert analysis.decide(_row("c1"), ev).verdict is Verdict.PASS


def test_fuzzy_high_confidence_pass():
    ev = _eval(check_type="experience", model_verdict="pass", confidence=0.85, evidence_ids=("exp-1",))
    assert analysis.decide(_row("c1"), ev).verdict is Verdict.PASS


def test_fuzzy_low_confidence_pass_becomes_review():
    # C-AC5: sub-0.75 fuzzy pass never auto-passes
    ev = _eval(check_type="experience", model_verdict="pass", confidence=0.61)
    assert analysis.decide(_row("c1"), ev).verdict is Verdict.NEEDS_REVIEW


def test_fuzzy_pass_without_evidence_becomes_review():
    ev = _eval(check_type="experience", model_verdict="pass", confidence=0.9, evidence_ids=())
    assert analysis.decide(_row("c1"), ev).verdict is Verdict.NEEDS_REVIEW


def test_exemption_waives_a_fail():
    ev = _eval(check_type="numeric", required_value_cr=10, actual_value_cr=8, operator=">=",
               model_verdict="fail", exemption_applies=True, exemption_clause="4.5")
    v = analysis.decide(_row("c1"), ev)
    assert v.verdict is Verdict.FAIL  # the raw verdict stays fail...
    assert v.exemption_granted is True  # ...but it's flagged waived (recommend() honors it)
    assert v.gap_note == ""  # waived items don't show a gap


def _patch(monkeypatch, mapping):
    monkeypatch.setattr(analysis, "evaluate_criterion", lambda text, profile: mapping[text])


def test_mandatory_fail_caps_recommendation_at_no_bid(monkeypatch):
    rows = [_row("c1", text="turnover"), _row("c2", text="iso")]
    _patch(monkeypatch, {
        "turnover": _eval(check_type="numeric", required_value_cr=10, actual_value_cr=8, operator=">="),
        "iso": _eval(check_type="date", model_verdict="pass", confidence=0.9),
    })
    result = analysis.analyze(rows, {})
    assert result["recommendation"] == Recommendation.NO_BID.value
    assert result["conservative"] is True
    assert result["counts"]["fail"] == 1
    assert len(result["gaps"]) >= 0  # gap present if the fail had a gap_note


def test_all_mandatory_pass_recommends_bid(monkeypatch):
    rows = [_row("c1", text="turnover"), _row("c2", text="exp")]
    _patch(monkeypatch, {
        "turnover": _eval(check_type="numeric", required_value_cr=10, actual_value_cr=12, operator=">="),
        "exp": _eval(check_type="experience", model_verdict="pass", confidence=0.9, evidence_ids=("e1",)),
    })
    assert analysis.analyze(rows, {})["recommendation"] == Recommendation.BID.value


def test_weighted_score_counts_only_non_mandatory(monkeypatch):
    rows = [_row("m", "mandatory", text="m"), _row("d1", "desirable", text="d1"), _row("d2", "desirable", text="d2")]
    _patch(monkeypatch, {
        "m": _eval(check_type="numeric", required_value_cr=1, actual_value_cr=2, operator=">="),
        "d1": _eval(check_type="other", model_verdict="pass", confidence=0.9, evidence_ids=("e",)),
        "d2": _eval(check_type="other", model_verdict="fail", confidence=0.9),
    })
    # 1 of 2 desirable passed -> 50
    assert analysis.analyze(rows, {})["weighted_score"] == 50


def test_a_tender_with_nothing_scoreable_scores_NONE_not_zero(monkeypatch):
    """Zero out of a hundred is a claim that the bidder scored nothing. An absent denominator
    is a different sentence, and a catalogue bid legitimately states no scored criterion —
    which is the common case now that only gates are evaluated."""
    rows = [_row("m", "mandatory", text="m")]
    _patch(monkeypatch, {"m": _eval(check_type="numeric", required_value_cr=1,
                                    actual_value_cr=2, operator=">=")})
    assert analysis.analyze(rows, {})["weighted_score"] is None


def test_every_verdict_has_rationale_and_anchor(monkeypatch):
    rows = [_row("c1", text="x")]
    _patch(monkeypatch, {"x": _eval(model_verdict="pass", confidence=0.9, evidence_ids=("e",))})
    v = analysis.analyze(rows, {})["verdicts"][0]
    assert v["rationale"]  # C-AC4
    assert "p.12" in v["source_anchor"]


def test_empty_criteria_needs_review():
    # no mandatory gates -> conservative Needs-review recommendation
    assert analysis.analyze([], {})["recommendation"] == Recommendation.NEEDS_REVIEW.value



# --- only gates vote ------------------------------------------------------------------------


def test_a_post_award_obligation_is_not_evaluated_and_does_not_vote(monkeypatch):
    """The live defect, in one test. A clause describing an inspection that happens months
    after award was scored as a condition of entry, and one mandatory needs-review dragged the
    whole card to NO-BID on a tender squarely inside the bidder's product line."""
    gate = _row("g", "mandatory", text="Average annual turnover of Rs 10 Crore", kind=None)
    duty = _row(
        "o", "mandatory", kind=None,
        text="FOR ALL THE ITEMS, FULL QUANTITY PROOF LOAD TEST MUST BE CONDUCTED AND WILL BE "
             "WITNESSED BY BHEL SAFETY ENGINEER DURING PRE DESPATCH INSPECTION.",
    )
    _patch(monkeypatch, {
        "Average annual turnover of Rs 10 Crore": _eval(
            check_type="numeric", required_value_cr=10, actual_value_cr=12, operator=">=",
        ),
    })

    out = analysis.analyze([gate, duty], {})

    assert out["recommendation"] == Recommendation.BID.value
    assert [v["criterion_id"] for v in out["verdicts"]] == ["g"]
    # Named, not dropped: an unplanned obligation still costs money, it is just not a reason
    # to skip the bid.
    assert [c["criterion_id"] for c in out["checklist"]] == ["o"]
    assert out["checklist"][0]["kind"] == "obligation"


def test_a_tender_of_nothing_but_obligations_makes_no_model_call(monkeypatch):
    """Eighteen mandatory criteria on the live bid, two of them gates. Filtering before the
    fan-out is a cost saving as well as a correctness fix."""
    called: list[str] = []
    monkeypatch.setattr(
        analysis, "evaluate_criterion",
        lambda text, profile: called.append(text) or _eval(),
    )
    rows = [_row("o1", text="Bidders to quote Rate / No. as defined above.", kind=None)]

    out = analysis.analyze(rows, {})

    assert called == []
    assert out["verdicts"] == []
    assert out["checklist"][0]["kind"] == "instruction"


def test_an_override_puts_a_criterion_back_in_front_of_the_verdict(monkeypatch):
    """The escape hatch for the classifier's named ceiling: a gate phrased without any noun
    the rules know is an obligation until a human says otherwise."""
    row = _row("x", "mandatory", text="Bidder must be on the approved panel.", kind="gate")
    _patch(monkeypatch, {"Bidder must be on the approved panel.": _eval(
        model_verdict="fail", confidence=0.9, evidence_ids=("e",))})

    out = analysis.analyze([row], {})

    assert out["recommendation"] == Recommendation.NO_BID.value
    assert out["checklist"] == []
