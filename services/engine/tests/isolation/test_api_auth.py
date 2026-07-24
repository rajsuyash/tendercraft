"""Engine API auth (T3) — /health public, /api/me derives tenant from the verified JWT.

Live integration: exercises the real JWKS verification + profile lookup against Supabase.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from .conftest import requires_supabase, sign_in


def _client():
    from app.main import app  # imported lazily so unit runs don't need engine deps loaded

    return TestClient(app)


def test_health_is_public_and_enveloped():
    resp = _client().get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["status"] == "healthy"
    assert body["error"] is None


def test_me_without_token_is_401_enveloped():
    resp = _client().get("/api/me")
    assert resp.status_code == 401
    body = resp.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "NO_TOKEN"


def test_me_with_garbage_token_is_401():
    resp = _client().get("/api/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "INVALID_TOKEN"


@requires_supabase
def test_me_returns_server_derived_tenant(one_user):
    jwt = sign_in(one_user["email"], one_user["password"])
    resp = _client().get("/api/me", headers={"Authorization": f"Bearer {jwt}"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    # tenant came from the profile lookup, not from any client input
    assert data["tenant_id"] == one_user["tenant_id"]
    assert data["user_id"] == one_user["user_id"]
    assert data["role"] == "admin"
