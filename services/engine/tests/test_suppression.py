"""D-AC4 / D-FR2 / RB-4 score-estimate suppression."""

import pytest

from app.deterministic.suppression import evaluate_suppression
from app.deterministic.types import SUPPRESSION_MIN_OUTCOMES


def test_below_outcome_floor_suppresses():
    d = evaluate_suppression(comparable_outcomes=12)
    assert d.suppressed is True
    assert "insufficient historical data" in d.reason


def test_at_outcome_floor_does_not_suppress():
    d = evaluate_suppression(comparable_outcomes=SUPPRESSION_MIN_OUTCOMES)
    assert d.suppressed is False
    assert d.reason is None


def test_above_floor_with_good_accuracy_estimates():
    assert evaluate_suppression(47, directional_accuracy=0.78).suppressed is False


def test_low_directional_accuracy_suppresses_even_with_data():
    # RB-4: enough data, but the cluster's predictions have degraded
    d = evaluate_suppression(100, directional_accuracy=0.65)
    assert d.suppressed is True
    assert "RB-4" in d.reason


def test_directional_accuracy_boundary_is_inclusive():
    assert evaluate_suppression(100, directional_accuracy=0.70).suppressed is False


def test_outcome_floor_checked_before_accuracy():
    # thin data reason wins even if accuracy is also low
    d = evaluate_suppression(5, directional_accuracy=0.10)
    assert "insufficient historical data" in d.reason


def test_custom_min_outcomes_threshold():
    assert evaluate_suppression(20, min_outcomes=15).suppressed is False


def test_negative_outcomes_rejected():
    with pytest.raises(ValueError):
        evaluate_suppression(-1)
