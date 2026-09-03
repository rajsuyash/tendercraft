"""Pre-bid clarification endpoints — UML ask 2.

The stubs here mirror the real queries' SELECT lists on purpose. A stub returning more than the
query does is not a test: nine green tests once passed against a `get_criterion_in_tender` stub
carrying a column the real query never selected, and the first live call 500'd
(docs/known-pitfalls.md).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth import AuthedUser, get_current_user
from app.main import create_app


@pytest.fixture
def client():
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: AuthedUser(
        user_id="u1", workspace_id="t1", role="admin",
    )
    return TestClient(app)


def _line(**over):
    """One `tender_line_items` row in the shape `db.get_line_items` actually selects."""
    row = {
        "id": "l1", "schedule_ref": "Schedule-A", "item_ref": "14",
        "description": "Steel wire rope 20 mm IS 2266", "quantity": 100, "uom": "m",
        "anchor_document": "BOQ.xlsx", "anchor_page": None, "anchor_row": 14,
        "source_criterion_id": None, "confirmed": True,
        "spec_parameters": [
            {"param_key": "diameter", "kind": "numeric", "unit": "mm",
             "num_min": 20, "num_max": 20, "allowed_values": [], "raw_text": "20 mm"},
        ],
    }
    row.update(over)
    return row


def _envelope(low: float, high: float):
    """A capability the bidder recorded, in `db.get_capability_specs`' shape."""
    return [{
        "id": "s1", "spec_kind": "envelope", "label": "Rope line", "standard_ref": None,
        "parent_envelope_id": None, "gem_catalogue_id": None, "updated_at": None,
        "spec_parameters": [
            {"param_key": "diameter", "kind": "numeric", "unit": "mm",
             "num_min": low, "num_max": high, "allowed_values": [], "raw_text": ""},
        ],
    }]


@pytest.fixture
def stub(monkeypatch):
    state: dict = {"stored": [], "upserted": None, "deleted_keep": None, "patched": None,
                   "audit": []}
    monkeypatch.setattr(db, "get_tender", lambda t, w: {"id": t} if t == "tender-1" else None)
    monkeypatch.setattr(db, "get_line_items", lambda t, w: [_line()])
    # 20 mm required against a 24–60 mm plant: a provable deviation.
    monkeypatch.setattr(db, "get_capability_specs", lambda w: _envelope(24, 60))
    monkeypatch.setattr(db, "get_clarifications", lambda t, w: state["stored"])
    monkeypatch.setattr(
        db, "upsert_clarification_drafts",
        lambda w, t, rows: state.__setitem__("upserted", rows),
    )
    monkeypatch.setattr(
        db, "delete_stale_clarification_drafts",
        lambda w, t, keep: state.__setitem__("deleted_keep", keep),
    )
    monkeypatch.setattr(db, "write_audit", lambda *a, **k: state["audit"].append((a, k)))
    return state


# ── GET ──────────────────────────────────────────────────────────────────────────────

def test_a_deviating_schedule_raises_a_question(client, stub):
    body = client.get("/api/tenders/tender-1/clarifications").json()

    assert body["ok"] is True
    items = body["data"]["clarifications"]
    assert len(items) == 1
    assert items[0]["param_key"] == "diameter"
    assert items[0]["kind"] == "relaxation"
    assert items[0]["status"] == "draft"
    assert items[0]["id"] is None
    assert body["data"]["summary"]["open"] == 1


def test_the_query_text_never_carries_the_bidders_capability(client, stub):
    """GeM publishes a buyer's clarification answers to every bidder on the tender."""
    item = client.get("/api/tenders/tender-1/clarifications").json()["data"]["clarifications"][0]

    assert "24" not in item["text"] and "60" not in item["text"]
    assert "24" in item["rationale"] or "60" in item["rationale"]


def test_a_supplied_schedule_raises_nothing(client, stub, monkeypatch):
    monkeypatch.setattr(db, "get_capability_specs", lambda w: _envelope(6, 60))

    body = client.get("/api/tenders/tender-1/clarifications").json()

    assert body["data"]["clarifications"] == []
    assert body["data"]["summary"]["total"] == 0


def test_the_screen_states_who_posts(client, stub):
    """We never post to GeM (G-1). Every surface must say the bidder does."""
    assert client.get("/api/tenders/tender-1/clarifications").json()["data"]["posting"] == "by_you"


def test_a_foreign_tender_is_not_found(client, stub):
    r = client.get("/api/tenders/someone-elses/clarifications")

    assert r.status_code == 404
    assert r.json()["error"]["code"] == "TENDER_NOT_FOUND"


def test_a_sent_question_keeps_the_text_that_was_actually_sent(client, stub):
    """The derived text may have moved since; showing the new one misreports what was asked."""
    stub["stored"] = [{
        "id": "c1", "param_key": "diameter", "kind": "relaxation",
        "query_text": "the exact words that went to the buyer", "required_display": "20 mm",
        "rationale": "", "line_ids": ["l1"], "status": "sent", "sent_at": "2026-09-01T00:00:00Z",
        "answered_at": None, "answer_text": None, "answer_source": None,
        "created_at": None, "updated_at": None,
    }]

    item = client.get("/api/tenders/tender-1/clarifications").json()["data"]["clarifications"][0]

    assert item["text"] == "the exact words that went to the buyer"
    assert item["status"] == "sent"
    assert item["id"] == "c1"


