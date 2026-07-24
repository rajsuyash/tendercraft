"""Score-estimate suppression gate — D-AC4 / D-FR2 / RB-4 (tendercraft-PRD.md Module D).

The estimator must suppress itself honestly rather than emit a confident number on thin
data (Appendix C #4). Suppress when either:
  - fewer than the cluster minimum of comparable historical outcomes exist (D-FR2), or
  - the cluster's directional accuracy has fallen below the floor (RB-4).

This is a gate, not a model: given the cluster statistics, the decision is deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass

from .types import MIN_DIRECTIONAL_ACCURACY, SUPPRESSION_MIN_OUTCOMES


@dataclass(frozen=True)
class SuppressionDecision:
    suppressed: bool
    reason: str | None = None


def evaluate_suppression(
    comparable_outcomes: int,
    directional_accuracy: float | None = None,
    min_outcomes: int = SUPPRESSION_MIN_OUTCOMES,
) -> SuppressionDecision:
    """Return whether the score estimate must be suppressed for this cluster."""
    if comparable_outcomes < 0:
        raise ValueError("comparable_outcomes cannot be negative")

    if comparable_outcomes < min_outcomes:
        return SuppressionDecision(
            suppressed=True,
            reason=(
                f"insufficient historical data: {comparable_outcomes} < {min_outcomes} "
                "comparable outcomes (D-FR2)"
            ),
        )

    # directional_accuracy is None when the cluster has no accuracy signal yet -> treated as
    # "no degradation observed", so count-driven suppression (D-FR2) is the only trigger.
    if directional_accuracy is not None and directional_accuracy < MIN_DIRECTIONAL_ACCURACY:
        return SuppressionDecision(
            suppressed=True,
            reason=(
                f"cluster directional accuracy {directional_accuracy:.2f} < "
                f"{MIN_DIRECTIONAL_ACCURACY:.2f} (RB-4)"
            ),
        )

    return SuppressionDecision(suppressed=False)
