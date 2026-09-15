"""PATCH /api/tenders/{id} — what a human may correct about a tender.

The name, for one stuck at the 'Untitled tender' fallback
(deterministic/tender_meta.display_title). And the deadline, for one whose document states
a date the parser cannot read — or which was uploaded before the parser existed, which is
every tender in the product today and cannot be backfilled, because nothing persists page
text after ingest.

Follows update_project's shape: 404-before-write ownership check, no audit row (its
neighbour in this file doesn't add one either).
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
        user_id="u1", workspace_id="w1", role="admin",
    )
    return TestClient(app)


def test_rename_rejects_tender_not_in_workspace(client, monkeypatch):
    monkeypatch.setattr(db, "get_tender", lambda t, w: None)
    calls: list = []
    monkeypatch.setattr(db, "update_tender", lambda *a, **k: calls.append(a))
    r = client.patch("/api/tenders/tX", json={"title": "GEM/2026/B/1234 — Wire Rope"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "TENDER_NOT_FOUND"
    assert calls == []  # no write on the rejected path


def test_rename_rejects_empty_title(client, monkeypatch):
    monkeypatch.setattr(db, "get_tender", lambda t, w: {"id": "tX"})
    calls: list = []
    monkeypatch.setattr(db, "update_tender", lambda *a, **k: calls.append(a))
    r = client.patch("/api/tenders/tX", json={"title": ""})
    assert r.status_code in (400, 422)
    assert calls == []


def test_rename_rejects_whitespace_only_title(client, monkeypatch):
    monkeypatch.setattr(db, "get_tender", lambda t, w: {"id": "tX"})
    calls: list = []
    monkeypatch.setattr(db, "update_tender", lambda *a, **k: calls.append(a))
    r = client.patch("/api/tenders/tX", json={"title": "   "})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "TITLE_REQUIRED"
    assert calls == []


def test_rename_rejects_title_over_length_cap(client, monkeypatch):
    monkeypatch.setattr(db, "get_tender", lambda t, w: {"id": "tX"})
    r = client.patch("/api/tenders/tX", json={"title": "x" * 301})
    assert r.status_code == 422


def test_rename_strips_and_writes(client, monkeypatch):
    monkeypatch.setattr(db, "get_tender", lambda t, w: {"id": "tX"})
    calls: list = []
    monkeypatch.setattr(
        db, "update_tender",
        lambda tender_id, workspace_id, patch: calls.append((tender_id, workspace_id, patch)),
    )
    r = client.patch("/api/tenders/tX", json={"title": "  GEM/2026/B/1234  "})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["data"]["title"] == "GEM/2026/B/1234"
    assert calls == [("tX", "w1", {"title": "GEM/2026/B/1234"})]


# --- the deadline a document never stated -------------------------------------------------


def test_a_deadline_can_be_set_with_its_offset_preserved(client, monkeypatch):
    """Indian submission deadlines are IST-sensitive: 15:00 IST is not 15:00 UTC, and a
    missed one is a lost bid. The offset the caller sends is what gets stored."""
    monkeypatch.setattr(db, "get_tender", lambda t, w: {"id": "tX"})
    calls: list = []
    monkeypatch.setattr(db, "update_tender",
                        lambda t, w, patch: calls.append(patch))
    r = client.patch("/api/tenders/tX", json={"deadline": "2026-10-02T15:00:00+05:30"})
    assert r.status_code == 200
    assert calls == [{"deadline": "2026-10-02T15:00:00+05:30"}]


def test_a_deadline_can_be_cleared(client, monkeypatch):
    """An explicit null must reach the column. A `if v is not None` filter would strip the
    one payload that means "unset this" and answer 422 — the pitfall this repo already paid
    for on PATCH /api/opportunities/{id}."""
    monkeypatch.setattr(db, "get_tender", lambda t, w: {"id": "tX"})
    calls: list = []
    monkeypatch.setattr(db, "update_tender", lambda t, w, patch: calls.append(patch))
    r = client.patch("/api/tenders/tX", json={"deadline": None})
    assert r.status_code == 200
    assert calls == [{"deadline": None}]


def test_omitting_a_field_does_not_write_it(client, monkeypatch):
    """Setting a deadline must not blank the title, and vice versa — the upsert-pads-with-
    None defect, in its PATCH form."""
    monkeypatch.setattr(db, "get_tender", lambda t, w: {"id": "tX"})
    calls: list = []
    monkeypatch.setattr(db, "update_tender", lambda t, w, patch: calls.append(patch))
    client.patch("/api/tenders/tX", json={"deadline": "2026-10-02T15:00:00+05:30"})
    assert "title" not in calls[0]


def test_an_empty_patch_is_refused(client, monkeypatch):
    monkeypatch.setattr(db, "get_tender", lambda t, w: {"id": "tX"})
    calls: list = []
    monkeypatch.setattr(db, "update_tender", lambda t, w, patch: calls.append(patch))
    r = client.patch("/api/tenders/tX", json={})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "NOTHING_TO_UPDATE"
    assert calls == []
