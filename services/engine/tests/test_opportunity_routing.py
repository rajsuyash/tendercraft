"""Routing a swept tender to a colleague (M12 — `docs/feedback/usha-martin.md` ask 1).

The ask asked for a CRM. The sentence after it — *"circulated to the respective Zonal Heads"* —
asked for routing, which is `assigned_to` and `watched`: two columns that shipped with migration
0019 and had no writer that a person could reach.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth import AuthedUser, get_current_user
from app.main import create_app

OPP = "11111111-1111-1111-1111-111111111111"
COLLEAGUE = "22222222-2222-2222-2222-222222222222"
OUTSIDER = "33333333-3333-3333-3333-333333333333"


def _client(role: str = "admin") -> TestClient:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: AuthedUser(
        user_id="u1", workspace_id="t1", role=role,
    )
    return TestClient(app)


@pytest.fixture
def written(monkeypatch) -> list[dict]:
    """Capture what reaches the database, and who the workspace actually contains."""
    seen: list[dict] = []

    def _flags(workspace_id, opportunity_id, patch):
        seen.append(patch)
        return [{"opportunity_id": opportunity_id, **patch}]

    monkeypatch.setattr(db, "set_match_flags", _flags)
    monkeypatch.setattr(
        db, "get_membership",
        lambda user_id, workspace_id: (
            {"user_id": user_id, "role": "writer"} if user_id == COLLEAGUE else None
        ),
    )
    return seen


def test_assigns_a_tender_to_a_member(written):
    res = _client().patch(f"/api/opportunities/{OPP}", json={"assigned_to": COLLEAGUE})
    assert res.status_code == 200
    assert res.json()["ok"] is True
    assert written == [{"assigned_to": COLLEAGUE}]


def test_unassigning_reaches_the_database(written):
    """The regression this endpoint shipped with: a None filter dropped an explicit null, so
    the only way to clear an assignment returned 422 and wrote nothing."""
    res = _client().patch(f"/api/opportunities/{OPP}", json={"assigned_to": None})
    assert res.status_code == 200
    assert written == [{"assigned_to": None}]


def test_watching_and_unwatching_both_write(written):
    for value in (True, False):
        assert _client().patch(f"/api/opportunities/{OPP}", json={"watched": value}).status_code == 200
    assert written == [{"watched": True}, {"watched": False}]


def test_refuses_a_non_member_assignee(written):
    res = _client().patch(f"/api/opportunities/{OPP}", json={"assigned_to": OUTSIDER})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "NOT_A_MEMBER"
    assert written == []  # nothing written — the row keeps its previous owner


def test_a_viewer_may_not_route(written):
    res = _client(role="viewer").patch(f"/api/opportunities/{OPP}", json={"watched": True})
    assert res.status_code == 403
    assert written == []


def test_an_empty_body_is_refused(written):
    res = _client().patch(f"/api/opportunities/{OPP}", json={})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "EMPTY_PATCH"


def test_a_foreign_opportunity_is_not_found(monkeypatch):
    monkeypatch.setattr(db, "get_membership", lambda u, w: {"role": "writer"})
    monkeypatch.setattr(db, "set_match_flags", lambda *a, **k: [])
    res = _client().patch(f"/api/opportunities/{OPP}", json={"watched": True})
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "NOT_FOUND"
