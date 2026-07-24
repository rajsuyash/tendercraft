"""Request authentication — verify the Supabase JWT, derive tenant server-side.

The tenant is ALWAYS looked up from the user's profile using the verified `sub`,
NEVER read from the request body (ET-6 / known-pitfalls: client-supplied tenant IDs
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
    tenant_id: str
    role: str


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


def _lookup_profile(user_id: str) -> dict | None:
    """Fetch the user's profile (tenant + role) via the service role (bypasses RLS)."""
    settings = get_settings()
    if not settings.supabase_service_key:
        raise ApiError(500, "ENGINE_MISCONFIGURED", "service key not configured")
    resp = httpx.get(
        f"{settings.supabase_url}/rest/v1/profiles",
        params={"user_id": f"eq.{user_id}", "select": "tenant_id,role"},
        headers={
            "apikey": settings.supabase_service_key,
            "Authorization": f"Bearer {settings.supabase_service_key}",
        },
        timeout=10,
    )
    resp.raise_for_status()
    rows = resp.json()
    return rows[0] if rows else None


async def get_current_user(authorization: str = Header(default="")) -> AuthedUser:
    """FastAPI dependency: authenticated user with a server-derived tenant."""
    if not authorization.startswith("Bearer "):
        raise ApiError(401, "NO_TOKEN", "missing bearer token")
    claims = verify_jwt(authorization.removeprefix("Bearer ").strip())
    user_id = claims["sub"]
    profile = _lookup_profile(user_id)
    if not profile:
        raise ApiError(403, "NO_PROFILE", "user has no tenant profile")
    return AuthedUser(user_id=user_id, tenant_id=profile["tenant_id"], role=profile["role"])
