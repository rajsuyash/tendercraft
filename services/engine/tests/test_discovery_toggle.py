"""The switch that decides which workspaces the scheduled sweep still works for (0047).

Five of the six workspaces the sweep runs for are demo fixtures, and each costs a full corpus
read three times a day — the reads that put this project 12.89 GB into a 5.5 GB egress quota.
So this is a cost control, and every test here is really about the two ways a cost control can
cost more than it saves: turning off a feed nobody asked to turn off, and turning off every
feed at once because one helper query hiccuped.
"""

from __future__ import annotations

import jwt
import pytest
from fastapi.testclient import TestClient

from app import cron_auth, db
from app.auth import AuthedUser, get_current_user
from app.envelope import ApiError
from app.main import create_app

AUDIENCE = "https://engine.test"
CALLER = "scheduler@proj.iam.gserviceaccount.com"


# ---------- the scheduled fan-out ----------

@pytest.fixture
def cron(monkeypatch):
    """A scheduler-authenticated client. HS256 stands in for Google's RS256 — everything this
    boundary decides on is claim checking, which is identical either way."""
    monkeypatch.setenv("CRON_AUDIENCE", AUDIENCE)
    monkeypatch.setenv("CRON_SERVICE_ACCOUNTS", CALLER)
    monkeypatch.setattr(
        cron_auth, "_jwks_client",
        lambda: type("K", (), {"get_signing_key_from_jwt":
                               lambda self, t: type("S", (), {"key": "secret"})()})())
    real = jwt.decode

    def decode(token, key, **kw):
        kw["algorithms"] = ["HS256"]
        return real(token, key, **kw)

    monkeypatch.setattr(jwt, "decode", decode)
    return TestClient(create_app())


