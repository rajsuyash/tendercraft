"""Server-side workspace derivation — the profile lookup must never guess (ET-6).

A second profile row cannot be inserted while `profiles.user_id` is the PRIMARY KEY, so
these stub the HTTP response directly. That is the point: the guard has to be provably in
place BEFORE the schema makes multi-membership possible.
"""

from __future__ import annotations

import pytest

from app import auth
from app.envelope import ApiError


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _service_key(monkeypatch):
    monkeypatch.setattr(
        auth, "get_settings",
        lambda: type("S", (), {
            "supabase_service_key": "svc", "supabase_url": "https://example.supabase.co",
        })(),
    )


def _stub(monkeypatch, payload):
    captured = {}

    def fake_get(url, **kw):
        captured["params"] = kw.get("params", {})
        return _Resp(payload)

    monkeypatch.setattr(auth.httpx, "get", fake_get)
    return captured


def test_single_profile_resolves(monkeypatch):
    _stub(monkeypatch, [{"workspace_id": "t1", "role": "admin"}])
    assert auth._lookup_profile("u1") == {"workspace_id": "t1", "role": "admin"}


def test_no_profile_returns_none(monkeypatch):
    _stub(monkeypatch, [])
    assert auth._lookup_profile("u1") is None


def test_two_profiles_fail_closed(monkeypatch):
    """The whole point: never rows[0]. Two memberships must 403, not pick one.

    Picking would return HTTP 200 with every downstream query correctly scoped to the
    WRONG workspace — a silent cross-workspace read.
    """
    _stub(monkeypatch, [
        {"workspace_id": "workspace-a", "role": "admin"},
        {"workspace_id": "workspace-b", "role": "writer"},
    ])
    with pytest.raises(ApiError) as exc:
        auth._lookup_profile("u1")
    assert exc.value.code == "AMBIGUOUS_PROFILE"
    assert exc.value.status == 403


def test_ambiguity_is_detectable_not_hidden(monkeypatch):
    """limit=2, not limit=1 — a limit of 1 would mask the second row instead of catching it."""
    captured = _stub(monkeypatch, [{"workspace_id": "t1", "role": "admin"}])
    auth._lookup_profile("u1")
    assert captured["params"]["limit"] == "2"


def test_error_message_leaks_no_workspace_ids(monkeypatch):
    _stub(monkeypatch, [
        {"workspace_id": "workspace-a", "role": "admin"},
        {"workspace_id": "workspace-b", "role": "writer"},
    ])
    with pytest.raises(ApiError) as exc:
        auth._lookup_profile("u1")
    assert "workspace-a" not in exc.value.message
    assert "workspace-b" not in exc.value.message


def test_missing_service_key_is_a_misconfiguration(monkeypatch):
    monkeypatch.setattr(
        auth, "get_settings",
        lambda: type("S", (), {"supabase_service_key": "", "supabase_url": "x"})(),
    )
    with pytest.raises(ApiError) as exc:
        auth._lookup_profile("u1")
    assert exc.value.code == "ENGINE_MISCONFIGURED"
