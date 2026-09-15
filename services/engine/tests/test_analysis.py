"""Module C analysis — the adapter layer (C-FR1/C-FR5/C-AC4/C-AC5).

These tests own the DECISION boundary: which criteria reach a verdict, what the model is
allowed to supply, and how gate verdicts roll up. The arithmetic itself belongs to
`tests/test_facts.py`, and the classifier to `tests/test_requirement_kind.py`.
"""

from __future__ import annotations

from datetime import date

from app import analysis
from app.deterministic.facts import Requirement
from app.deterministic.types import CheckType, Recommendation, Verdict

BID_DATE = date(2026, 8, 14)

#: A profile with enough on file that a turnover gate can actually be decided. FY24|FY25|FY26
#: is the window `recent_fys(2026-08-14, 3)` produces.
PROFILE = {
    "legal_identity": {"net_worth_cr": 4.0, "udyam_registration": "UDYAM-JH-01-0001"},
    "financials": [
        {"fy_label": "FY24", "turnover_cr": 6.8},
        {"fy_label": "FY25", "turnover_cr": 8.1},
        {"fy_label": "FY26", "turnover_cr": 9.7},
    ],
    "experience_records": [],
    "certifications": [],
}


def _row(cid, level="mandatory", text="crit", page=12, clause="4.1(a)", kind="gate"):
    """A criterion row. `kind_override="gate"` by default because these tests are about the
    DECISION layer, not about classification — `analyze` evaluates gates only, so without it
    a row of placeholder text ("crit", "d1") classifies as an obligation and is correctly
    never analysed. `tests/test_requirement_kind.py` owns the classifier."""
    return {
        "id": cid,
        "verbatim_text": text,
        "requirement_level": level,
        "anchor_page": page,
        "anchor_clause": clause,
        "kind_override": kind,
    }


def _req(**kw) -> Requirement:
    """What the MODEL is allowed to say. Note what cannot be passed here: no verdict, no
    actual value, no evidence ids, no exemption boolean. Those are not fields."""
    kw.setdefault("confidence", 0.9)
    return Requirement(**kw)


def _turnover(threshold: float) -> Requirement:
    return _req(check=CheckType.TURNOVER_AVG, operator=">=", threshold_cr=threshold, fy_count=3)


def _patch(monkeypatch, mapping):
    monkeypatch.setattr(analysis, "extract_requirement", lambda text: mapping[text])


# --- the model cannot report the bidder's side ------------------------------------------------


def test_the_extractor_is_called_with_the_criterion_text_and_nothing_else(monkeypatch):
    """The structural half of the fix, asserted at the call site: `analyze` has the profile
    in hand and does not hand it to the model. A model that cannot see the bidder's numbers
    cannot report them, which is worth more than any instruction in the prompt."""
    seen: list = []

    def spy(*args, **kwargs):
        seen.append((args, kwargs))
        return _turnover(5)

    monkeypatch.setattr(analysis, "extract_requirement", spy)
    analysis.analyze([_row("c1", text="Average annual turnover of Rs 5 Crore")], PROFILE,
                     BID_DATE)

    assert seen == [(("Average annual turnover of Rs 5 Crore",), {})]


# --- the verdict is arithmetic over facts -----------------------------------------------------


def test_a_shortfall_is_computed_from_the_profile_not_reported(monkeypatch):
    """₹8.20 Cr averaged across FY24|FY25|FY26 against a ₹10 Cr demand. Nothing in the
    model's answer names 8.2 — it cannot, it never saw the profile."""
    v = analysis.decide(_row("c1"), _turnover(10), analysis.profile_facts(PROFILE), BID_DATE)

    assert v.verdict is Verdict.FAIL
    assert v.actual_display == "₹8.20 Cr (avg FY24|FY25|FY26)"
    assert v.required_display == "₹10.00 Cr"
    assert v.operator == ">="
    assert "gap ₹1.80 Cr" in v.gap_note
    assert v.fy_window == ("FY24", "FY25", "FY26")
    assert "Cl. 4.1(a)" in v.source_anchor  # C-AC4 source anchor