def _auth() -> dict:
    token = jwt.encode({"aud": AUDIENCE, "iss": "https://accounts.google.com",
                        "email": CALLER, "email_verified": True, "exp": 9_999_999_999},
                       "secret", algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def swept(monkeypatch):
    """Three member workspaces; record which ones the recompute actually ran for."""
    from app.discovery import ingest

    monkeypatch.setattr(db, "list_workspaces_for_sweep", lambda: [
        {"id": "customer", "name": "Usha Martin", "markets": ["IN"]},
        {"id": "demo-in", "name": "Meridian Infotech", "markets": ["IN"]},
        {"id": "demo-fr", "name": "Groupe Convergence", "markets": ["FR"]},
    ])
    seen: dict = {"markets": None, "recomputed": []}
    monkeypatch.setattr(ingest, "refresh_markets",
                        lambda markets, query="": seen.update(markets=markets)
                        or {"markets": [], "failed": []})
    monkeypatch.setattr(ingest, "refresh_licensed_awards", lambda *a, **k: {"stored": 0})
    monkeypatch.setattr(ingest, "recompute_matches",
                        lambda ws: seen["recomputed"].append(ws) or {"matched": 1})
    return seen


def test_a_workspace_switched_off_is_not_recomputed(cron, swept, monkeypatch):
    """The whole feature: the corpus read a demo fixture costs three times a day, not spent."""
    monkeypatch.setattr(db, "discovery_disabled_workspace_ids",
                        lambda: {"demo-in", "demo-fr"})

    body = cron.post("/internal/cron/sweep", headers=_auth()).json()["data"]

    assert swept["recomputed"] == ["customer"]
    assert body["rematched"] == 1


def test_a_freshly_backfilled_workspace_is_still_swept(cron, swept, monkeypatch):
    """Migration 0047 backfills `true`, so nothing is disabled the moment it lands and every
    workspace must be swept exactly as before. A migration that silently switches feeds off is
    the ET-7 failure arriving through the fix for it."""
    monkeypatch.setattr(db, "discovery_disabled_workspace_ids", set)

    body = cron.post("/internal/cron/sweep", headers=_auth()).json()["data"]

    assert swept["recomputed"] == ["customer", "demo-in", "demo-fr"]
    assert body["rematched"] == 3


def test_a_failed_flag_read_sweeps_every_workspace_and_says_so(cron, swept, monkeypatch, caplog):
    """A set that FILTERS must fail open. An empty set returned for the wrong reason would stop
    every feed in the product at once — worse than the cost this switch was added to save.

    The log line is asserted, not just the behaviour: sweeping everything is also what a
    correctly-empty set does, so without the warning the healthy and the degraded run are
    indistinguishable from outside."""
    monkeypatch.setattr(db, "discovery_disabled_workspace_ids", lambda: None)

    with caplog.at_level("WARNING", logger="app.cron_routes"):
        body = cron.post("/internal/cron/sweep", headers=_auth()).json()["data"]

    assert swept["recomputed"] == ["customer", "demo-in", "demo-fr"]
    assert body["rematched"] == 3
    assert any("discovery_enabled read failed" in r.getMessage() for r in caplog.records)


def test_a_healthy_run_does_not_log_the_fail_open_warning(cron, swept, monkeypatch, caplog):
    """The other half of the previous test. A warning that fires on every run is a warning
    nobody reads — the 1,000-row recompute window logged SATURATED for weeks."""
    monkeypatch.setattr(db, "discovery_disabled_workspace_ids", lambda: {"demo-in"})

    with caplog.at_level("WARNING", logger="app.cron_routes"):
        cron.post("/internal/cron/sweep", headers=_auth())

    assert not any("discovery_enabled read failed" in r.getMessage() for r in caplog.records)


def test_the_shared_corpus_is_still_swept_for_a_disabled_workspaces_market(
        cron, swept, monkeypatch):
    """The toggle buys back the per-workspace recompute and nothing else. Narrowing the markets
    too would mean turning off the last French demo also stops the French corpus, which the
    price screen and the freshness header read."""
    monkeypatch.setattr(db, "discovery_disabled_workspace_ids", lambda: {"demo-fr"})

    cron.post("/internal/cron/sweep", headers=_auth())

    assert swept["markets"] == ["FR", "IN"]


# ---------- the query behind the flag ----------

def test_the_flag_read_asks_only_for_the_disabled(monkeypatch):
    """Asked as "who is disabled?" so absence means enabled: every way this read can come back
    short — the row limit, a workspace created since — lands on sweeping, not skipping."""
    captured: dict = {}
    monkeypatch.setattr(db, "_rest",
                        lambda m, p, **k: captured.update(method=m, path=p, **k) or [])

    assert db.discovery_disabled_workspace_ids() == set()
    assert captured["method"] == "GET"
    assert captured["path"] == "workspaces"
    assert captured["params"]["discovery_enabled"] == "is.false"
    assert captured["params"]["select"] == "id"


def test_a_missing_column_reads_as_none_not_as_nobody_disabled(monkeypatch):
    """Deploying ahead of the migration makes PostgREST 400 on the unknown column. That must
    resolve to "sweep everything", which is what `None` means — an empty set would be the
    engine asserting that nobody turned their feed off."""
    def boom(*a, **k):
        raise ApiError(502, "DB_ERROR", 'column "discovery_enabled" does not exist')

    monkeypatch.setattr(db, "_rest", boom)
    assert db.discovery_disabled_workspace_ids() is None


def test_a_null_body_is_a_failed_read_too(monkeypatch):
    monkeypatch.setattr(db, "_rest", lambda *a, **k: None)
    assert db.discovery_disabled_workspace_ids() is None


def test_a_row_without_an_id_is_dropped_rather_than_disabling_nothing(monkeypatch):
    monkeypatch.setattr(db, "_rest", lambda *a, **k: [{"id": "w1"}, {"id": None}, {}])
    assert db.discovery_disabled_workspace_ids() == {"w1"}


# ---------- the toggle endpoint ----------

def _client(role: str) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: AuthedUser(
        user_id="u1", workspace_id="ws1", role=role,
    )
    return TestClient(app)


@pytest.fixture
def writes(monkeypatch):
    state: dict = {"set": [], "audit": []}
    monkeypatch.setattr(db, "set_workspace_discovery",
                        lambda ws, enabled: state["set"].append((ws, enabled))
                        or {"id": ws, "discovery_enabled": enabled})
    monkeypatch.setattr(db, "write_audit",
                        lambda *a, **k: state["audit"].append((a, k)))
    return state


def test_an_admin_can_switch_the_sweep_off(writes):
    r = _client("admin").put("/api/workspace/discovery", json={"enabled": False})

    assert r.status_code == 200
    assert r.json() == {"ok": True, "data": {"enabled": False}, "error": None}
    assert writes["set"] == [("ws1", False)]


def test_an_admin_can_switch_it_back_on(writes):
    r = _client("admin").put("/api/workspace/discovery", json={"enabled": True})

    assert r.json()["data"] == {"enabled": True}
    assert writes["set"] == [("ws1", True)]


def test_a_viewer_is_refused_with_the_envelope(writes):
    """A viewer is the role defined as "must never touch a draft". Switching a whole
    workspace's feed off is further from a draft than a draft is."""
    r = _client("viewer").put("/api/workspace/discovery", json={"enabled": False})

    assert r.status_code == 403
    assert r.json() == {"ok": False, "data": None, "error": {
        "code": "FORBIDDEN",
        "message": "role 'viewer' may not perform this action (manage:members)",
    }}
    assert writes["set"] == [], "a refused call must not have written"
    assert writes["audit"] == [], "a refused call must not have audited"


def test_a_writer_is_refused_too(writes):
    """Not a drafting act: it changes what arrives for everyone in the workspace."""
    assert _client("writer").put(
        "/api/workspace/discovery", json={"enabled": False}).status_code == 403
    assert writes["set"] == []


def test_the_change_is_audited_with_the_stored_value(writes):
    """"Why did the feed stop?" must have an answer with a name and a timestamp on it — and
    the value the database actually holds, not the one the request sent."""
    _client("admin").put("/api/workspace/discovery", json={"enabled": False})

    (args, kwargs), = writes["audit"]
    assert args[:5] == ("ws1", "u1", "discovery_enabled_changed", "workspace", "ws1")
    assert kwargs["after"] == {"discovery_enabled": False}


def test_the_workspace_comes_from_the_session_never_the_body(writes):
    """ET-6. The endpoint takes no workspace id at all, so a supplied one is simply ignored."""
    r = _client("admin").put("/api/workspace/discovery",
                             json={"enabled": False, "workspace_id": "somebody-else"})

    assert r.status_code == 200
    assert writes["set"] == [("ws1", False)]


def test_a_missing_enabled_field_is_a_422_not_a_default(writes):
    """No default on the model: "turn it off" and "I forgot to say" must not be the same
    request."""
    assert _client("admin").put(
        "/api/workspace/discovery", json={}).status_code == 422
    assert writes["set"] == []


def test_a_missing_workspace_row_is_a_404_not_a_silent_success(monkeypatch):
    monkeypatch.setattr(db, "_rest", lambda *a, **k: [])
    with pytest.raises(ApiError) as exc:
        db.set_workspace_discovery("ws1", False)
    assert exc.value.code == "WORKSPACE_NOT_FOUND"


def test_the_write_patches_only_the_one_column_for_the_named_workspace(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(db, "_rest", lambda m, p, **k: captured.update(method=m, path=p, **k)
                        or [{"id": "ws1", "discovery_enabled": False}])

    db.set_workspace_discovery("ws1", False)

    assert captured["method"] == "PATCH"
    assert captured["path"] == "workspaces"
    assert captured["params"]["id"] == "eq.ws1"
    assert captured["json"] == {"discovery_enabled": False}
