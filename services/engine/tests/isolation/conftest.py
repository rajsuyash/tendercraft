"""Shared Supabase REST/Auth helpers for the workspace-isolation suite (ET-6).

Dependency-free (urllib) so the isolation proof needs no extra install. Reads
credentials from the repo-root .env; skips cleanly when they are absent so the
unit suite never depends on a live project.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

_ENV_PATH = Path(__file__).resolve().parents[4] / ".env"


def _load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    if _ENV_PATH.exists():
        for line in _ENV_PATH.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    env.update({k: v for k, v in os.environ.items() if k.startswith(("NEXT_PUBLIC_", "SUPABASE_"))})
    return env


ENV = _load_env()
SUPABASE_URL = ENV.get("NEXT_PUBLIC_SUPABASE_URL", "")
# Use the legacy JWT keys for auth/admin/REST — every Supabase API accepts them,
# whereas the new sb_publishable_/sb_secret_ keys aren't accepted by the GoTrue
# admin endpoint. The app still uses the modern keys; these are test-only.
ANON_KEY = ENV.get("SUPABASE_ANON_JWT") or ENV.get("NEXT_PUBLIC_SUPABASE_ANON_KEY", "")
SERVICE_KEY = ENV.get("SUPABASE_SERVICE_JWT") or ENV.get("SUPABASE_SERVICE_ROLE_KEY", "")

_creds_missing = not (SUPABASE_URL and ANON_KEY and SERVICE_KEY)
# Fail CLOSED in CI: the ET-6 mitigation is "isolation tests in CI" (PRD §3.2). A silent
# skip when secrets are un-wired would let a Sev-1 control go unverified. Locally (no CI env)
# we skip so a fresh clone without creds still runs the unit suite.
if _creds_missing and os.environ.get("CI"):
    raise RuntimeError(
        "ET-6 isolation suite requires live Supabase creds in CI — refusing to skip silently"
    )
requires_supabase = pytest.mark.skipif(
    _creds_missing, reason="live Supabase credentials not present in .env"
)


def _request(method: str, path: str, *, key: str, bearer: str | None = None,
             body: dict | None = None, prefer: str | None = None,
             headers: dict | None = None):
    url = f"{SUPABASE_URL}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("apikey", key)
    req.add_header("Authorization", f"Bearer {bearer or key}")
    req.add_header("Content-Type", "application/json")
    # Extra headers let a test drive the x-workspace-id path that current_workspace_id()
    # prefers — PostgREST exposes them to RLS via current_setting('request.headers').
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    if method in ("POST", "PATCH"):
        # `prefer` lets a test model an engine upsert exactly (resolution=merge-duplicates),
        # which is how the cross-workspace approval regression is reproduced.
        req.add_header(
            "Prefer", f"return=representation,{prefer}" if prefer else "return=representation"
        )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw


def rest(method: str, table: str, *, bearer: str, key: str, body=None, query: str = "",
         prefer: str | None = None, headers: dict | None = None):
    """PostgREST call. Pass a user JWT as `bearer` to exercise RLS as that user."""
    return _request(
        method, f"/rest/v1/{table}{query}", key=key, bearer=bearer, body=body,
        prefer=prefer, headers=headers,
    )


def admin_create_user(email: str, password: str) -> str:
    status, data = _request(
        "POST", "/auth/v1/admin/users", key=SERVICE_KEY,
        body={"email": email, "password": password, "email_confirm": True},
    )
    assert status in (200, 201), f"create user failed: {status} {data}"
    return data["id"]


def admin_delete_user(user_id: str) -> None:
    _request("DELETE", f"/auth/v1/admin/users/{user_id}", key=SERVICE_KEY)


def admin_delete_users_by_email(*emails: str) -> None:
    """Remove leftover test users from a prior aborted run (idempotent setup)."""
    status, data = _request("GET", "/auth/v1/admin/users", key=SERVICE_KEY)
    if status != 200 or not isinstance(data, dict):
        return
    wanted = set(emails)
    for user in data.get("users", []):
        if user.get("email") in wanted:
            admin_delete_user(user["id"])


def grant_membership(user_id: str, workspace_id: str, role: str = "admin",
                     email: str | None = None) -> None:
    """Give a user access to a workspace, the way the product does.

    Since migration 0011 a profiles row alone grants NOTHING: current_workspace_id()
    resolves the active workspace and then validates it against workspace_members. A
    fixture that writes only a profile silently produces a user who can see zero rows.

    `email` matters because the roster renders it — a fixture that omits it produces a
    member who displays as a truncated UUID, which is not what production does (invite
    accept writes it, and migration 0013 backfills everyone else).
    """
    profile = {"user_id": user_id, "workspace_id": workspace_id, "role": role,
               "active_workspace_id": workspace_id}
    if email:
        profile["email"] = email
    rest("POST", "profiles", bearer=SERVICE_KEY, key=SERVICE_KEY, body=profile)
    rest("POST", "workspace_members", bearer=SERVICE_KEY, key=SERVICE_KEY,
         body={"user_id": user_id, "workspace_id": workspace_id, "role": role})


@pytest.fixture
def one_user():
    """Provision a single workspace + confirmed user + profile; yield sign-in details."""
    email = "api-user@tendercraft.test"
    pw = "Api-Test-Pw-24!"
    admin_delete_users_by_email(email)
    # This fixture RECREATES the same address every test, so a cached token would carry the
    # deleted user's sub and resolve to NO_PROFILE.
    forget_token(email, pw)
    _, t = rest("POST", "workspaces", bearer=SERVICE_KEY, key=SERVICE_KEY, body={"name": "API Workspace"})
    workspace_id = t[0]["id"]
    uid = admin_create_user(email, pw)
    grant_membership(uid, workspace_id)
    try:
        yield {"email": email, "password": pw, "user_id": uid, "workspace_id": workspace_id}
    finally:
        admin_delete_user(uid)
        rest("DELETE", "workspaces", bearer=SERVICE_KEY, key=SERVICE_KEY, query=f"?id=eq.{workspace_id}")


_TOKENS: dict[tuple[str, str], str] = {}


def sign_in(email: str, password: str, *, fresh: bool = False) -> str:
    """Sign in, caching the token per user for the session.

    GoTrue rate-limits password grants, and the suite calls this once per assertion — an
    uncached version 429s partway through and fails RANDOM tests, which reads as flakiness
    in the product rather than in the harness.

    Caching is safe: the JWT carries identity only. Workspace scope and role are resolved
    server-side from workspace_members on EVERY request, so a token issued before a
    membership change still reflects the change immediately — which is exactly what
    test_revoking_membership_immediately_removes_all_access relies on.
    """
    key = (email, password)
    if fresh or key not in _TOKENS:
        # GoTrue rate-limits password grants per project. Caching removes most of the load;
        # this backs off for the rest rather than failing a random test and reading as a
        # product defect.
        for attempt in range(4):
            status, data = _request(
                "POST", "/auth/v1/token?grant_type=password", key=ANON_KEY,
                body={"email": email, "password": password},
            )
            if status == 200:
                break
            if status != 429:
                break
            time.sleep(2**attempt)
        assert status == 200, f"sign-in failed: {status} {data}"
        _TOKENS[key] = data["access_token"]
    return _TOKENS[key]


def forget_token(email: str, password: str) -> None:
    """Drop a cached token — needed when a test deletes and recreates the same address."""
    _TOKENS.pop((email, password), None)
