"""Ownership guards on the per-item decision + ingest-link write paths (ET-6).

These exercise the exact vulnerability class the review flagged: the engine bypasses RLS, so a
foreign tender_id/criterion_id must be rejected in code before any write.
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
        user_id="u1", tenant_id="t1", role="admin",
    )
    return TestClient(app)


def test_decision_rejects_criterion_not_in_tender(client, monkeypatch):
    monkeypatch.setattr(db, "get_criterion_in_tender", lambda c, t, ten: None)
    calls: list = []
    monkeypatch.setattr(db, "upsert_readiness_decision", lambda *a, **k: calls.append(1))
    monkeypatch.setattr(db, "write_audit", lambda *a, **k: calls.append(1))
    r = client.put("/api/tenders/tX/criteria/cX/decision", json={"decision": "ignore"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "CRITERION_NOT_FOUND"
    assert calls == []  # no write, no audit on the rejected path


def test_decision_audits_override_before_write(client, monkeypatch):
    monkeypatch.setattr(db, "get_criterion_in_tender", lambda c, t, ten: {"id": "cX"})
    order: list[str] = []
    monkeypatch.setattr(db, "write_audit", lambda *a, **k: order.append("audit"))
    monkeypatch.setattr(db, "upsert_readiness_decision", lambda *a, **k: order.append("write") or {})
    # a decision-aware payload is returned; stub its reads
    monkeypatch.setattr(db, "get_criteria", lambda t, ten: [])
    monkeypatch.setattr(db, "get_analysis", lambda t, ten: None)
    monkeypatch.setattr(db, "get_proposal_by_tender", lambda t, ten: None)
    monkeypatch.setattr(db, "get_readiness_decisions", lambda t, ten: [])
    r = client.put("/api/tenders/tX/criteria/cX/decision", json={"decision": "ignore"})
    assert r.status_code == 200
    assert order == ["audit", "write"]  # audit precedes the gate-softening write


def test_decision_resolve_is_not_audited(client, monkeypatch):
    monkeypatch.setattr(db, "get_criterion_in_tender", lambda c, t, ten: {"id": "cX"})
    audited: list = []
    monkeypatch.setattr(db, "write_audit", lambda *a, **k: audited.append(1))
    monkeypatch.setattr(db, "upsert_readiness_decision", lambda *a, **k: {})
    monkeypatch.setattr(db, "get_criteria", lambda t, ten: [])
    monkeypatch.setattr(db, "get_analysis", lambda t, ten: None)
    monkeypatch.setattr(db, "get_proposal_by_tender", lambda t, ten: None)
    monkeypatch.setattr(db, "get_readiness_decisions", lambda t, ten: [])
    r = client.put("/api/tenders/tX/criteria/cX/decision", json={"decision": "resolve"})
    assert r.status_code == 200
    assert audited == []  # resolve doesn't soften the gate, so no audit


def test_decision_rejects_invalid_enum(client):
    r = client.put("/api/tenders/tX/criteria/cX/decision", json={"decision": "skip"})
    assert r.status_code == 422  # Pydantic boundary validation


def test_ingest_rejects_foreign_criterion(client, monkeypatch):
    monkeypatch.setattr(db, "get_criterion_in_tender", lambda c, t, ten: None)
    r = client.post(
        "/api/knowledge/ingest",
        data={"url": "http://example.com", "criterion_id": "cX", "tender_id": "tY"},
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "CRITERION_NOT_FOUND"


def test_ingest_rejects_half_specified_link(client):
    r = client.post("/api/knowledge/ingest", data={"url": "http://example.com", "criterion_id": "cX"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "BAD_LINK"
