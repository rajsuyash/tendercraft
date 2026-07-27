"""Runtime config — fail fast on missing required env, no silent fallbacks."""

from __future__ import annotations

import os
from decimal import Decimal
from functools import lru_cache
from pathlib import Path


def _repo_env() -> Path | None:
    # services/evaluate-engine/evaluate -> repo root is three up in a checkout. In a container
    # the app sits at /app/evaluate, which has fewer parents, and an unguarded parents[3]
    # raises IndexError AT IMPORT — reported by the platform only as "failed to listen on
    # PORT". A dev convenience must never be able to take down production.
    here = Path(__file__).resolve()
    if len(here.parents) > 3:
        c = here.parents[3] / ".env"
        if c.exists():
            return c
    return None


def _load_dotenv() -> None:
    p = _repo_env()
    if p is None:
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.split("#")[0].strip().strip('"').strip("'"))


class Settings:
    def __init__(self) -> None:
        _load_dotenv()
        self.supabase_url = self._require("NEXT_PUBLIC_EVAL_SUPABASE_URL")
        self.service_key = os.environ.get("EVAL_SUPABASE_SERVICE_JWT", "")
        self.jwks_url = f"{self.supabase_url}/auth/v1/.well-known/jwks.json"
        self.jwt_issuer = f"{self.supabase_url}/auth/v1"
        self.variance_threshold = float(os.environ.get("EVAL_VARIANCE_THRESHOLD", "0.20"))
        self.default_quorum = int(os.environ.get("EVAL_DEFAULT_QUORUM", "3"))

        # Throughput extension (ENV-9..12). Defaults match .env.example; every one of them is
        # a bound on something that is otherwise unbounded — an archive, a page budget, a
        # model's willingness to be confident.
        self.ocr_max_pages = int(os.environ.get("EVAL_OCR_MAX_PAGES_PER_TENDER", "300"))
        self.archive_max_bytes = int(os.environ.get("EVAL_ARCHIVE_MAX_BYTES", "524288000"))
        self.archive_max_files = int(os.environ.get("EVAL_ARCHIVE_MAX_FILES", "500"))
        self.attribution_threshold = Decimal(
            os.environ.get("EVAL_ATTRIBUTION_THRESHOLD", "0.85"))

        # F13-AC2 enforced at runtime, not only in CI. If someone ever points this at the
        # bidder database, the process refuses to start rather than quietly serving from it.
        bidder = os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "")
        if bidder and bidder.rstrip("/") == self.supabase_url.rstrip("/"):
            raise RuntimeError(
                "F13 WALL BREACH: the evaluate engine is configured against the bidder "
                "Supabase project. These products may not share a database."
            )

    @staticmethod
    def _require(name: str) -> str:
        v = os.environ.get(name)
        if not v:
            raise RuntimeError(f"missing required env var: {name}")
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
