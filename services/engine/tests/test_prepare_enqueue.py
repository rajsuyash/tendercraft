# services/engine/tests/test_prepare_enqueue.py
"""The prepare contract: fast answers stay fast, slow work leaves a job behind.

Follows the FakeDB-at-module-boundary style of test_jobs.py and the OIDC-mint style of
test_cron.py — `verify_cron_caller` is the real function, exercised with a real (HS256-signed
in test) token, not monkeypatched away, because that boundary is the whole point of this file.
"""
from __future__ import annotations

import jwt
import pytest
from fastapi.testclient import TestClient

from app import cron_auth, db, tasks
from app.auth import AuthedUser, get_current_user
from app.main import create_app

AUDIENCE = "https://engine.test"
CALLER = "tasks@proj.iam.gserviceaccount.com"

WORKSPACE = "w1"
OTHER_WORKSPACE = "w2"
TENDER = "t1"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("CRON_AUDIENCE", AUDIENCE)
    monkeypatch.setenv("CRON_SERVICE_ACCOUNTS", CALLER)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: AuthedUser(
        user_id="u1", workspace_id=WORKSPACE, role="admin",
    )
    return TestClient(app)


@pytest.fixture
def google(monkeypatch):
    """Stand in for Google's JWKS with a symmetric key (see test_cron.py::google)."""
    monkeypatch.setattr(
        cron_auth, "_jwks_client",
        lambda: type("K", (), {"get_signing_key_from_jwt":
                                lambda self, t: type("S", (), {"key": "secret"})()})(),
    )

    def decode(token, key, **kw):
        kw["algorithms"] = ["HS256"]
        return real_decode(token, key, **kw)

    real_decode = jwt.decode
    monkeypatch.setattr(jwt, "decode", decode)
    return None


def _mint(**overrides) -> str:
    claims = {"aud": AUDIENCE, "iss": "https://accounts.google.com",
              "email": CALLER, "email_verified": True, "exp": 9_999_999_999}
    claims.update(overrides)
    return jwt.encode(claims, "secret", algorithm="HS256")


@pytest.fixture
def oidc_headers(google):
    return {"Authorization": f"Bearer {_mint()}"}


@pytest.fixture
def auth_headers():
    # get_current_user is overridden by the `client` fixture; no real bearer token needed.
    return {}


