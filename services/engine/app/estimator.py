"""Score estimator v0 (Module D). Suppresses honestly on thin data; else a range, never a point.

No trained model yet — this is a transparent heuristic over the eligibility analysis, gated
by the deterministic suppression rule (D-AC4/D-FR2). It always emits a RANGE (D-FR1), ranks
weak sections by heuristic marginal impact (D-FR3), and attributes per criterion (D-AC5).
When the corpus crosses threshold, the heuristic is replaced by the calibrated model; the
suppression gate and the range/attribution contract stay identical.
"""

from __future__ import annotations

from .deterministic.suppression import evaluate_suppression

_THRESHOLD = 70  # typical technical-qualifying mark


def estimate(
    cluster_outcome_count: int, analysis: dict, directional_accuracy: float | None = None
) -> dict:
    """Return a suppressed marker or a score-range estimate for a proposal's analysis."""
    decision = evaluate_suppression(cluster_outcome_count, directional_accuracy)
    if decision.suppressed:
        return {"suppressed": True, "reason": decision.reason}

    base = int(analysis.get("weighted_score", 0))
    # Band tightens as the corpus grows past the floor (never a point — D-FR1).
    band = max(5, round(20 * (30 / cluster_outcome_count)))
    low, high = max(0, base - band), min(100, base + band)
    likelihood = round(100 * max(0.0, min(1.0, (base - (_THRESHOLD - band)) / (2 * band))))

    verdicts = analysis.get("verdicts", [])
    weak = [
        {
            "criterion_id": v["criterion_id"],
            "verdict": v["verdict"],
            "expected_delta": "+2–5 marks" if v["verdict"] == "fail" else "+1–3 marks",
            "rationale": v.get("rationale", ""),
            "source": v.get("source_anchor", ""),
        }
        for v in verdicts
        if v["verdict"] in ("fail", "needs_review")
    ]
    # rank fails above needs_review (bigger marginal impact)
    weak.sort(key=lambda w: 0 if w["verdict"] == "fail" else 1)

    attribution = [
        {
            "criterion_id": v["criterion_id"],
            "verdict": v["verdict"],
            "rationale": v.get("rationale", ""),
        }
        for v in verdicts
    ]

    return {
        "suppressed": False,
        "range": [low, high],
        "threshold": _THRESHOLD,
        "clears_threshold_likelihood": likelihood,
        "weak_sections": weak,
        "attribution": attribution,
        "cluster_outcomes": cluster_outcome_count,
    }
