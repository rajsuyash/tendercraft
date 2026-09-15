"""PATCH /api/tenders/{id} — the only way a user can fix a tender stuck at the
'Untitled tender' fallback (deterministic/tender_meta.display_title).

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
    monkeypatch.setattr(db, "set_tender_title", lambda *a, **k: calls.append(a))
    r = client.patch("/api/tenders/tX", json={"title": "GEM/2026/B/1234 — Wire Rope"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "TENDER_NOT_FOUND"
    assert calls == []  # no write on the rejected path


def test_rename_rejects_empty_title(client, monkeypatch):
    monkeypatch.setattr(db, "get_tender", lambda t, w: {"id": "tX"})
    calls: list = []
    monkeypatch.setattr(db, "set_tender_title", lambda *a, **k: calls.append(a))
    r = client.patch("/api/tenders/tX", json={"title": ""})
    assert r.status_code in (400, 422)
    assert calls == []


def test_rename_rejects_whitespace_only_title(client, monkeypatch):
    monkeypatch.setattr(db, "get_tender", lambda t, w: {"id": "tX"})
    calls: list = []
    monkeypatch.setattr(db, "set_tender_title", lambda *a, **k: calls.append(a))
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
        db, "set_tender_title",
        lambda tender_id, workspace_id, title: calls.append((tender_id, workspace_id, title)),
    )
    r = client.patch("/api/tenders/tX", json={"title": "  GEM/2026/B/1234  "})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["data"]["title"] == "GEM/2026/B/1234"
    assert calls == [("tX", "w1", "GEM/2026/B/1234")]
