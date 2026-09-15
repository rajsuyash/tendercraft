"""Eligibility analysis — deterministic decisions over the model's evaluations (Module C).

The model (pipeline.analyzer) extracts values + a proposed verdict per criterion; THIS
module decides:
  - numeric criteria -> `compare_numeric` (C-FR1); the model never decides a number
  - fuzzy criteria    -> the 0.75 router; a sub-0.75 or evidence-less pass -> Needs-review (C-AC5)
  - exemptions        -> a granted MSE/DPIIT relaxation waives a Fail (C-FR3)
  - Bid/No-Bid        -> gates-not-weights via `recommend` (C-FR5); a mandatory Fail caps at No-Bid
Every verdict carries a rationale + source anchor (C-AC4).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from pipeline.analyzer import ModelEval, evaluate_criterion

from .deterministic.eligibility import CriterionOutcome, compare_numeric, recommend
from .deterministic.requirement_kind import effective_kind
from .deterministic.types import (
    FUZZY_REVIEW_THRESHOLD,
    Recommendation,
    RequirementKind,
    RequirementLevel,
    SourceAnchor,
    Verdict,
)


@dataclass(frozen=True)
class CriterionVerdict:
    criterion_id: str
    verbatim_text: str
    requirement_level: RequirementLevel
    verdict: Verdict
    confidence: float
    rationale: str
    source_anchor: str
    gap_note: str
    exemption_granted: bool


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


def decide(row: dict, ev: ModelEval) -> CriterionVerdict:
    """Apply the deterministic decision layer to one model evaluation."""
    level = RequirementLevel(row["requirement_level"])

    if (
        ev.check_type == "numeric"
        and ev.required_value_cr is not None
        and ev.actual_value_cr is not None
        and ev.operator
    ):
        passed = compare_numeric(ev.actual_value_cr, ev.required_value_cr, ev.operator)
        verdict = Verdict.PASS if passed else Verdict.FAIL
    else:
        verdict = Verdict(ev.model_verdict)
        # C-AC5 + "no pass on empty evidence": a low-confidence or unevidenced pass is review
        if verdict is Verdict.PASS and (
            ev.confidence < FUZZY_REVIEW_THRESHOLD or not ev.evidence_ids
        ):
            verdict = Verdict.NEEDS_REVIEW

    exemption_granted = verdict is Verdict.FAIL and ev.exemption_applies
    gap = ev.gap_note if verdict is Verdict.FAIL and not exemption_granted else ""

    return CriterionVerdict(
        criterion_id=row["id"],
        verbatim_text=row["verbatim_text"],
        requirement_level=level,
        verdict=verdict,
        confidence=ev.confidence,
        rationale=ev.rationale,
        source_anchor=_anchor(row),
        gap_note=gap,
        exemption_granted=exemption_granted,
    )


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


def analyze(criteria_rows: list[dict], profile_json: dict) -> dict:
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
        {
            "criterion_id": r["id"],
            "verbatim_text": r.get("verbatim_text", ""),
            "kind": effective_kind(r).value,
            "requirement_level": str(r.get("requirement_level") or ""),
            "source_anchor": _anchor(r),
        }
        for r in criteria_rows
        if effective_kind(r) is not RequirementKind.GATE
    ]

    # Evaluate criteria concurrently — each is an independent model call; sequential blows
    # the request budget on a large tender (retry cap bounds cost per call).
    with ThreadPoolExecutor(max_workers=6) as pool:
        evals = list(
            pool.map(lambda row: evaluate_criterion(row["verbatim_text"], profile_json), gates)
        )
    verdicts = [decide(row, ev) for row, ev in zip(gates, evals, strict=True)]

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
            }
            for v in verdicts
        ],
        "gaps": gaps,
    }


def _kind_counts(criteria_rows: list[dict]) -> dict[str, int]:
    """How many of each kind, for a screen that wants to explain the verdict's scope."""
    counts = dict.fromkeys((k.value for k in RequirementKind), 0)
    for row in criteria_rows:
        counts[effective_kind(row).value] += 1
    return counts
