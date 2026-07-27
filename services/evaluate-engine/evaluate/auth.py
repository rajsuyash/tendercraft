"""Verify the Supabase JWT; derive the authority server-side.

The authority is ALWAYS resolved from the verified `sub`, NEVER read from a request body.
Client-supplied tenant ids are authz bug class #1 and the bidder product already shipped a
Sev-1 on exactly this.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Header
from jwt import PyJWKClient

from . import db
from .config import get_settings
from .envelope import ApiError


@lru_cache
def _jwks() -> PyJWKClient:
    return PyJWKClient(get_settings().jwks_url)


@dataclass(frozen=True)
class AuthedUser:
    user_id: str
    authority_id: str
    role: str

    @property
    def is_officer(self) -> bool:
        return self.role in ("officer", "chair")

    @property
    def is_chair(self) -> bool:
        return self.role == "chair"

    @property
    def is_auditor(self) -> bool:
        return self.role == "auditor"


def verify_jwt(token: str) -> dict:
    s = get_settings()
    try:
        key = _jwks().get_signing_key_from_jwt(token)
        return jwt.decode(token, key.key, algorithms=["ES256", "RS256"],
                          audience="authenticated", issuer=s.jwt_issuer,
                          options={"require": ["exp", "sub"]})
    except jwt.PyJWTError as exc:
        raise ApiError(401, "INVALID_TOKEN", f"authentication failed: {exc}") from exc


async def get_current_user(
    authorization: str = Header(default=""),
    x_authority_id: str = Header(default=""),
) -> AuthedUser:
    if not authorization.startswith("Bearer "):
        raise ApiError(401, "NO_TOKEN", "missing bearer token")
    claims = verify_jwt(authorization.removeprefix("Bearer ").strip())
    user_id = claims["sub"]

    m = db.member_for(user_id, x_authority_id.strip() or None)
    if not m:
        # A header naming an authority the caller does not belong to is not an error to
        # explain — it is simply not an authority they have.
        raise ApiError(403, "NOT_A_MEMBER", "you are not a member of this authority")
    return AuthedUser(user_id=user_id, authority_id=m["authority_id"], role=m["role"])


def require_write(user: AuthedUser) -> None:
    """Auditors are read-only, everywhere (F1-AC3)."""
    if user.is_auditor:
        raise ApiError(403, "READ_ONLY_ROLE", "auditors cannot modify a tender")
