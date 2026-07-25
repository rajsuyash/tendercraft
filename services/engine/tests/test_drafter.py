"""Drafter wrapping — placeholder fallback, cite-or-flag statuses (no live model)."""

from __future__ import annotations

from pipeline import drafter as dr

CHUNKS = [{"id": "chunk-1", "name": "turnover-cert", "text": "turnover ₹9.7 Cr FY25"}]


def _stub(payload):
    return lambda prompt, schema, **kw: payload


def _sent(text, citations=(), cls="claim"):
    return {"text": text, "citations": list(citations), "proposed_class": cls}


def test_no_evidence_is_placeholder():
    r = dr.draft_response("crit", [])
    assert r.draft_status == "placeholder"
    assert "Insert evidence" in r.draft_text


def test_insufficient_evidence_is_placeholder(monkeypatch):
    monkeypatch.setattr(
        dr, "generate_json", _stub({"has_sufficient_evidence": False, "sentences": []})
    )
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
            _sent("The bidder holds the certification.", ["chunk-1"]),
            _sent("This demonstrates compliance.", cls="narrative"),
        ],
    }))
    r = dr.draft_response("crit", CHUNKS)
    # Both sentences resolve to CLAIM — a per-criterion response is a COMPLIANCE section,
    # so "narrative" is unavailable. The second cites nothing, hence unverified.
    assert r.draft_status == "unverified"
    assert "bidder holds" in r.draft_text
    assert [s["cls"] for s in r.sentences] == ["claim", "claim"]


def test_uncited_fact_is_flagged_unverified(monkeypatch):
    monkeypatch.setattr(dr, "generate_json", _stub({
        "has_sufficient_evidence": True,
        "sentences": [_sent("We have deep experience.")],
    }))
    r = dr.draft_response("crit", CHUNKS)
    assert r.draft_status == "unverified"
    assert r.flags[0]["reason"] == "unverified"


def test_model_authored_financial_is_flagged(monkeypatch):
    monkeypatch.setattr(dr, "generate_json", _stub({
        "has_sufficient_evidence": True,
        "sentences": [_sent("Turnover is ₹9.7 Cr.", ["chunk-1"])],
    }))
    r = dr.draft_response("crit", CHUNKS)
    assert r.draft_status == "unverified"
    assert r.flags[0]["reason"] == "uncited_financial"  # B-AC4: model can't author money


def test_financial_gate_no_longer_depends_on_the_model_self_reporting(monkeypatch):
    """Regression for the closed defect.

    The model used to supply `is_financial`, and prompts/drafter.md told it to always send
    false — so the 'hard, non-overridable' B-AC4 gate never fired. Now the amount is found
    in the text, whatever the model claims about itself.
    """
    monkeypatch.setattr(dr, "generate_json", _stub({
        "has_sufficient_evidence": True,
        "sentences": [
            # Every escape the old shape allowed, in one response.
            _sent("Our turnover is Rs 8.2 Crore.", ["chunk-1"], cls="narrative"),
        ],
    }))
    r = dr.draft_response("crit", CHUNKS)
    assert r.flags[0]["reason"] == "uncited_financial"
    assert r.sentences[0]["is_financial"] is True


def test_compliant_phrasing_without_a_figure_still_drafts(monkeypatch):
    """The prompt's prescribed output must remain clean — FY refs are not money."""
    monkeypatch.setattr(dr, "generate_json", _stub({
        "has_sufficient_evidence": True,
        "sentences": [_sent(
            "The bidder satisfies the minimum average annual turnover requirement for "
            "FY23-FY25, as certified by the chartered accountant.",
            ["chunk-1"],
        )],
    }))
    r = dr.draft_response("crit", CHUNKS)
    assert r.draft_status == "drafted"
    assert r.flags == []
