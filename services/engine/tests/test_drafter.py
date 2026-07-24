"""Drafter wrapping — placeholder fallback, cite-or-flag statuses (no live model)."""

from __future__ import annotations

from pipeline import drafter as dr

CHUNKS = [{"id": "chunk-1", "name": "turnover-cert", "text": "turnover ₹9.7 Cr FY25"}]


def _stub(payload):
    return lambda prompt, schema, **kw: payload


def test_no_evidence_is_placeholder():
    r = dr.draft_response("crit", [])
    assert r.draft_status == "placeholder"
    assert "Insert evidence" in r.draft_text


def test_insufficient_evidence_is_placeholder(monkeypatch):
    monkeypatch.setattr(dr, "generate_json", _stub({"has_sufficient_evidence": False, "sentences": []}))
    assert dr.draft_response("crit", CHUNKS).draft_status == "placeholder"


def test_model_error_falls_back_to_placeholder(monkeypatch):
    def boom(*a, **k):
        raise dr.ModelError("down")

    monkeypatch.setattr(dr, "generate_json", boom)
    assert dr.draft_response("crit", CHUNKS).draft_status == "placeholder"


def test_cited_draft_is_drafted(monkeypatch):
    monkeypatch.setattr(dr, "generate_json", _stub({
        "has_sufficient_evidence": True,
        "sentences": [
            {"text": "The bidder holds the certification.", "citations": ["chunk-1"], "requires_citation": True, "is_financial": False},
            {"text": "This demonstrates compliance.", "citations": [], "requires_citation": False, "is_financial": False},
        ],
    }))
    r = dr.draft_response("crit", CHUNKS)
    assert r.draft_status == "drafted"
    assert r.flags == []
    assert "bidder holds" in r.draft_text


def test_uncited_fact_is_flagged_unverified(monkeypatch):
    monkeypatch.setattr(dr, "generate_json", _stub({
        "has_sufficient_evidence": True,
        "sentences": [{"text": "We have deep experience.", "citations": [], "requires_citation": True, "is_financial": False}],
    }))
    r = dr.draft_response("crit", CHUNKS)
    assert r.draft_status == "unverified"
    assert r.flags[0]["reason"] == "unverified"


def test_model_authored_financial_is_flagged(monkeypatch):
    monkeypatch.setattr(dr, "generate_json", _stub({
        "has_sufficient_evidence": True,
        "sentences": [{"text": "Turnover is ₹9.7 Cr.", "citations": ["chunk-1"], "requires_citation": True, "is_financial": True}],
    }))
    r = dr.draft_response("crit", CHUNKS)
    assert r.draft_status == "unverified"
    assert r.flags[0]["reason"] == "uncited_financial"  # B-AC4: model can't author money
