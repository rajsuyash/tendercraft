"""The scheduled entry points, and the auth boundary in front of them (UML asks 1 and 4).

These endpoints send email and hit a government portal on behalf of every workspace at once,
with no user in the request. That makes the authentication the feature: most of what follows
tests refusal, because a bug that lets the wrong caller in produces a 200 and looks fine.
"""

from __future__ import annotations

import jwt
import pytest
from fastapi.testclient import TestClient

from app import cron_auth, cron_routes, db, notify_service
from app.main import create_app

AUDIENCE = "https://engine.test"
CALLER = "scheduler@proj.iam.gserviceaccount.com"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("CRON_AUDIENCE", AUDIENCE)
    monkeypatch.setenv("CRON_SERVICE_ACCOUNTS", f"{CALLER},other@proj.iam.gserviceaccount.com")
    return TestClient(create_app())


@pytest.fixture
def google(monkeypatch):
    """Stand in for Google's JWKS with a symmetric key, so tests mint their own tokens.

    The algorithm differs from production (HS256 vs RS256) but everything this module decides
    on — audience, issuer, email, email_verified, expiry — is claim checking, which is
    identical either way.
    """
    monkeypatch.setattr(cron_auth, "_jwks_client",
                        lambda: type("K", (), {"get_signing_key_from_jwt":
                                               lambda self, t: type("S", (), {"key": "secret"})()})())
    monkeypatch.setattr(jwt, "decode", _decoder(jwt.decode))
    return _mint


def _decoder(real):
    def decode(token, key, **kw):
        kw["algorithms"] = ["HS256"]
        return real(token, key, **kw)
    return decode


def _mint(**overrides) -> str:
    claims = {"aud": AUDIENCE, "iss": "https://accounts.google.com",
              "email": CALLER, "email_verified": True, "exp": 9_999_999_999}
    claims.update(overrides)
    return jwt.encode(claims, "secret", algorithm="HS256")


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------- the boundary ----------

def test_no_token_is_refused(client):
    assert client.post("/internal/cron/digest").status_code == 401


def test_a_token_for_another_service_is_refused(client, google):
    """The single most likely real attack: a valid Google token, minted for something else."""
    r = client.post("/internal/cron/digest", headers=_auth(google(aud="https://elsewhere.test")))
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "INVALID_TOKEN"


def test_an_unlisted_service_account_is_refused(client, google):
    """Anyone can mint a valid token for our audience. The signature proves who, not what."""
    r = client.post("/internal/cron/digest", headers=_auth(google(email="stranger@gmail.com")))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "CRON_CALLER_REJECTED"


def test_an_unverified_email_is_refused(client, google):
    r = client.post("/internal/cron/digest", headers=_auth(google(email_verified=False)))
    assert r.status_code == 403


def test_an_expired_token_is_refused(client, google):
    r = client.post("/internal/cron/digest", headers=_auth(google(exp=1_000_000)))
    assert r.status_code == 401


def test_missing_config_fails_closed(monkeypatch, google):
    """The variable nobody set must refuse everyone, not admit everyone."""
    monkeypatch.delenv("CRON_AUDIENCE", raising=False)
    monkeypatch.delenv("CRON_SERVICE_ACCOUNTS", raising=False)
    r = TestClient(create_app()).post("/internal/cron/digest", headers=_auth(_mint()))
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "CRON_NOT_CONFIGURED"


def test_a_supabase_session_cannot_reach_a_cron_route(client):
    """`/internal/*` answers to Google only — a logged-in user's token is not a way in."""
    r = client.post("/internal/cron/digest",
                    headers={"Authorization": "Bearer a.supabase.jwt"})
    assert r.status_code == 401


# ---------- the fan-out ----------

def test_digest_runs_once_per_opted_in_workspace(client, google, monkeypatch):
    monkeypatch.setattr(db, "list_notifying_workspaces", lambda: ["w1", "w2"])
    seen = []
    monkeypatch.setattr(notify_service, "dispatch_digest",
                        lambda ws: seen.append(ws) or {"status": "sent", "sent": 1})

    r = client.post("/internal/cron/digest", headers=_auth(google()))

    assert r.status_code == 200
    assert seen == ["w1", "w2"]
    assert r.json()["data"]["ran"] == 2


def test_one_broken_workspace_does_not_cost_the_others_their_run(client, google, monkeypatch):
    """The whole reason the sweep catches per workspace: a 500 here would say nothing ran."""
    monkeypatch.setattr(db, "list_notifying_workspaces", lambda: ["ok1", "broken", "ok2"])

    def dispatch(ws):
        if ws == "broken":
            raise RuntimeError("SMTP is not configured on this deployment")
        return {"status": "sent", "sent": 1}

    monkeypatch.setattr(notify_service, "dispatch_digest", dispatch)

    body = client.post("/internal/cron/digest", headers=_auth(google())).json()["data"]

    assert body["ran"] == 2
    assert body["failed"] == 1
    assert body["failures"][0]["workspace_id"] == "broken"
    assert "SMTP" in body["failures"][0]["error"]


def test_no_opted_in_workspaces_is_a_quiet_success_not_an_error(client, google, monkeypatch):
    """A scheduler reads a status code. "Nobody enabled alerts" is not a fault to alarm on."""
    monkeypatch.setattr(db, "list_notifying_workspaces", list)
    r = client.post("/internal/cron/digest", headers=_auth(google()))
    assert r.status_code == 200
    assert r.json()["data"] == {"job": "digest", "workspaces": 0, "ran": 0, "failed": 0,
                                "results": [], "failures": []}


def test_watch_sweeps_watching_workspaces_under_the_portal_budget(client, google, monkeypatch):
    """The per-workspace cap is a politeness budget at a government site, so pin it."""
    monkeypatch.setattr(db, "list_watching_workspaces", lambda: ["w1"])
    calls = []
    monkeypatch.setattr(notify_service, "check_watched_stages",
                        lambda ws, limit: calls.append((ws, limit)) or {"checked": 3})

    r = client.post("/internal/cron/watch", headers=_auth(google()))

    assert r.status_code == 200
    assert calls == [("w1", cron_routes._WATCH_LIMIT)]


def test_health_reports_the_caller_without_doing_any_work(client, google, monkeypatch):
    monkeypatch.setattr(db, "list_notifying_workspaces", lambda: ["w1", "w2"])
    monkeypatch.setattr(db, "list_watching_workspaces", lambda: ["w1"])
    monkeypatch.setattr(notify_service, "dispatch_digest",
                        lambda ws: pytest.fail("health must not send anything"))

    body = client.get("/internal/cron/health", headers=_auth(google())).json()["data"]

    assert body == {"caller": CALLER, "notifying_workspaces": 2, "watching_workspaces": 1}


# ---------- the fan-out queries ----------

def test_watching_workspaces_are_deduplicated(monkeypatch):
    """Ten starred bids in one workspace is one sweep, not ten."""
    monkeypatch.setattr(db, "_rest", lambda *a, **k: [
        {"workspace_id": "w1"}, {"workspace_id": "w2"}, {"workspace_id": "w1"},
    ])
    assert db.list_watching_workspaces() == ["w1", "w2"]


def test_fanout_queries_ask_only_for_the_opted_in(monkeypatch):
    """`enabled=is.true` is the opt-in. Reading every row and filtering later would work here
    and quietly stop working the moment someone trusts the caller to filter."""
    captured = {}
    monkeypatch.setattr(db, "_rest",
                        lambda m, p, **k: captured.update(path=p, **k) or [])
    db.list_notifying_workspaces()
    assert captured["path"] == "notification_settings"
    assert captured["params"]["enabled"] == "is.true"