def test_the_same_facts_against_a_lower_threshold_pass(monkeypatch):
    v = analysis.decide(_row("c1"), _turnover(8), analysis.profile_facts(PROFILE), BID_DATE)
    assert v.verdict is Verdict.PASS
    assert v.gap_note == ""


def test_a_low_confidence_reading_never_decides_a_number(monkeypatch):
    """C-AC5, and the defect it was missing: the confidence guard applied to the fuzzy branch
    only, so a numeric comparison at confidence 0.01 produced a hard PASS."""
    req = Requirement(check=CheckType.TURNOVER_AVG, operator=">=", threshold_cr=1.0,
                      fy_count=3, confidence=0.01)
    v = analysis.decide(_row("c1"), req, analysis.profile_facts(PROFILE), BID_DATE)
    assert v.verdict is Verdict.NEEDS_REVIEW


def test_an_absent_fact_is_needs_review_never_fail(monkeypatch):
    """A false "you do not qualify" costs a bid the customer would have won, and nobody
    audits the bids they were told to skip."""
    v = analysis.decide(_row("c1"), _turnover(10), analysis.profile_facts({}), BID_DATE)
    assert v.verdict is Verdict.NEEDS_REVIEW
    assert v.missing_facts  # and it names what it wants


def test_an_exemption_needs_a_clause_and_a_matching_registration(monkeypatch):
    req = _req(check=CheckType.TURNOVER_AVG, operator=">=", threshold_cr=10, fy_count=3,
               exemption_for=("mse",), exemption_clause="Cl. 4.5 — MSE relaxation")
    v = analysis.decide(_row("c1"), req, analysis.profile_facts(PROFILE), BID_DATE)

    assert v.verdict is Verdict.FAIL          # the raw verdict stays fail...
    assert v.exemption_granted is True        # ...but recommend() honours the waiver
    assert v.gap_note == ""                   # a waived item shows no gap
    assert v.exemption_clause == "Cl. 4.5 — MSE relaxation"


def test_an_exemption_the_bidder_is_not_in_is_not_granted(monkeypatch):
    """The old `exemption_applies` was a bare model boolean, so one `true` on a mandatory
    criterion turned NO-BID into BID with nothing resolved anywhere."""
    req = _req(check=CheckType.TURNOVER_AVG, operator=">=", threshold_cr=10, fy_count=3,
               exemption_for=("dpiit",), exemption_clause="Cl. 4.6 — start-up relaxation")
    v = analysis.decide(_row("c1"), req, analysis.profile_facts(PROFILE), BID_DATE)

    assert v.exemption_granted is False
    assert v.gap_note


# --- rolling up -------------------------------------------------------------------------------


def test_mandatory_fail_caps_recommendation_at_no_bid(monkeypatch):
    rows = [_row("c1", text="turnover"), _row("c2", text="networth")]
    _patch(monkeypatch, {
        "turnover": _turnover(10),
        "networth": _req(check=CheckType.NET_WORTH, operator=">=", threshold_cr=2),
    })
    result = analysis.analyze(rows, PROFILE, BID_DATE)

    assert result["recommendation"] == Recommendation.NO_BID.value
    assert result["conservative"] is True
    assert result["counts"] == {"pass": 1, "fail": 1, "needs_review": 0}
    assert result["gaps"][0]["criterion_id"] == "c1"


def test_all_mandatory_pass_recommends_bid(monkeypatch):
    rows = [_row("c1", text="turnover"), _row("c2", text="udyam")]
    _patch(monkeypatch, {
        "turnover": _turnover(8),
        "udyam": _req(check=CheckType.REGISTRATION_PRESENT, registration_key="udyam"),
    })
    assert analysis.analyze(rows, PROFILE, BID_DATE)["recommendation"] == Recommendation.BID.value


