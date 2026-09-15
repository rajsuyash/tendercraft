"""Eligibility analysis — the adapter between what the tender asks and what the bidder has.

Three layers, and the split is the point (PRD §2.4):

  - `pipeline.analyzer.extract_requirement` reads ONE criterion and describes what it
    DEMANDS. It is not given the profile, so it cannot report the bidder's numbers.
  - `deterministic.facts.decide_requirement` compares that demand against
    `db.get_profile_context`, using the comparators in `deterministic/eligibility.py`. A
    fact that is missing is needs-review, never a failure.
  - `deterministic.eligibility.recommend` turns the gate verdicts into Bid/No-Bid —
    gates-not-weights (C-FR5), a mandatory Fail caps at No-Bid.

Only GATES reach any of it. `deterministic/requirement_kind.py` says which criteria are
pre-bid conditions on the bidder; a post-award duty, a quoting instruction and a blank
declaration form are none of them and travel back as `checklist`.

Every verdict carries a rationale, a source anchor (C-AC4) and the arithmetic that produced
it, so it can be audited without re-running the model.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date

from pipeline.analyzer import extract_requirement

from .deterministic.eligibility import (
    CriterionOutcome,
    normalise_fy,
    recent_fys,
    recommend,
)
from .deterministic.facts import (
    ProfileFacts,
    Requirement,
    decide_requirement,
    exemption_granted,
    profile_facts,
)
from .deterministic.requirement_kind import effective_kind
from .deterministic.types import (
    FUZZY_REVIEW_THRESHOLD,
    CheckType,
    Recommendation,
    RequirementKind,
    RequirementLevel,
    SourceAnchor,
    Verdict,
)


@dataclass(frozen=True)
class CriterionVerdict:
    """A decided gate, with enough of the arithmetic to audit it afterwards.

    The stored verdict used to carry the answer and none of the working — no threshold, no
    actual value, no operator, no window — so nobody could reconstruct what had been compared
    to what. Everything below is persisted.
    """

    criterion_id: str
    verbatim_text: str
    requirement_level: RequirementLevel
    verdict: Verdict
    confidence: float
    rationale: str
    source_anchor: str
    gap_note: str
    exemption_granted: bool
    check: str = "none"
    operator: str | None = None
    required_display: str = ""
    actual_display: str = ""
    fy_window: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    missing_facts: tuple[str, ...] = ()
    exemption_clause: str = ""



def _checklist_item(row: dict, note: str = "") -> dict:
    """A requirement that is not a question about whether the bidder qualifies.

    Named rather than silently dropped: an obligation nobody planned for is still a way to
    lose money, it just is not a reason to skip the bid.
    """
    return {
        "criterion_id": row["id"],
        "verbatim_text": row.get("verbatim_text", ""),
        "kind": effective_kind(row).value,
        "requirement_level": str(row.get("requirement_level") or ""),
        "source_anchor": _anchor(row),
        "note": note,
    }


def _anchor(row: dict) -> str:
    # Page alone is a resolvable anchor: real tenders state obligations in unnumbered
    # prose, and requiring a clause here silently produced anchor=None, which the lock
    # gate then refused forever (types.SourceAnchor.is_resolvable).
    if not row.get("anchor_page"):
        return "no anchor"
    return SourceAnchor(
        page=row["anchor_page"],
        clause=row.get("anchor_clause") or "",
        document=row.get("anchor_document") or "",
    ).label()


def decide(
    row: dict, req: Requirement, facts: ProfileFacts, bid_date: date | None = None
) -> CriterionVerdict:
    """Decide one gate from the tender's demand and the bidder's own records.

    Both halves used to come from the model, and the numeric branch skipped the confidence
    and evidence guard the other branch applied — so a model at confidence 0.01 with no
    evidence produced a hard PASS. Now the model describes the requirement, Python supplies
    the facts, and `deterministic/facts.py` compares them.
    """
    level = RequirementLevel(row["requirement_level"])

    window: tuple[str, ...] = ()
    if req.check is CheckType.TURNOVER_AVG:
        window = _fy_window(req, bid_date)

    outcome = decide_requirement(req, facts, bid_date, window)
    granted = exemption_granted(req, facts, outcome.verdict)

    return CriterionVerdict(
        criterion_id=row["id"],
        verbatim_text=row["verbatim_text"],
        requirement_level=level,
        verdict=outcome.verdict,
        confidence=req.confidence,
        rationale=outcome.rationale,
        source_anchor=_anchor(row),
        gap_note="" if granted else outcome.gap_note,
        exemption_granted=granted,
        check=outcome.check.value,
        operator=outcome.operator,
        required_display=outcome.required_display,
        actual_display=outcome.actual_display,
        fy_window=outcome.fy_window or window,
        evidence_ids=outcome.evidence_ids,
        missing_facts=outcome.missing_facts,
        exemption_clause=req.exemption_clause if granted else "",
    )


def _fy_window(req: Requirement, bid_date: date | None) -> tuple[str, ...]:
    """Which financial years an average turnover requirement covers.

    Named years first — the clause said them. Otherwise a count plus the bid date, because
    "the last three financial years" is relative to when the bid closes. NEVER derived from
    the years the BIDDER happens to have on file: averaging whatever is stored and calling it
    the answer is the exact defect `sections.py::assemble_compliance_pq` was rewritten to
    kill, on a hard non-overridable financial gate.
    """
    if req.fy_labels:
        return tuple(fy for fy in (normalise_fy(x) for x in req.fy_labels) if fy)
    if req.fy_count and bid_date:
        return recent_fys(bid_date, req.fy_count)
    return ()


def _weighted_score(verdicts: list[CriterionVerdict]) -> int | None:
    """Strength on desirable/scored criteria only (C-FR5) — mandatory gates don't count here.

    `None`, not 0, when the tender states nothing scoreable. Zero out of a hundred is a
    claim that the bidder scored nothing; an absent denominator is a different sentence, and
    a catalogue bid legitimately states no scored criterion at all. Once only gates are
    evaluated this is the common case rather than the edge one — the live wire-rope bid has
    five gates and no scored criteria, and the card read "0/100" beside a verdict that had
    found no gaps.
    """
    scored = [v for v in verdicts if v.requirement_level is not RequirementLevel.MANDATORY]
    if not scored:
        return None
    passed = sum(1 for v in scored if v.verdict is Verdict.PASS)
    return round(100 * passed / len(scored))


def analyze(
    criteria_rows: list[dict], profile_json: dict, bid_date: date | None = None
) -> dict:
    """Full analysis over a locked TOM's criteria vs the vendor profile.

    ONLY GATES ARE EVALUATED, and only gates vote. A pre-bid eligibility condition is a
    question about the bidder and has an answer; a post-award duty, a quoting instruction and
    a blank declaration form do not, and scoring them produced a NO-BID on the live wire-rope
    bid from a clause about an inspection that happens months after a contract exists. See
    `deterministic/requirement_kind.py` for the measurement.

    Everything else travels back as `checklist` — visible, actionable, and not a verdict. It
    is a cost saving as well as a correctness fix: 18 of 35 criteria on that tender were
    mandatory and 2 were gates, so this is one model call instead of eighteen.
    """
    gates = [r for r in criteria_rows if effective_kind(r) is RequirementKind.GATE]
    checklist = [
        _checklist_item(r)
        for r in criteria_rows
        if effective_kind(r) is not RequirementKind.GATE
    ]

    # Evaluate criteria concurrently — each is an independent model call; sequential blows
    # the request budget on a large tender (retry cap bounds cost per call).
    with ThreadPoolExecutor(max_workers=6) as pool:
        reqs = list(pool.map(lambda row: extract_requirement(row["verbatim_text"]), gates))

    # A second, independent reading. `requirement_kind` classifies from the sentence's
    # vocabulary; the extractor read the whole clause and can say there is no pre-bid
    # condition in it at all. When it says so CONFIDENTLY, the rules over-reached — a
    # requirement nobody can check is not a gate, and scoring it would park the card on
    # needs-review permanently, with no fact a user could ever supply to clear it.
    #
    # The confidence floor is the whole guard. A `none` at zero confidence is a MODEL
    # FAILURE, not a reading, and must stay a gate so it reads needs-review and a human
    # looks at it. Those two states are identical in the payload and opposite in meaning.
    scored, demoted = [], []
    for row, req in zip(gates, reqs, strict=True):
        target = (demoted if req.check is CheckType.NONE
                  and req.confidence >= FUZZY_REVIEW_THRESHOLD else scored)
        target.append((row, req))
    checklist.extend(
        _checklist_item(row, note="Classified as an eligibility gate, but the clause states "
                                 "no pre-bid condition that can be checked. Override its kind "
                                 "if you disagree.")
        for row, _ in demoted
    )

    facts = profile_facts(profile_json or {})
    verdicts = [decide(row, r, facts, bid_date) for row, r in scored]

    outcomes = [
        CriterionOutcome(
            id=v.criterion_id,
            requirement_level=v.requirement_level,
            verdict=v.verdict,
            exemption_granted=v.exemption_granted,
        )
        for v in verdicts
    ]
    recommendation = recommend(outcomes)

    gaps = [
        {"criterion_id": v.criterion_id, "gap": v.gap_note, "source": v.source_anchor}
        for v in verdicts
        if v.verdict is Verdict.FAIL and v.gap_note
    ]
    counts = {
        "pass": sum(1 for v in verdicts if v.verdict is Verdict.PASS),
        "fail": sum(1 for v in verdicts if v.verdict is Verdict.FAIL),
        "needs_review": sum(1 for v in verdicts if v.verdict is Verdict.NEEDS_REVIEW),
    }

    return {
        "recommendation": recommendation.value,
        "conservative": recommendation is Recommendation.NO_BID,
        "weighted_score": _weighted_score(verdicts),
        "counts": counts,
        # What the tender asks for that is not a question about the bidder. Named rather than
        # silently dropped: an obligation nobody planned for is still a way to lose money,
        # it just is not a reason to skip the bid.
        "checklist": checklist,
        "verdicts": [
            {
                "criterion_id": v.criterion_id,
                "verbatim_text": v.verbatim_text,
                "requirement_level": v.requirement_level.value,
                "verdict": v.verdict.value,
                "confidence": v.confidence,
                "rationale": v.rationale,
                "source_anchor": v.source_anchor,
                "gap_note": v.gap_note,
                "exemption_granted": v.exemption_granted,
                # The working, not just the answer — so a verdict can be audited without
                # re-running it.
                "check": v.check,
                "operator": v.operator,
                "required_display": v.required_display,
                "actual_display": v.actual_display,
                "fy_window": list(v.fy_window),
                "evidence_ids": list(v.evidence_ids),
                "missing_facts": list(v.missing_facts),
                "exemption_clause": v.exemption_clause,
            }
            for v in verdicts
        ],
        "gaps": gaps,
    }

