"""Runtime configuration — fail fast on missing required env (no silent fallbacks)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


def _repo_env_path() -> Path | None:
    """Locate the repo-root .env, or None when there isn't one.

    services/engine/app -> repo root is three levels up in a checkout. In a container the
    app lives at /app/app, so that index does not exist — and an unguarded parents[3] raised
    IndexError at import time, which Cloud Run reports only as "container failed to listen
    on PORT". A dev convenience must never be able to take down production.
    """
    here = Path(__file__).resolve()
    if len(here.parents) > 3:
        candidate = here.parents[3] / ".env"
        if candidate.exists():
            return candidate
    return None


def _load_dotenv() -> None:
    """Minimal .env loader (dev). Production injects real env; existing vars win."""
    env_path = _repo_env_path()
    if env_path is None:
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


class Settings:
    def __init__(self) -> None:
        _load_dotenv()
        self.supabase_url = self._require("NEXT_PUBLIC_SUPABASE_URL")
        # Service key for RLS-bypassing engine ops (audit, jobs). Prefer the legacy JWT —
        # it is accepted by every Supabase API; the new sb_secret_ key has narrower coverage.
        # Optional at boot so /health works without it; endpoints that need it check at call time.
        self.supabase_service_key = os.environ.get("SUPABASE_SERVICE_JWT") or os.environ.get(
            "SUPABASE_SERVICE_ROLE_KEY", ""
        )
        self.jwks_url = f"{self.supabase_url}/auth/v1/.well-known/jwks.json"
        self.jwt_issuer = f"{self.supabase_url}/auth/v1"

    @staticmethod
    def _require(name: str) -> str:
        val = os.environ.get(name)
        if not val:
            raise RuntimeError(f"missing required env var: {name}")
        return val


@lru_cache
def get_settings() -> Settings:
    return Settings()
