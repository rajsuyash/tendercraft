"""D-AC4/D-FR1/D-FR3/D-AC5 score estimator."""

from app import estimator

ANALYSIS = {
    "weighted_score": 68,
    "verdicts": [
        {"criterion_id": "a", "verdict": "pass", "rationale": "ok", "source_anchor": "p.1"},
        {"criterion_id": "b", "verdict": "fail", "rationale": "gap", "source_anchor": "p.2"},
        {"criterion_id": "c", "verdict": "needs_review", "rationale": "unsure", "source_anchor": "p.3"},
    ],
}


def test_suppressed_on_thin_data():
    r = estimator.estimate(cluster_outcome_count=12, analysis=ANALYSIS)
    assert r["suppressed"] is True
    assert "insufficient historical data" in r["reason"]


def test_estimate_is_a_range_never_a_point():
    r = estimator.estimate(cluster_outcome_count=47, analysis=ANALYSIS)
    assert r["suppressed"] is False
    low, high = r["range"]
    assert low < high  # D-FR1: always a range, never a single number


def test_weak_sections_from_fails_and_reviews_ranked():
    r = estimator.estimate(cluster_outcome_count=47, analysis=ANALYSIS)
    weak = r["weak_sections"]
    assert {w["criterion_id"] for w in weak} == {"b", "c"}  # the pass is not weak
    assert weak[0]["verdict"] == "fail"  # fail ranked above needs_review


def test_attribution_covers_every_criterion():
    r = estimator.estimate(cluster_outcome_count=47, analysis=ANALYSIS)
    assert {a["criterion_id"] for a in r["attribution"]} == {"a", "b", "c"}  # D-AC5


def test_directional_accuracy_below_floor_suppresses():
    r = estimator.estimate(cluster_outcome_count=100, analysis=ANALYSIS, directional_accuracy=0.6)
    assert r["suppressed"] is True
    assert "RB-4" in r["reason"]


def test_band_tightens_with_more_data():
    small = estimator.estimate(30, ANALYSIS)["range"]
    large = estimator.estimate(120, ANALYSIS)["range"]
    assert (large[1] - large[0]) < (small[1] - small[0])