def test_weighted_score_counts_only_non_mandatory(monkeypatch):
    rows = [_row("m", "mandatory", text="m"),
            _row("d1", "desirable", text="d1"),
            _row("d2", "desirable", text="d2")]
    _patch(monkeypatch, {
        "m": _turnover(8),
        "d1": _req(check=CheckType.NET_WORTH, operator=">=", threshold_cr=2),
        "d2": _req(check=CheckType.NET_WORTH, operator=">=", threshold_cr=99),
    })
    # 1 of 2 desirable passed -> 50
    assert analysis.analyze(rows, PROFILE, BID_DATE)["weighted_score"] == 50


def test_a_tender_with_nothing_scoreable_scores_NONE_not_zero(monkeypatch):
    """Zero out of a hundred is a claim that the bidder scored nothing. An absent denominator
    is a different sentence, and a catalogue bid legitimately states no scored criterion —
    which is the common case now that only gates are evaluated."""
    _patch(monkeypatch, {"m": _turnover(8)})
    assert analysis.analyze([_row("m", text="m")], PROFILE, BID_DATE)["weighted_score"] is None


def test_every_verdict_carries_its_rationale_anchor_and_working(monkeypatch):
    _patch(monkeypatch, {"x": _turnover(10)})
    v = analysis.analyze([_row("c1", text="x")], PROFILE, BID_DATE)["verdicts"][0]

    assert v["rationale"]  # C-AC4
    assert "p.12" in v["source_anchor"]
    # The working, not just the answer — a verdict nobody can reconstruct cannot be audited.
    assert v["check"] == "turnover_avg"
    assert v["operator"] == ">="
    assert v["required_display"] == "₹10.00 Cr"
    assert v["actual_display"].startswith("₹8.20 Cr")
    assert v["fy_window"] == ["FY24", "FY25", "FY26"]


def test_a_tender_stating_no_gate_is_not_needs_review():
    """NO_GATES, not NEEDS_REVIEW. Nothing here disqualifies the bidder, and there is nothing
    for a human to go and resolve."""
    assert analysis.analyze([], {})["recommendation"] == Recommendation.NO_GATES.value


# --- the financial-year window -----------------------------------------------------------------


def test_a_named_window_beats_the_bid_date(monkeypatch):
    """The clause said which years. Use them."""
    req = _req(check=CheckType.TURNOVER_AVG, operator=">=", threshold_cr=7,
               fy_labels=("2023-24", "2024-25"))
    v = analysis.decide(_row("c1"), req, analysis.profile_facts(PROFILE), BID_DATE)
    assert v.fy_window == ("FY24", "FY25")
    assert v.actual_display == "₹7.45 Cr (avg FY24|FY25)"


def test_without_a_bid_date_a_relative_window_cannot_be_resolved(monkeypatch):
    """"The last three financial years" is relative to when the bid closes. With no deadline
    on file the honest answer is needs-review, never a window guessed from whichever years the
    BIDDER happens to have on file."""
    v = analysis.decide(_row("c1"), _turnover(10), analysis.profile_facts(PROFILE), None)
    assert v.verdict is Verdict.NEEDS_REVIEW
    assert v.fy_window == ()


# --- only gates vote ---------------------------------------------------------------------------


def test_a_post_award_obligation_is_not_evaluated_and_does_not_vote(monkeypatch):
    """The live defect, in one test. A clause describing an inspection that happens months
    after award was scored as a condition of entry, and one mandatory needs-review dragged the
    whole card to NO-BID on a tender squarely inside the bidder's product line."""
    gate = _row("g", "mandatory", text="Average annual turnover of Rs 5 Crore", kind=None)
    duty = _row(
        "o", "mandatory", kind=None,
        text="FOR ALL THE ITEMS, FULL QUANTITY PROOF LOAD TEST MUST BE CONDUCTED AND WILL BE "
             "WITNESSED BY BHEL SAFETY ENGINEER DURING PRE DESPATCH INSPECTION.",
    )
    _patch(monkeypatch, {"Average annual turnover of Rs 5 Crore": _turnover(5)})

    out = analysis.analyze([gate, duty], PROFILE, BID_DATE)

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
    monkeypatch.setattr(analysis, "extract_requirement",
                        lambda text: called.append(text) or _req())
    rows = [_row("o1", text="Bidders to quote Rate / No. as defined above.", kind=None)]

    out = analysis.analyze(rows, PROFILE, BID_DATE)

    assert called == []
    assert out["verdicts"] == []
    assert out["checklist"][0]["kind"] == "instruction"


