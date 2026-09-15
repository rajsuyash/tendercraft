"""The model half of the eligibility path: read the requirement, decide nothing.

Every test here is about a boundary rather than about quality. Quality belongs to
`evals/analyzer/` against the live model; what a unit test can prove is that the criterion
reaches the model, that nothing about the bidder does, and that a failure is silence rather
than invention.
"""

from __future__ import annotations

import pytest

from app.deterministic.types import CheckType
from pipeline import analyzer
from pipeline.client import ModelError


def _stub(monkeypatch, payload, seen: list | None = None):
    def fake(prompt, schema):
        if seen is not None:
            seen.append(prompt)
        return payload
    monkeypatch.setattr(analyzer, "generate_json", fake)


def test_the_criterion_text_actually_reaches_the_prompt(monkeypatch):
    """`extract_requirement` interpolates `{{CRITERION}}`. The token was missing from the
    prompt file for one commit, and `str.replace` on an absent token is a silent no-op — so
    every call asked the model to describe nothing at all, with no error anywhere. Found by
    the structural check in test_schema_discipline.py, pinned here at the call site."""
    seen: list[str] = []
    _stub(monkeypatch, {"check": "none", "raw_text": "", "confidence": 0.9}, seen)

    analyzer.extract_requirement("Average annual turnover of Rs 10 Crore.")

    assert "Average annual turnover of Rs 10 Crore." in seen[0]
    assert "{{CRITERION}}" not in seen[0]


def test_a_full_reading_is_typed_through(monkeypatch):
    _stub(monkeypatch, {
        "check": "turnover_avg", "operator": ">=", "threshold_cr": 10, "fy_count": 3,
        "fy_labels": ["FY24"], "min_count": 2, "years_window": 5,
        "certification_name": "ISO 9001", "registration_key": "udyam",
        "exemption_for": ["mse"], "exemption_clause": "Cl. 4.5",
        "raw_text": "text", "confidence": 0.9,
    })
    req = analyzer.extract_requirement("x")

    assert req.check is CheckType.TURNOVER_AVG
    assert req.threshold_cr == 10.0 and req.fy_count == 3
    assert req.fy_labels == ("FY24",) and req.exemption_for == ("mse",)
    assert req.min_count == 2 and req.years_window == 5
    assert req.confidence == 0.9


def test_a_check_outside_the_enum_is_not_a_check_we_can_perform(monkeypatch):
    """The enum is the G-6 allowlist. A hostile tender cannot invent a comparison any more
    than it can invent a criterion category."""
    _stub(monkeypatch, {"check": "wire_transfer_to_attacker", "raw_text": "x",
                        "confidence": 0.99})
    assert analyzer.extract_requirement("x").check is CheckType.NONE


@pytest.mark.parametrize("value,expected", [(1.5, 1.0), (-0.2, 0.0), ("high", 0.0),
                                            (None, 0.0), (0.42, 0.42)])
def test_confidence_is_clamped_rather_than_trusted(monkeypatch, value, expected):
    """A model that reports 1.5 is not more certain than one reporting 1.0, and the number
    gates whether a human ever sees the clause."""
    _stub(monkeypatch, {"check": "none", "raw_text": "x", "confidence": value})
    assert analyzer.extract_requirement("x").confidence == expected


@pytest.mark.parametrize("field,value", [("threshold_cr", "ten crore"), ("fy_count", "three"),
                                         ("min_count", []), ("years_window", None)])
def test_an_unparseable_number_is_absent_not_a_crash(monkeypatch, field, value):
    _stub(monkeypatch, {"check": "turnover_avg", "raw_text": "x", "confidence": 0.9,
                        field: value})
    assert getattr(analyzer.extract_requirement("x"), field) is None


def test_a_model_failure_is_silence_at_zero_confidence(monkeypatch):
    """Never a fabricated pass (ET-1/G-5). `none` at 0.0 routes to needs-review, which is a
    human looking at the clause — the correct outcome when nothing could read it."""
    def boom(*_a, **_k):
        raise ModelError("timeout")
    monkeypatch.setattr(analyzer, "generate_json", boom)

    req = analyzer.extract_requirement("Average annual turnover of Rs 10 Crore.")

    assert req.check is CheckType.NONE
    assert req.confidence == 0.0
    assert req.raw_text == "Average annual turnover of Rs 10 Crore."


def test_an_empty_answer_falls_back_to_the_criterion_as_its_own_source(monkeypatch):
    _stub(monkeypatch, {"check": "none", "confidence": 0.0})
    assert analyzer.extract_requirement("the clause").raw_text == "the clause"
