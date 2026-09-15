"""Eligibility comparators + Bid/No-Bid recommendation.

PRD Module C, deterministic half (§2.4): numeric/date/boolean criteria are decided
here, never by a model.
  - C-FR1  numeric/date/boolean comparators, with financial-year normalization
  - C-FR3  exemption overlays waive a criterion only where the tender grants it
  - C-FR5  mandatory eligibility criteria are GATES, not weights:
           one hard mandatory Fail caps the recommendation at No-Bid, whatever the score
  - ET-1   borderline never auto-passes — an unresolved mandatory gate -> Needs-review

Fuzzy ("similar nature of work") matching is NOT here — that is the AI matcher (C-FR2);
its sub-0.75 routing lives in the pipeline, this module only consumes final verdicts.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from .types import Recommendation, RequirementLevel, Verdict

_OPS = {
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    "==": lambda a, b: a == b,
}


def compare_numeric(actual: float, required: float, op: str = ">=") -> bool:
    """Deterministic numeric comparison. Unknown operator is a programming error."""
    try:
        return _OPS[op](actual, required)
    except KeyError as exc:
        raise ValueError(f"unsupported operator {op!r}") from exc


def average_annual_turnover(
    fy_values: Mapping[str, float], required_fys: Sequence[str]
) -> float | None:
    """Average turnover across the required financial years (C-FR1 FY normalization).

    Returns None when any required FY is absent — the caller must route that to
    Needs-review, never assume zero (assuming zero would manufacture a false Fail).
    """
    if not required_fys:
        raise ValueError("required_fys must not be empty")
    unique_fys = list(dict.fromkeys(required_fys))  # dedupe: a repeated FY must not double-count
    values = [fy_values[fy] for fy in unique_fys if fy in fy_values]
    if len(values) != len(unique_fys):
        return None
    return sum(values) / len(unique_fys)


_FY = re.compile(r"(?:FY\s*)?(\d{4}|\d{2})\s*[-/]?\s*(\d{2,4})?", re.I)


def normalise_fy(label: str) -> str | None:
    """"2022-23", "F.Y. 2024-25", "FY 24-25" -> the profile's own label ("FY23", "FY25").

    Indian financial years end on 31 March and are named for the CLOSING year, which is what
    `profile_financials.fy_label` stores. A label that will not normalise returns None and is
    simply absent from the window — `average_annual_turnover` then returns None and the gate
    reads needs-review, which is honest by construction.
    """
    text = (label or "").strip().replace(".", "")
    m = _FY.search(text)
    if not m:
        return None
    first, second = m.group(1), m.group(2)
    end = second or first
    if len(end) == 4:
        end = end[2:]
    if len(first) == 4 and not second:
        # A single four-digit year names itself.
        end = first[2:]
    return f"FY{int(end):02d}" if end.isdigit() else None


def recent_fys(bid_date: date, count: int) -> tuple[str, ...]:
    """The last `count` COMPLETED Indian financial years, oldest first.

    A bid on 14 August 2026 sits in FY27, whose year is not over; the last completed one ends
    31 March 2026 and the profile labels it FY26. Off by one here shifts the whole window a
    year on a hard, non-overridable financial gate, which is why this is pinned by its own
    test rather than inlined at the call site.
    """
    if count <= 0:
        return ()
    # Before April the current calendar year's FY has not closed either.
    last_complete = bid_date.year if bid_date.month >= 4 else bid_date.year - 1
    return tuple(f"FY{(last_complete - i) % 100:02d}" for i in range(count - 1, -1, -1))


def is_valid_on(expiry: date, bid_date: date) -> bool:
    """A certificate is valid if it has not expired on the bid date (inclusive)."""
    return expiry >= bid_date


def completed_within(completion: date, reference: date, years: int) -> bool:
    """True if `completion` falls within `years` before `reference` (inclusive window)."""
    if years <= 0:
        raise ValueError("years must be positive")
    earliest = reference.replace(year=reference.year - years)
    return earliest <= completion <= reference


@dataclass(frozen=True)
class CriterionOutcome:
    """A resolved mandatory/desirable criterion feeding the recommendation."""

    id: str
    requirement_level: RequirementLevel
    verdict: Verdict
    exemption_granted: bool = False  # C-FR3: tender text grants the relaxation
    exemption_clause: str | None = None

    def effective_verdict(self) -> Verdict:
        """Apply a granted exemption: a Fail the tender explicitly waives becomes a Pass."""
        if self.verdict is Verdict.FAIL and self.exemption_granted:
            return Verdict.PASS
        return self.verdict


def recommend(outcomes: Sequence[CriterionOutcome]) -> Recommendation:
    """Bid / No-Bid / Needs-review from criterion outcomes (C-FR5 gates-not-weights, ET-1).

    Only MANDATORY criteria gate. A single mandatory Fail -> No-Bid. A mandatory
    Needs-review (and no Fail) -> Needs-review (conservative). All mandatory Pass -> Bid.
    """
    mandatory = [o for o in outcomes if o.requirement_level is RequirementLevel.MANDATORY]
    if not mandatory:
        # NOT needs-review. "Needs review" asks a human to go and resolve something; a tender
        # that states no mandatory eligibility gate has nothing to resolve and disqualifies
        # nobody. Reading it as needs-review is how a catalogue bid inside the bidder's own
        # product line came back looking unresolved forever.
        return Recommendation.NO_GATES

    effective = [o.effective_verdict() for o in mandatory]
    if any(v is Verdict.FAIL for v in effective):
        return Recommendation.NO_BID
    if any(v is Verdict.NEEDS_REVIEW for v in effective):
        return Recommendation.NEEDS_REVIEW
    return Recommendation.BID
