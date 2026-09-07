"""Pursuits (0039) — the link between a found opportunity and the bid against it.

The engine writes with the service role, which bypasses RLS, so every assertion here is about
the scope column appearing in the key and in the filter. RLS is the second line; these tests
pin the first. Cross-workspace behaviour against real policies lives in
tests/isolation/test_pursuit_isolation.py.
"""

from app import db


def test_create_pursuit_scopes_the_conflict_target(monkeypatch):
    """A conflict target omitting workspace_id can reassign another workspace's row (0027)."""
    captured: dict = {}

    def _fake_rest(method, table, params=None, json=None, headers=None):
        captured.update({"method": method, "table": table,
                         "params": params or {}, "json": json, "headers": headers or {}})
        return [{"id": "p-1", "workspace_id": "ws-1", "opportunity_id": "o-1",
                 "tender_id": None, "state": "pursuing"}]

    monkeypatch.setattr(db, "_rest", _fake_rest)
    row = db.create_pursuit("ws-1", "o-1", "user-1")

    assert row["id"] == "p-1"
    assert captured["method"] == "POST"
    assert captured["table"] == "pursuits"
    assert captured["params"]["on_conflict"] == "workspace_id,opportunity_id"
    assert captured["json"]["workspace_id"] == "ws-1"
    assert captured["json"]["opportunity_id"] == "o-1"
    assert captured["json"]["created_by"] == "user-1"


def test_create_pursuit_merges_rather_than_erroring(monkeypatch):
    """Idempotency is the unique key plus this Prefer header, not a read-then-write race."""
    captured: dict = {}
    monkeypatch.setattr(
        db, "_rest",
        lambda m, t, params=None, json=None, headers=None: (
            captured.update({"headers": headers or {}}) or [{"id": "p-1"}]
        ),
    )
    db.create_pursuit("ws-1", "o-1", "user-1")
    assert "merge-duplicates" in captured["headers"].get("Prefer", "")


def test_create_pursuit_returns_empty_when_the_write_returns_nothing(monkeypatch):
    """PostgREST can answer with no representation; the caller must not IndexError."""
    monkeypatch.setattr(db, "_rest",
                        lambda m, t, params=None, json=None, headers=None: [])
    assert db.create_pursuit("ws-1", "o-1", "user-1") == {}


def test_link_tender_filters_on_workspace(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        db, "_rest",
        lambda m, t, params=None, json=None, headers=None: (
            captured.update({"method": m, "params": params or {}, "json": json})
            or [{"id": "p-1", "tender_id": "t-9", "state": "ingested"}]
        ),
    )
    db.link_pursuit_tender("ws-1", "p-1", "t-9")

    assert captured["method"] == "PATCH"
    assert captured["params"]["workspace_id"] == "eq.ws-1"
    assert captured["params"]["id"] == "eq.p-1"
    assert captured["json"]["tender_id"] == "t-9"
    # The state and the tender move together, or `pursuits_ingested_has_a_tender` is a lie
    # that happens to be satisfied.
    assert captured["json"]["state"] == "ingested"


def test_get_pursuit_is_workspace_scoped(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        db, "_rest",
        lambda m, t, params=None, json=None, headers=None: (
            captured.update({"params": params or {}}) or []
        ),
    )
    assert db.get_pursuit("ws-1", "p-1") is None
    assert captured["params"]["workspace_id"] == "eq.ws-1"
    assert captured["params"]["id"] == "eq.p-1"


def test_get_pursuit_embeds_the_opportunity(monkeypatch):
    """The caller needs the portal reference and authority in the same round trip — the whole
    point is not making the user re-type them."""
    captured: dict = {}
    monkeypatch.setattr(
        db, "_rest",
        lambda m, t, params=None, json=None, headers=None: (
            captured.update({"params": params or {}})
            or [{"id": "p-1", "opportunities": {"portal_ref_no": "GEM/2026/B/1"}}]
        ),
    )
    row = db.get_pursuit("ws-1", "p-1")
    assert "opportunities(" in captured["params"]["select"]
    assert row["opportunities"]["portal_ref_no"] == "GEM/2026/B/1"


