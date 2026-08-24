"""Authenticating Cloud Scheduler, and nothing else.

Two jobs have no user behind them — the alert digest (UML ask 1) and the stage watcher (UML
ask 4) — so `get_current_user` cannot gate them: it verifies a Supabase token and derives a
workspace from `sub`, and a scheduler has neither. The reflex alternative is a shared secret in
a header, but Google already signs a fresh OIDC token per invocation, so there is nothing to
store, leak or rotate. Same reasoning as `service_auth.py`, pointed the other way: that module
mints an identity for calls we make, this one verifies the identity of calls we receive.

Two independent checks, because neither is sufficient alone:

1. **Audience** — the token was minted for THIS service's URL. A token Google issued for some
   other Cloud Run service, in this project or any other, is a perfectly valid Google token and
   must still be refused here.
2. **Caller identity** — `email` must be an allowlisted service account. Anyone with a Google
   account can ask Google to mint a valid OIDC token for an arbitrary audience; the signature
   proves *who is calling*, never *that they may*.

**Unset config fails closed.** A deployment that forgot the env vars refuses every cron call
rather than accepting every caller — the opposite default would turn a missing variable into an
open, unauthenticated write endpoint, and nothing about the response would look wrong.
"""

from __future__ import annotations

import os
from functools import lru_cache

import jwt
from jwt import PyJWKClient

from .envelope import ApiError

#: Google's OIDC signing keys and the issuer it stamps on tokens minted for service accounts.
_GOOGLE_JWKS = "https://www.googleapis.com/oauth2/v3/certs"
_GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")


@lru_cache
def _jwks_client() -> PyJWKClient:
    return PyJWKClient(_GOOGLE_JWKS)


def _allowed_callers() -> set[str]:
    raw = os.environ.get("CRON_SERVICE_ACCOUNTS", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def verify_cron_caller(authorization: str | None) -> str:
    """Return the verified caller's service-account email, or raise ApiError(401/403).

    Never returns a workspace: a cron acts across every workspace that opted in, and deciding
    which those are is the route's job, from the database — not something a caller may assert.
    """
    audience = os.environ.get("CRON_AUDIENCE", "").strip()
    allowed = _allowed_callers()
    if not audience or not allowed:
        raise ApiError(
            503, "CRON_NOT_CONFIGURED",
            "scheduled jobs are not configured on this deployment "
            "(CRON_AUDIENCE, CRON_SERVICE_ACCOUNTS)",
        )

    if not authorization or not authorization.lower().startswith("bearer "):
        raise ApiError(401, "INVALID_TOKEN", "missing bearer token")
    token = authorization.split(" ", 1)[1].strip()

    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=audience,
            issuer=list(_GOOGLE_ISSUERS),
            options={"require": ["exp", "aud", "iss"]},
        )
    except jwt.PyJWTError as exc:
        raise ApiError(401, "INVALID_TOKEN", f"cron authentication failed: {exc}") from exc

    email = str(claims.get("email") or "").lower()
    # `email_verified` is Google asserting the address belongs to this principal. A service
    # account token always carries it true; requiring it stops a token whose email claim came
    # from somewhere softer than Google's own directory.
    if not claims.get("email_verified") or email not in allowed:
        raise ApiError(403, "CRON_CALLER_REJECTED", "caller is not an allowed scheduler")
    return email