@pytest.fixture
def enqueued(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(tasks, "enqueue_job", lambda job_id: calls.append(job_id))
    return calls


@pytest.fixture
def _no_op_lock_ok(monkeypatch):
    """A tender with one confirmed, anchored criterion: the lock gate passes."""
    monkeypatch.setattr(db, "get_tender", lambda tid, wid: {"id": tid, "workspace_id": wid})
    monkeypatch.setattr(
        db, "get_criteria",
        lambda tid, wid, **k: [{
            "id": "c1", "confidence": 0.95, "confirmed": True,
            "requirement_level": "mandatory", "anchor_page": 3, "anchor_clause": "4.1",
        }],
    )


@pytest.fixture
def seeded_tender(_no_op_lock_ok, enqueued, monkeypatch):
    """Fresh tender, no job yet — start() will create one."""
    fake_jobs: dict[str, dict] = {}

    def create_job(workspace_id, tender_id, kind):
        row = {"id": "j1", "workspace_id": workspace_id, "tender_id": tender_id,
               "kind": kind, "state": "queued", "stage": None, "done_stages": [],
               "attempts": 0}
        fake_jobs["j1"] = row
        return row

    def get_active(workspace_id, tender_id, kind):
        for row in fake_jobs.values():
            if row["state"] in ("queued", "running"):
                return row
        return None

    monkeypatch.setattr(db, "create_job", create_job)
    monkeypatch.setattr(db, "get_active_job_for_tender", get_active)
    return TENDER


@pytest.fixture
def blocked_tender(monkeypatch):
    monkeypatch.setattr(db, "get_tender", lambda tid, wid: {"id": tid, "workspace_id": wid})
    monkeypatch.setattr(
        db, "get_criteria",
        lambda tid, wid, **k: [{
            "id": "c1", "confidence": 0.4, "confirmed": False,
            "requirement_level": "mandatory", "anchor_page": None, "anchor_clause": None,
        }],
    )
    return TENDER


@pytest.fixture
def other_workspace_job(monkeypatch):
    row = {"id": "j-other", "tender_id": "t-other", "workspace_id": OTHER_WORKSPACE,
           "state": "succeeded", "stage": None, "done_stages": [], "error_code": None,
           "error_message": None}
    monkeypatch.setattr(db, "get_tender", lambda tid, wid: None)  # not in THIS workspace
    monkeypatch.setattr(db, "get_active_job_for_tender", lambda w, t, k: None)
    monkeypatch.setattr(db, "get_last_job_for_tender", lambda w, t, k: row)
    return row


@pytest.fixture
def job_with_lock_done(monkeypatch):
    fake = {"id": "j-lock-done", "workspace_id": WORKSPACE, "tender_id": TENDER,
            "state": "queued", "stage": None, "done_stages": ["lock"], "attempts": 0}
    monkeypatch.setattr(db, "get_job", lambda jid, workspace_id=None: fake if jid == fake["id"] else None)

    def update_job(job_id, patch):
        fake.update(patch)
        return fake

    monkeypatch.setattr(db, "update_job", update_job)
    return fake["id"]


@pytest.fixture
def ran(monkeypatch, job_with_lock_done):
    """Record which stages `_run_prepare_job` actually executes, without touching real work."""
    calls: list[str] = []

    def fake_run(job_id: str) -> None:
        from app import jobs as jobs_mod
        for stage in ("lock", "analysis", "draft"):
            if jobs_mod.should_run(job_id, stage):
                calls.append(stage)
                jobs_mod.finish_stage(job_id, stage)

    monkeypatch.setattr("app.readiness_routes._run_prepare_job", fake_run)
    return calls


@pytest.fixture
def failing_job(monkeypatch):
    fake = {"id": "j-fail", "workspace_id": WORKSPACE, "tender_id": TENDER,
            "state": "queued", "stage": None, "done_stages": [], "attempts": 0,
            "error_code": None, "error_message": None}

    def get_job(jid, workspace_id=None):
        return fake if jid == fake["id"] else None

    def update_job(job_id, patch):
        fake.update(patch)
        return fake

    monkeypatch.setattr(db, "get_job", get_job)
    monkeypatch.setattr(db, "update_job", update_job)

    def boom(job_id: str) -> None:
        from app.envelope import ApiError
        raise ApiError(409, "LOCK_BLOCKED", "3 unconfirmed requirements")

    monkeypatch.setattr("app.readiness_routes._run_prepare_job", boom)
    return fake["id"]


def test_prepare_returns_202_with_a_job_id(client, auth_headers, seeded_tender):
    r = client.post(f"/api/tenders/{seeded_tender}/prepare", headers=auth_headers)
    assert r.status_code == 202
    body = r.json()
    assert body["ok"] is True and body["data"]["job_id"]
    assert body["data"]["state"] in ("queued", "running")


def test_a_blocked_lock_is_still_answered_synchronously(client, auth_headers, blocked_tender):
    """LOCK_BLOCKED is deterministic and instant; making the user wait for a queue to hear it
    would be a worse product, not a more consistent one."""
    r = client.post(f"/api/tenders/{blocked_tender}/prepare", headers=auth_headers)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "LOCK_BLOCKED"


def test_a_second_click_joins_the_running_job_rather_than_starting_another(
    client, auth_headers, seeded_tender, enqueued,
):
    first = client.post(f"/api/tenders/{seeded_tender}/prepare", headers=auth_headers).json()
    second = client.post(f"/api/tenders/{seeded_tender}/prepare", headers=auth_headers).json()
    assert first["data"]["job_id"] == second["data"]["job_id"]
    assert len(enqueued) == 1  # the queue was asked once


def test_status_is_workspace_scoped(client, auth_headers, other_workspace_job):
    r = client.get(f"/api/tenders/{other_workspace_job['tender_id']}/prepare/status",
                    headers=auth_headers)
    assert r.status_code == 404


def test_internal_run_refuses_an_unsigned_caller(client):
    r = client.post("/internal/jobs/run", json={"job_id": "j1"})
    assert r.status_code == 401


def test_internal_run_skips_a_stage_already_done(client, oidc_headers, job_with_lock_done, ran):
    client.post("/internal/jobs/run", json={"job_id": job_with_lock_done}, headers=oidc_headers)
    assert "lock" not in ran and "analysis" in ran


def test_internal_run_records_the_failure_code_on_the_job(client, oidc_headers, failing_job):
    client.post("/internal/jobs/run", json={"job_id": failing_job}, headers=oidc_headers)
    row = db.get_job(failing_job)
    assert row["state"] == "failed" and row["error_code"] != "JOB_FAILED"