def test_an_override_puts_a_criterion_back_in_front_of_the_verdict(monkeypatch):
    """The escape hatch for the classifier's named ceiling: a gate phrased without any noun
    the rules know is an obligation until a human says otherwise."""
    row = _row("x", "mandatory", text="Bidder must be on the approved panel.", kind="gate")
    _patch(monkeypatch, {"Bidder must be on the approved panel.": _turnover(99)})

    out = analysis.analyze([row], PROFILE, BID_DATE)

    assert out["recommendation"] == Recommendation.NO_BID.value
    assert out["checklist"] == []


# --- when the two readings disagree ------------------------------------------------------------


def test_a_gate_the_extractor_confidently_finds_nothing_to_check_in_stops_voting(monkeypatch):
    """Two independent readings. `requirement_kind` classifies from the sentence's
    vocabulary — "OEM", "manufacturer's authorisation" — and over-reached on four bidding
    rules in the live tender. The extractor read the whole clause and said there is no
    pre-bid condition in it.

    Scoring it anyway parks the card on needs-review permanently, because there is no fact a
    user could ever supply to clear it. That is a dead end wearing a verdict's clothes."""
    row = _row("r", "mandatory",
               text="such agent shall not be allowed to represent more than one manufacturer")
    _patch(monkeypatch, {row["verbatim_text"]: _req(check=CheckType.NONE, confidence=0.95)})

    out = analysis.analyze([row], PROFILE, BID_DATE)

    assert out["verdicts"] == []
    assert out["recommendation"] == Recommendation.NO_GATES.value
    assert out["checklist"][0]["criterion_id"] == "r"
    # And it says WHY it is not being scored. The screen pairs the note with the control
    # that reverses it — a sentence naming an action with no affordance is a dead end.
    assert "nothing that can be checked" in out["checklist"][0]["note"]


def test_a_model_failure_is_not_a_reading_and_keeps_its_vote(monkeypatch):
    """The confidence floor is the whole guard, and it separates two states that are
    identical in the payload and opposite in meaning: `none` at 0.95 is "I read it and there
    is nothing to check"; `none` at 0.0 is a timeout. Demoting the second would silently
    drop a real gate every time the model was unavailable."""
    row = _row("g", "mandatory", text="Average annual turnover of Rs 10 Crore")
    _patch(monkeypatch, {row["verbatim_text"]: _req(check=CheckType.NONE, confidence=0.0)})

    out = analysis.analyze([row], PROFILE, BID_DATE)

    assert out["checklist"] == []
    assert out["verdicts"][0]["verdict"] == Verdict.NEEDS_REVIEW.value
    assert out["recommendation"] == Recommendation.NEEDS_REVIEW.value


def test_a_checklist_item_that_was_never_a_gate_carries_no_note(monkeypatch):
    """The note explains a demotion. An ordinary obligation was never claimed to be a gate,
    so there is nothing to explain and an empty string is the honest value."""
    row = _row("o", "mandatory", kind=None,
               text="The warranty period shall be 24 months from the date of delivery.")
    out = analysis.analyze([row], PROFILE, BID_DATE)
    assert out["checklist"][0]["note"] == ""


# --- the reading is stored, so the verdict is reproducible ---------------------------------------


def _cached_row(cid, req: Requirement, text="Average annual turnover of Rs 10 Crore"):
    from pipeline.analyzer import requirement_hash, to_json
    row = _row(cid, text=text)
    row["requirement"] = to_json(req)
    row["requirement_hash"] = requirement_hash(text)
    return row


