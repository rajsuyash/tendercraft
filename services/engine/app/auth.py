"""Request authentication — verify the Supabase JWT, derive workspace server-side.

The workspace is ALWAYS looked up from the user's profile using the verified `sub`,
NEVER read from the request body (ET-6 / known-pitfalls: client-supplied workspace IDs
are authz bug class #1). Supabase signs with ES256 asymmetric keys, so we verify
against the project JWKS.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import httpx
import jwt
from fastapi import Header
from jwt import PyJWKClient

from .config import get_settings
from .envelope import ApiError


@lru_cache
def _jwks_client() -> PyJWKClient:
    return PyJWKClient(get_settings().jwks_url)


@dataclass(frozen=True)
class AuthedUser:
    user_id: str
    workspace_id: str
    role: str            # role IN this workspace (workspace_members.role)
    is_org_admin: bool = False


def verify_jwt(token: str) -> dict:
    """Verify signature, expiry, audience. Raises ApiError(401) on any failure."""
    settings = get_settings()
    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            audience="authenticated",
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise ApiError(401, "INVALID_TOKEN", f"authentication failed: {exc}") from exc


def _rest_get(path: str, params: dict) -> list:
    settings = get_settings()
    if not settings.supabase_service_key:
        raise ApiError(500, "ENGINE_MISCONFIGURED", "service key not configured")
    resp = httpx.get(
        f"{settings.supabase_url}/rest/v1/{path}",
        params=params,
        headers={
            "apikey": settings.supabase_service_key,
            "Authorization": f"Bearer {settings.supabase_service_key}",
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def _lookup_profile(user_id: str) -> dict | None:
    """Fetch the user's profile row via the service role (bypasses RLS).

    Returns None when the user has no profile. Raises AMBIGUOUS_PROFILE when they have
    more than one — never picks a row.

    Why the explicit ambiguity check: this query has no ORDER BY, so with two matching
    rows PostgREST returns them in physical heap order, which changes after any UPDATE or
    VACUUM. Taking rows[0] would silently resolve a request into a NON-DETERMINISTIC
    workspace — a 200 response with every downstream query correctly scoped to the wrong
    workspace, and no error anywhere. Fail closed, always.
    """
    rows = _rest_get(
        "profiles",
        # limit=2 rather than 1: we need to be able to DETECT a second row, not hide it.
        {"user_id": f"eq.{user_id}", "select": "active_workspace_id,is_org_admin", "limit": "2"},
    )
    if not rows:
        return None
    if len(rows) > 1:
        raise ApiError(
            403, "AMBIGUOUS_PROFILE",
            "account resolves to more than one workspace; contact your administrator",
        )
    return rows[0]


def _resolve_membership(user_id: str, workspace_id: str) -> dict | None:
    """The caller's role IN this workspace, or None if they are not a member.

    This MUST mirror public.current_workspace_id() exactly. RLS resolves the scope in SQL;
    the engine resolves it here with the service role (RLS bypassed), so these are two
    implementations of one rule and drift between them is a cross-workspace read. The
    agreement is pinned by tests/isolation/test_workspace_membership.py.
    """
    rows = _rest_get(
        "workspace_members",
        {"user_id": f"eq.{user_id}", "workspace_id": f"eq.{workspace_id}",
         "select": "role", "limit": "1"},
    )
    return rows[0] if rows else None


async def get_current_user(
    authorization: str = Header(default=""),
    x_workspace_id: str = Header(default=""),
) -> AuthedUser:
    """Authenticated user, scoped to ONE workspace derived server-side.

    Resolution order mirrors public.current_workspace_id(): the X-Workspace-Id header if
    present, else the stored active workspace — and EITHER WAY validated against
    workspace_members. A header naming a workspace the caller does not belong to is not an
    error to explain, it is simply not a workspace they have: 403, never a fallback to a
    different one.
    """
    if not authorization.startswith("Bearer "):
        raise ApiError(401, "NO_TOKEN", "missing bearer token")
    claims = verify_jwt(authorization.removeprefix("Bearer ").strip())
    user_id = claims["sub"]

    profile = _lookup_profile(user_id)
    if not profile:
        raise ApiError(403, "NO_PROFILE", "user has no workspace profile")

    workspace_id = x_workspace_id.strip() or profile.get("active_workspace_id")
    if not workspace_id:
        raise ApiError(403, "NO_WORKSPACE", "no active workspace selected")

    membership = _resolve_membership(user_id, workspace_id)
    if not membership:
        raise ApiError(403, "NOT_A_MEMBER", "you are not a member of this workspace")

    return AuthedUser(
        user_id=user_id,
        workspace_id=workspace_id,
        role=membership["role"],
        is_org_admin=bool(profile.get("is_org_admin")),
    )
