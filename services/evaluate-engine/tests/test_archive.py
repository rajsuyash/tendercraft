"""Archiving — the only removal this product has, and until now the only one with no route.

`db.tenders()` has filtered `state != 'archived'` since 0001 and nothing could set that value,
so an abandoned tender sat on the officer's board forever. The demo's own dashboard had one and
it had to be cleared with hand-written SQL against production.

It is deliberately not a delete, and these tests pin the properties that make it defensible:
a reason is required, both directions are audited, and only an officer or chair may do it.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from evaluate import db
from evaluate.auth import AuthedUser, get_current_user
from evaluate.main import create_app

AUTH = "a0000000-0000-4000-8000-00000000000a"
TENDER = "e0000000-0000-4000-8000-00000000000a"


def _client(role: str, *, state: str, monkeypatch):
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: AuthedUser(
        user_id="u1", authority_id=AUTH, role=role)
    monkeypatch.setattr(db, "tender", lambda *a, **k: {"id": TENDER, "state": state})
    patches: list[dict] = []
    audits: list[tuple] = []
    monkeypatch.setattr(db, "update_tender", lambda t, a, patch: patches.append(patch))
    monkeypatch.setattr(db, "audit",
                        lambda a, t, u, action, *rest, **k: audits.append((action, rest)))
    c = TestClient(app, raise_server_exceptions=False)
    c.patches, c.audits = patches, audits  # type: ignore[attr-defined]
    return c


def test_an_officer_can_archive_with_a_reason(monkeypatch):
    c = _client("officer", state="active", monkeypatch=monkeypatch)
    r = c.post(f"/api/tenders/{TENDER}/archive",
               json={"archived": True, "reason": "Cancelled before bid opening"})
    assert r.status_code == 200, r.text
    assert r.json()["data"] == {"state": "archived", "changed": True}
    assert c.patches == [{"state": "archived"}]           # type: ignore[attr-defined]
    assert c.audits[0][0] == "tender_archived"            # type: ignore[attr-defined]


def test_archiving_without_a_reason_is_refused(monkeypatch):
    """Removing a live procurement from the board is a decision someone should have to justify.
    An audit row reading only "archived" explains nothing to whoever reads it a year later."""
    c = _client("officer", state="active", monkeypatch=monkeypatch)
    r = c.post(f"/api/tenders/{TENDER}/archive", json={"archived": True, "reason": "   "})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "REASON_REQUIRED"
    assert c.patches == []                                # type: ignore[attr-defined]
    assert c.audits == []                                 # type: ignore[attr-defined]


def test_restoring_needs_no_reason_but_is_still_audited(monkeypatch):
    """A tender that quietly reappears is as hard to explain as one that quietly vanished."""
    c = _client("officer", state="archived", monkeypatch=monkeypatch)
    r = c.post(f"/api/tenders/{TENDER}/archive", json={"archived": False})
    assert r.status_code == 200
    assert c.patches == [{"state": "active"}]             # type: ignore[attr-defined]
    assert c.audits[0][0] == "tender_restored"            # type: ignore[attr-defined]


def test_archiving_an_already_archived_tender_writes_nothing(monkeypatch):
    """Idempotent, and it does not pad the audit trail with rows saying nothing happened."""
    c = _client("officer", state="archived", monkeypatch=monkeypatch)
    r = c.post(f"/api/tenders/{TENDER}/archive", json={"archived": True, "reason": "again"})
    assert r.status_code == 200
    assert r.json()["data"]["changed"] is False
    assert c.patches == [] and c.audits == []             # type: ignore[attr-defined]


@pytest.mark.parametrize("role,code", [("member", "NOT_OFFICER"), ("auditor", "READ_ONLY_ROLE")])
def test_only_an_officer_or_chair_may_archive(role, code, monkeypatch):
    c = _client(role, state="active", monkeypatch=monkeypatch)
    r = c.post(f"/api/tenders/{TENDER}/archive", json={"archived": True, "reason": "x"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == code
    assert c.patches == []                                # type: ignore[attr-defined]


def test_a_tender_in_another_authority_cannot_be_archived(monkeypatch):
    """Scoped like every other write. 404, not 403 — 403 would confirm it exists."""
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: AuthedUser(
        user_id="u1", authority_id=AUTH, role="officer")
    monkeypatch.setattr(db, "tender", lambda *a, **k: None)
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.post(f"/api/tenders/{TENDER}/archive", json={"archived": True, "reason": "x"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "TENDER_NOT_FOUND"