def test_a_stored_reading_is_used_and_the_model_is_not_asked_again(monkeypatch):
    """The card used to move between identical runs, because whether a clause IS a gate
    depends on a model reading and that reading is stochastic. Measured on the live bid: one
    OEM-authorisation clause came back `none` at 0.90 four times in six and
    `certification_valid` at 1.00 twice — confidently on both sides, so no threshold could
    separate them. A compliance product may not answer the same question two ways."""
    called: list[str] = []
    monkeypatch.setattr(analysis, "extract_requirement",
                        lambda text: called.append(text) or _turnover(999))

    out = analysis.analyze([_cached_row("c1", _turnover(8))], PROFILE, BID_DATE)

    assert called == []
    assert out["verdicts"][0]["verdict"] == Verdict.PASS.value  # the 8, not the fresh 999


def test_editing_the_criterion_text_re_reads_it(monkeypatch):
    """The hash covers the text. A human correcting a mis-extracted clause must not keep the
    reading taken from the old words."""
    _patch(monkeypatch, {"Average annual turnover of Rs 99 Crore": _turnover(99)})
    row = _cached_row("c1", _turnover(8))
    row["verbatim_text"] = "Average annual turnover of Rs 99 Crore"

    out = analysis.analyze([row], PROFILE, BID_DATE)

    assert out["verdicts"][0]["verdict"] == Verdict.FAIL.value


def test_editing_the_prompt_re_reads_every_tender(monkeypatch):
    """Without the prompt's digest in the key, improving the prompt would freeze every
    existing tender on the old reading forever — the cache silently becoming the product."""
    from pipeline import analyzer as pa

    row = _cached_row("c1", _turnover(8))
    monkeypatch.setattr(pa, "PROMPT_DIGEST", "a-different-prompt")
    _patch(monkeypatch, {row["verbatim_text"]: _turnover(99)})

    out = analysis.analyze([row], PROFILE, BID_DATE)

    assert out["verdicts"][0]["verdict"] == Verdict.FAIL.value


def test_a_fresh_reading_is_written_back_against_its_hash(monkeypatch):
    from pipeline.analyzer import requirement_hash

    saved: list = []
    monkeypatch.setattr(analysis.db, "save_criterion_requirements",
                        lambda ws, rows: saved.append((ws, rows)))
    _patch(monkeypatch, {"crit": _turnover(8)})

    analysis.analyze([_row("c1")], PROFILE, BID_DATE, "ws-1")

    assert saved[0][0] == "ws-1"
    assert saved[0][1][0]["id"] == "c1"
    assert saved[0][1][0]["requirement_hash"] == requirement_hash("crit")
    assert saved[0][1][0]["requirement"]["check"] == "turnover_avg"


def test_a_failed_read_is_never_stored(monkeypatch):
    """A timeout is not a reading. Storing `none` at zero confidence would make one outage
    permanent — the next run would serve it from cache instead of trying again."""
    saved: list = []
    monkeypatch.setattr(analysis.db, "save_criterion_requirements",
                        lambda ws, rows: saved.append(rows))
    _patch(monkeypatch, {"crit": _req(check=CheckType.NONE, confidence=0.0)})

    analysis.analyze([_row("c1")], PROFILE, BID_DATE, "ws-1")

    assert saved == [[]]


def test_nothing_is_written_without_a_workspace(monkeypatch):
    """The function stays callable with no database — which is what every test above does."""
    def boom(*_a, **_k):
        raise AssertionError("wrote to the database with no workspace")
    monkeypatch.setattr(analysis.db, "save_criterion_requirements", boom)
    _patch(monkeypatch, {"crit": _turnover(8)})

    analysis.analyze([_row("c1")], PROFILE, BID_DATE)


def test_a_row_stored_in_an_older_shape_degrades_to_needs_review(monkeypatch):
    """Tolerant rehydration. A row written by a previous schema must not raise inside the
    analysis of an unrelated tender; `none` at zero confidence reads needs-review, which is
    a human looking at the clause."""
    from pipeline.analyzer import requirement_hash

    row = _row("c1")
    row["requirement"] = {"model_verdict": "pass", "actual_value_cr": 99}
    row["requirement_hash"] = requirement_hash("crit")

    out = analysis.analyze([row], PROFILE, BID_DATE)

    assert out["verdicts"][0]["verdict"] == Verdict.NEEDS_REVIEW.value