def test_a_sent_question_the_schedule_no_longer_raises_is_kept_and_flagged(
    client, stub, monkeypatch
):
    """It was asked. Quietly erasing a question put to a public buyer would rewrite the record."""
    monkeypatch.setattr(db, "get_capability_specs", lambda w: _envelope(6, 60))
    stub["stored"] = [{
        "id": "c1", "param_key": "diameter", "kind": "relaxation",
        "query_text": "asked before the corrigendum", "required_display": "20 mm",
        "rationale": "", "line_ids": [], "status": "sent", "sent_at": "2026-09-01T00:00:00Z",
        "answered_at": None, "answer_text": None, "answer_source": None,
        "created_at": None, "updated_at": None,
    }]

    items = client.get("/api/tenders/tender-1/clarifications").json()["data"]["clarifications"]

    assert len(items) == 1
    assert items[0]["stale"] is True


def test_a_draft_the_schedule_no_longer_raises_disappears(client, stub, monkeypatch):
    monkeypatch.setattr(db, "get_capability_specs", lambda w: _envelope(6, 60))
    stub["stored"] = [{
        "id": "c1", "param_key": "diameter", "kind": "relaxation", "query_text": "never asked",
        "required_display": "20 mm", "rationale": "", "line_ids": [], "status": "draft",
        "sent_at": None, "answered_at": None, "answer_text": None, "answer_source": None,
        "created_at": None, "updated_at": None,
    }]

    assert client.get(
        "/api/tenders/tender-1/clarifications"
    ).json()["data"]["clarifications"] == []


# ── POST (save) ──────────────────────────────────────────────────────────────────────

def test_saving_stores_the_pack_and_keeps_only_live_drafts(client, stub):
    r = client.post("/api/tenders/tender-1/clarifications")

    assert r.status_code == 200
    assert r.json()["data"]["saved"] == 1
    assert stub["upserted"][0]["param_key"] == "diameter"
    assert stub["upserted"][0]["line_ids"] == ["l1"]
    assert stub["upserted"][0]["created_by"] == "u1"
    assert stub["deleted_keep"] == ["diameter"]


def test_saving_a_foreign_tender_is_not_found(client, stub):
    assert client.post("/api/tenders/someone-elses/clarifications").status_code == 404


# ── PATCH ────────────────────────────────────────────────────────────────────────────

def _stored(status="draft", **over):
    row = {"id": "c1", "tender_id": "tender-1", "param_key": "diameter", "status": status,
           "query_text": "q", "answer_text": None, "sent_at": None}
    row.update(over)
    return row


def test_marking_sent_stamps_the_time_and_audits(client, stub, monkeypatch):
    monkeypatch.setattr(db, "get_clarification", lambda c, w: _stored())
    captured: dict = {}
    monkeypatch.setattr(
        db, "update_clarification",
        lambda c, w, patch: captured.update(patch) or {"status": "sent", **patch},
    )

    r = client.patch("/api/clarifications/c1", json={"status": "sent"})

    assert r.status_code == 200
    assert captured["sent_at"]
    assert stub["audit"], "a clarification changes what the tender requires (E-FR4)"


def test_recording_an_answer_without_the_reply_text_is_refused(client, stub, monkeypatch):
    monkeypatch.setattr(db, "get_clarification", lambda c, w: _stored("sent"))

    r = client.patch("/api/clarifications/c1", json={"status": "answered"})

    assert r.status_code == 400
    assert r.json()["error"]["code"] == "CLARIFICATION_NO_ANSWER"


def test_recording_an_answer_stamps_a_source_and_a_time(client, stub, monkeypatch):
    monkeypatch.setattr(db, "get_clarification", lambda c, w: _stored("sent", sent_at="t0"))
    captured: dict = {}
    monkeypatch.setattr(
        db, "update_clarification",
        lambda c, w, patch: captured.update(patch) or {"status": "answered", **patch},
    )

    r = client.patch(
        "/api/clarifications/c1",
        json={"status": "answered", "answer_text": "Diameter is mandatory."},
    )

    assert r.status_code == 200
    assert captured["answer_source"] == "portal"
    assert captured["answered_at"]


def test_an_answered_question_cannot_return_to_draft(client, stub, monkeypatch):
    """Reopening would put a question the buyer already answered back into the derived pack,
    where the next save would rewrite it."""
    monkeypatch.setattr(db, "get_clarification", lambda c, w: _stored("answered"))

    r = client.patch("/api/clarifications/c1", json={"status": "draft"})

    assert r.status_code == 409
    assert r.json()["error"]["code"] == "CLARIFICATION_NOT_REOPENABLE"


def test_clearing_an_answer_is_reachable(client, stub, monkeypatch):
    """`exclude_unset`, not a None-filter: the one payload meaning 'unset this' must not be
    stripped to {} and refused (docs/known-pitfalls.md)."""
    monkeypatch.setattr(db, "get_clarification", lambda c, w: _stored("sent", answer_text="oops"))
    captured: dict = {}
    monkeypatch.setattr(
        db, "update_clarification",
        lambda c, w, patch: captured.update(patch) or {"status": "sent", **patch},
    )

    r = client.patch("/api/clarifications/c1", json={"answer_text": None})

    assert r.status_code == 200
    assert "answer_text" in captured and captured["answer_text"] is None


def test_an_empty_patch_is_refused(client, stub, monkeypatch):
    monkeypatch.setattr(db, "get_clarification", lambda c, w: _stored())

    r = client.patch("/api/clarifications/c1", json={})

    assert r.status_code == 400
    assert r.json()["error"]["code"] == "CLARIFICATION_EMPTY_PATCH"


def test_a_foreign_clarification_is_not_found(client, stub, monkeypatch):
    monkeypatch.setattr(db, "get_clarification", lambda c, w: None)

    r = client.patch("/api/clarifications/c1", json={"status": "sent"})

    assert r.status_code == 404
    assert r.json()["error"]["code"] == "CLARIFICATION_NOT_FOUND"
