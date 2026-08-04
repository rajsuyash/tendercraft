"""The reuse endpoints: ownership guards, the acceptance gate (G-AC6), re-validation.

The gate this file exists to pin: a suggested answer may NEVER reach a draft without an
explicit accept. GET /suggestions must therefore write nothing at all, and POST /reuse must
record a usage row every time it does write.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import db, reuse_routes
from app.auth import AuthedUser, get_current_user
from app.main import create_app

_ANSWER_TEXT = (
    "Our quality management system is certified to ISO 9001:2015 and audited annually. "
    "The programme manager reports to the department every week."
)


@pytest.fixture
def client():
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: AuthedUser(
        user_id="u1", workspace_id="t1", role="admin",
    )
    return TestClient(app)


@pytest.fixture
def corpus(monkeypatch):
    """One mined answer, one live library document, nothing expired."""
    monkeypatch.setattr(db, "get_answers_with_bids", lambda ws: [{
        "id": "a1", "requirement_text": "quality management certification",
        "answer_text": _ANSWER_TEXT, "section_key": None,
        "bid_name": "NIC 2025 bid", "authority": "NIC",
        "submitted_on": "2025-04-01", "outcome": "won",
    }])
    monkeypatch.setattr(db, "get_valid_library_docs", lambda ws, today: [
        {"id": "d1", "name": "ISO 9001:2015 Certificate",
         "text_content": "Quality management system certified to ISO 9001:2015, audited annually."},
    ])
    monkeypatch.setattr(db, "get_expired_library_docs", lambda ws, today: [])


def test_suggestions_return_provenance_and_write_nothing(client, monkeypatch, corpus):
    monkeypatch.setattr(db, "get_criterion_in_tender", lambda c, t, ws: {
        "id": "c1", "verbatim_text": "quality management certification",
    })
    writes: list = []
    monkeypatch.setattr(db, "record_answer_usage", lambda *a, **k: writes.append(1))
    monkeypatch.setattr(db, "upsert_response", lambda *a, **k: writes.append(1))
    monkeypatch.setattr(db, "append_reused_section_text", lambda *a, **k: writes.append(1))

    r = client.get("/api/tenders/t1/criteria/c1/suggestions")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["suggestions"][0]["provenance"] == {
        "bid": "NIC 2025 bid", "authority": "NIC",
        "submitted_on": "2025-04-01", "outcome": "won",
    }
    # G-AC6: looking at a suggestion is not accepting it.
    assert writes == []


def test_a_suggestion_carries_its_flags_before_acceptance(client, monkeypatch, corpus):
    # The certificate that backed this claim has lapsed — the user must see that BEFORE
    # they accept, not discover it at the export gate.
    monkeypatch.setattr(db, "get_expired_library_docs", lambda ws, today: [
        {"id": "d9", "name": "ISO 9001:2015 Certificate", "valid_to": "2026-03-14"},
    ])
    monkeypatch.setattr(db, "get_criterion_in_tender", lambda c, t, ws: {
        "id": "c1", "verbatim_text": "quality management certification",
    })
    stale = client.get("/api/tenders/t1/criteria/c1/suggestions").json()["data"]
    assert stale["suggestions"][0]["stale_claims"][0]["expired_on"] == "2026-03-14"


def test_accepting_writes_the_draft_and_the_receipt(client, monkeypatch, corpus):
    monkeypatch.setattr(db, "get_proposal", lambda p, ws: {"id": "p1", "tender_id": "t1"})
    monkeypatch.setattr(db, "get_answer", lambda a, ws: {"id": "a1", "answer_text": _ANSWER_TEXT})
    monkeypatch.setattr(db, "get_criterion_in_tender", lambda c, t, ws: {"id": "c1"})
    written: dict = {}
    monkeypatch.setattr(db, "upsert_response",
                        lambda ws, p, c, resp: written.update(resp))
    def _usage(*a, **k):
        written["usage"] = True
        return {"id": "u9"}

    monkeypatch.setattr(db, "record_answer_usage", _usage)
    monkeypatch.setattr(db, "write_audit", lambda *a, **k: written.setdefault("audit", True))

    r = client.post("/api/proposals/p1/reuse", json={
        "answer_id": "a1", "target_kind": "criterion", "target": "c1",
    })
    assert r.status_code == 200
    assert written["draft_text"] == _ANSWER_TEXT
    assert written["usage"] and written["audit"]  # the receipt, every time


def test_reuse_rejects_a_criterion_from_another_tender(client, monkeypatch, corpus):
    # The engine bypasses RLS: a foreign criterion id must be refused in code, before any write.
    monkeypatch.setattr(db, "get_proposal", lambda p, ws: {"id": "p1", "tender_id": "t1"})
    monkeypatch.setattr(db, "get_answer", lambda a, ws: {"id": "a1", "answer_text": _ANSWER_TEXT})
    monkeypatch.setattr(db, "get_criterion_in_tender", lambda c, t, ws: None)
    writes: list = []
    monkeypatch.setattr(db, "upsert_response", lambda *a, **k: writes.append(1))
    monkeypatch.setattr(db, "record_answer_usage", lambda *a, **k: writes.append(1))

    r = client.post("/api/proposals/p1/reuse", json={
        "answer_id": "a1", "target_kind": "criterion", "target": "cFOREIGN",
    })
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "CRITERION_NOT_FOUND"
    assert writes == []


def test_reuse_rejects_an_answer_from_another_workspace(client, monkeypatch, corpus):
    monkeypatch.setattr(db, "get_proposal", lambda p, ws: {"id": "p1", "tender_id": "t1"})
    monkeypatch.setattr(db, "get_answer", lambda a, ws: None)
    writes: list = []
    monkeypatch.setattr(db, "record_answer_usage", lambda *a, **k: writes.append(1))
    r = client.post("/api/proposals/p1/reuse", json={
        "answer_id": "aFOREIGN", "target_kind": "criterion", "target": "c1",
    })
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "ANSWER_NOT_FOUND"
    assert writes == []


def test_a_money_sentence_in_a_prior_answer_is_hard_flagged(monkeypatch):
    # B-AC4 is non-overridable and applies to reused text exactly as to generated text: a
    # copied "₹8.2 Cr" is an authored figure unless it transcludes from structured data.
    chunks = [{"id": "d1#0", "name": "turnover", "text": "annual turnover statement"}]
    result = reuse_routes._revalidate(
        "Our average annual turnover is ₹8.2 Cr over the last three years.",
        chunks, reuse_routes.SectionKind.COMPLIANCE,
    )
    assert [f["reason"] for f in result["flags"]] == ["uncited_financial"]
    assert result["status"] == "unverified"


def test_a_reused_claim_with_no_supporting_document_today_is_unverified(monkeypatch):
    result = reuse_routes._revalidate(
        "We hold ISO 9001:2015 certification.", [], reuse_routes.SectionKind.COMPLIANCE,
    )
    assert [f["reason"] for f in result["flags"]] == ["unverified"]


def test_the_ownership_guard_returns_the_text_the_suggestion_needs():
    """Regression: the route read criterion["verbatim_text"], which the guard did not select.

    Every unit test passed because they stubbed the guard with a field the real query never
    returned; a live end-to-end run 500'd on the first call. A stub that returns more than the
    real function does is not a test, so this one asserts the QUERY, not the stub.
    """
    import inspect

    src = inspect.getsource(db.get_criterion_in_tender)
    assert "verbatim_text" in src, "the reuse suggestion path reads this field from the guard"


def test_a_criterion_with_no_text_yields_no_suggestions_rather_than_a_500(client, monkeypatch,
                                                                         corpus):
    monkeypatch.setattr(db, "get_criterion_in_tender", lambda c, t, ws: {"id": "c1"})
    r = client.get("/api/tenders/t1/criteria/c1/suggestions")
    assert r.status_code == 200
    assert r.json()["data"]["suggestions"] == []
