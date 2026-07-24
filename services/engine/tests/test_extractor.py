"""Extractor wrapping logic — deterministic parts, no live model calls.

Confidence routing (A-FR4/A-AC5), model-failure fallback (G-5: never crash/invent),
and confidence clamping are all pure given the model output, so they unit-test with a
stubbed client.
"""

from __future__ import annotations

import pytest

from pipeline import extractor as ex
from pipeline.client import ModelError


def _stub(criteria):
    return lambda prompt, schema, **kw: {"criteria": criteria}


BASE = {
    "verbatim_text": "Average annual turnover of not less than Rs. 10 Crores.",
    "category": "eligibility",
    "requirement_level": "mandatory",
    "anchor_clause": "4.1(a)",
    "evidence_required": "CA-certified turnover certificate",
    "evaluation_weight": None,
}


def test_model_failure_returns_empty(monkeypatch):
    def boom(*a, **k):
        raise ModelError("down")

    monkeypatch.setattr(ex, "generate_json", boom)
    assert ex.extract_from_page("some text", 12) == []  # fallback -> manual review, no crash


def test_low_confidence_flags_needs_confirmation(monkeypatch):
    monkeypatch.setattr(ex, "generate_json", _stub([{**BASE, "confidence": 0.64}]))
    [c] = ex.extract_from_page("t", 12)
    assert c.needs_confirmation is True  # sub-0.80 must be human-confirmed (A-AC5)
    assert c.anchor_page == 12


def test_high_confidence_not_flagged(monkeypatch):
    monkeypatch.setattr(ex, "generate_json", _stub([{**BASE, "confidence": 0.92}]))
    [c] = ex.extract_from_page("t", 5)
    assert c.needs_confirmation is False
    assert c.category == "eligibility"


def test_confidence_clamped_above_one(monkeypatch):
    monkeypatch.setattr(ex, "generate_json", _stub([{**BASE, "confidence": 1.5}]))
    [c] = ex.extract_from_page("t", 1)
    assert c.confidence == 1.0
    assert c.needs_confirmation is False


def test_confidence_clamped_below_zero(monkeypatch):
    monkeypatch.setattr(ex, "generate_json", _stub([{**BASE, "confidence": -0.2}]))
    [c] = ex.extract_from_page("t", 1)
    assert c.confidence == 0.0
    assert c.needs_confirmation is True


def test_empty_criteria_is_empty_list(monkeypatch):
    monkeypatch.setattr(ex, "generate_json", _stub([]))
    assert ex.extract_from_page("logistics only", 1) == []


def test_missing_optional_fields_default(monkeypatch):
    minimal = {
        "verbatim_text": "x",
        "category": "terms",
        "requirement_level": "mandatory",
        "confidence": 0.9,
        "anchor_clause": "",
    }
    monkeypatch.setattr(ex, "generate_json", _stub([minimal]))
    [c] = ex.extract_from_page("t", 3)
    assert c.evidence_required == ""
    assert c.evaluation_weight is None
    assert c.anchor_clause == ""


@pytest.mark.parametrize("conf,expected", [(0.79, True), (0.80, False), (0.81, False)])
def test_threshold_boundary(monkeypatch, conf, expected):
    monkeypatch.setattr(ex, "generate_json", _stub([{**BASE, "confidence": conf}]))
    [c] = ex.extract_from_page("t", 1)
    assert c.needs_confirmation is expected
