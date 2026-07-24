"""Shared Supabase REST/Auth helpers for the tenant-isolation suite (ET-6).

Dependency-free (urllib) so the isolation proof needs no extra install. Reads
credentials from the repo-root .env; skips cleanly when they are absent so the
unit suite never depends on a live project.
"""

from __future__ import annotations

import json
import os
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


def _request(method: str, path: str, *, key: str, bearer: str | None = None, body: dict | None = None):
    url = f"{SUPABASE_URL}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("apikey", key)
    req.add_header("Authorization", f"Bearer {bearer or key}")
    req.add_header("Content-Type", "application/json")
    if method in ("POST", "PATCH"):
        req.add_header("Prefer", "return=representation")
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


def rest(method: str, table: str, *, bearer: str, key: str, body=None, query: str = ""):
    """PostgREST call. Pass a user JWT as `bearer` to exercise RLS as that user."""
    return _request(method, f"/rest/v1/{table}{query}", key=key, bearer=bearer, body=body)


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


def sign_in(email: str, password: str) -> str:
    status, data = _request(
        "POST", "/auth/v1/token?grant_type=password", key=ANON_KEY,
        body={"email": email, "password": password},
    )
    assert status == 200, f"sign-in failed: {status} {data}"
    return data["access_token"]