def test_get_match_is_scoped_by_workspace_not_by_watched_markets(monkeypatch):
    """Market scope is a DISPLAY preference (see `_market_scope`); it must not decide what a
    workspace may act on. Un-ticking a country hides rows and deliberately keeps their state —
    it should not also make a tender the workspace already claimed unreachable."""
    captured: dict = {}
    monkeypatch.setattr(
        db, "_rest",
        lambda m, t, params=None, json=None, headers=None: (
            captured.update({"params": params or {}}) or []
        ),
    )
    assert db.get_match("ws-1", "o-1") is None
    assert captured["params"]["workspace_id"] == "eq.ws-1"
    assert captured["params"]["opportunity_id"] == "eq.o-1"
    assert not any(k.startswith("opportunities.") for k in captured["params"])


# ---------- the endpoint ----------
#
# TestClient + dependency_overrides, matching tests/test_clarification_routes.py: it exercises
# the real route, the real auth dependency and the real envelope, none of which a direct call
# to the handler would touch.

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.auth import AuthedUser, get_current_user  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture
def client():
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: AuthedUser(
        user_id="u1", workspace_id="t1", role="admin",
    )
    return TestClient(app)


@pytest.fixture
def reader_client():
    """A member who may read but not draft."""
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: AuthedUser(
        user_id="u2", workspace_id="t1", role="compliance_checker",
    )
    return TestClient(app)


def test_pursue_refuses_an_opportunity_not_in_this_workspaces_feed(client, monkeypatch):
    """The corpus is shared and its ids are guessable, so a bare workspace check is not
    enough — the match row is what makes an opportunity this workspace's to act on. 404 not
    403: a distinguishable 403 confirms the row exists in someone else's feed."""
    monkeypatch.setattr(db, "get_match", lambda ws, oid: None)

    r = client.post("/api/opportunities/o-unknown/pursue")

    assert r.status_code == 404
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "NOT_FOUND"


def test_pursue_is_idempotent(client, monkeypatch):
    """A double-click is one pursuit — the unique key does it, this asserts it."""
    monkeypatch.setattr(db, "get_match", lambda ws, oid: {"opportunity_id": oid})
    monkeypatch.setattr(
        db, "create_pursuit",
        lambda ws, oid, uid: {"id": "p-1", "opportunity_id": oid, "state": "pursuing"},
    )

    first = client.post("/api/opportunities/o-1/pursue").json()
    second = client.post("/api/opportunities/o-1/pursue").json()

    assert first["ok"] is True
    assert first["data"]["id"] == second["data"]["id"] == "p-1"


def test_pursue_passes_the_caller_not_a_body_supplied_id(client, monkeypatch):
    """Tenant and actor come from the verified JWT, never the request (ET-6)."""
    seen: dict = {}
    monkeypatch.setattr(db, "get_match", lambda ws, oid: {"opportunity_id": oid})
    monkeypatch.setattr(
        db, "create_pursuit",
        lambda ws, oid, uid: seen.update({"ws": ws, "oid": oid, "uid": uid}) or {"id": "p-1"},
    )

    client.post("/api/opportunities/o-1/pursue")

    assert seen == {"ws": "t1", "oid": "o-1", "uid": "u1"}


def test_pursue_refuses_a_member_who_cannot_draft(reader_client, monkeypatch):
    """Claiming a tender is a write."""
    monkeypatch.setattr(db, "get_match", lambda ws, oid: {"opportunity_id": oid})
    monkeypatch.setattr(db, "create_pursuit", lambda ws, oid, uid: {"id": "p-1"})

    r = reader_client.post("/api/opportunities/o-1/pursue")

    assert r.status_code == 403
