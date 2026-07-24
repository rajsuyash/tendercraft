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
        return Recommendation.NEEDS_REVIEW  # no gates to clear -> cannot confirm eligibility

    effective = [o.effective_verdict() for o in mandatory]
    if any(v is Verdict.FAIL for v in effective):
        return Recommendation.NO_BID
    if any(v is Verdict.NEEDS_REVIEW for v in effective):
        return Recommendation.NEEDS_REVIEW
    return Recommendation.BID
