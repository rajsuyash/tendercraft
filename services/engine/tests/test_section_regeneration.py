"""Regeneration must not quietly undo human work — the B-FR4 guarantee, from the other side.

The watermark rule says unapproved AI prose is marked and cannot be exported. Approval is
what removes the mark. So a regeneration that replaces a section's text while leaving
`approved_at` in place produces the exact state the rule exists to forbid: new, unreviewed
model prose carrying a human's signature. It was reachable from one click ("Regenerate"),
and from `/prepare`, which the readiness screen runs on every "Re-match".

Three properties, one test each:
  - a section a human edited is left alone entirely
  - a section that IS rewritten loses its approval in the same write
  - a per-criterion response a human accepted a prior answer into survives Re-match
"""

from types import SimpleNamespace

import pytest

from app import proposal_routes, spec_service
from app.sections import NARRATIVE_KEYS, SECTION_SPECS


class _Drafted(SimpleNamespace):
    pass


def _draft(key, heading, target, context, ev, needs, style):
    return _Drafted(key=key, body_md=f"fresh {key}", sentences=[], status="drafted",
                    confidence=1.0, flags=[], word_count=2)


@pytest.fixture
def wired(monkeypatch):
    """Everything `do_generate_sections` touches, with the writes captured."""
    state = {"written": {}, "sections": [], "reuse": set()}
    db = proposal_routes.db

    monkeypatch.setattr(db, "get_proposal_by_tender", lambda t, w: {"id": "p-1"})
    monkeypatch.setattr(db, "get_tender", lambda t, w: {"id": t, "title": "Rope supply"})
    monkeypatch.setattr(db, "get_criteria", lambda t, w: [])
    monkeypatch.setattr(db, "get_responses", lambda p, w: [])
    monkeypatch.setattr(db, "get_valid_library_docs", lambda w, d: [])
    monkeypatch.setattr(db, "get_profile_context", lambda w: {"legal_identity": {}})
    monkeypatch.setattr(db, "get_style_profile", lambda w: None)
    monkeypatch.setattr(db, "get_sections", lambda p, w: state["sections"])
    monkeypatch.setattr(db, "get_reuse_targets", lambda w, p: state["reuse"])
    monkeypatch.setattr(db, "upsert_section",
                        lambda w, p, key, row: state["written"].__setitem__(key, row))
    monkeypatch.setattr(spec_service, "assess_schedule", lambda w, t, tender=None: {"lines": []})
    monkeypatch.setattr(proposal_routes, "draft_section", _draft)
    return state


def test_a_section_a_human_edited_is_not_regenerated(wired):
    wired["sections"] = [{"key": "solution", "edited_by": "u-1", "body_md": "my own words"}]

    out = proposal_routes.do_generate_sections("ws-1", "t-1")

    assert "solution" not in wired["written"], "a human's rewrite was overwritten"
    assert "solution" in out["kept"]
    assert len(wired["written"]) == len(SECTION_SPECS) - 1


def test_regenerating_a_section_voids_its_approval_in_the_same_write(wired):
    """The upsert MERGES, so a field left out keeps its old value. Approval of prose that no
    longer exists is the defect; it must be nulled explicitly, not just left unset."""
    wired["sections"] = [{"key": "solution", "approved_by": "u-9",
                          "approved_at": "2026-09-01T00:00:00Z"}]

    proposal_routes.do_generate_sections("ws-1", "t-1")

    for key, row in wired["written"].items():
        assert row["approved_at"] is None, f"{key} kept an approval across a rewrite"
        assert row["approved_by"] is None


def test_a_section_with_an_accepted_prior_answer_is_left_alone(wired):
    """The acceptance receipt (G-AC6) is the record that no suggestion entered a draft
    unaccepted. Overwriting the text leaves the receipt pointing at prose nobody accepted."""
    wired["reuse"] = {"section:approach_methodology"}

    out = proposal_routes.do_generate_sections("ws-1", "t-1")

    assert "approach_methodology" not in wired["written"]
    assert out["kept"] == ["approach_methodology"]


def test_an_untouched_document_is_still_fully_regenerated(wired):
    """The guard must not be so broad that Regenerate stops working — the failure mode on
    the other side, and the one a test asserting only 'nothing was overwritten' would miss."""
    out = proposal_routes.do_generate_sections("ws-1", "t-1")

    assert out["kept"] == []
    assert set(wired["written"]) == {s.key for s in SECTION_SPECS}
    assert all(wired["written"][k]["body_md"] == f"fresh {k}" for k in NARRATIVE_KEYS)


def test_a_criterion_with_an_accepted_prior_answer_survives_re_match(monkeypatch):
    """`/prepare` runs do_generate on every Re-match. Without the skip, one gap fixed on the
    readiness screen silently reverted every reused answer in the proposal."""
    db = proposal_routes.db
    written: list[str] = []
    monkeypatch.setattr(db, "get_criteria", lambda t, w: [
        {"id": "c-1", "verbatim_text": "Turnover", "requirement_level": "mandatory"},
        {"id": "c-2", "verbatim_text": "ISO 9001", "requirement_level": "mandatory"},
    ])
    monkeypatch.setattr(db, "get_valid_library_docs", lambda w, d: [])
    monkeypatch.setattr(db, "get_readiness_decisions", lambda t, w: [])
    monkeypatch.setattr(db, "create_proposal", lambda w, t: {"id": "p-1"})
    monkeypatch.setattr(db, "get_reuse_targets", lambda w, p: {"criterion:c-2"})
    monkeypatch.setattr(db, "upsert_response",
                        lambda w, p, cid, resp: written.append(cid))
    monkeypatch.setattr(proposal_routes, "draft_response", lambda text, ev: SimpleNamespace(
        draft_text="x", sentences=[], draft_status="drafted", flags=[]))

    out = proposal_routes.do_generate("ws-1", "t-1")

    assert written == ["c-1"]
    assert out["kept_reused"] == 1
