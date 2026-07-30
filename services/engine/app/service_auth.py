"""Service-to-service auth for calling our own private Cloud Run services.

Lives here rather than in `app/discovery/` on purpose. The discovery guardrail rejects an
`Authorization` header anywhere under that tree, and it is right to: the header it is guarding
against is one sent to a *portal*, which would turn a public-page reader into a credentialed
scraper (G-8). Authenticating to our own connector is the opposite kind of call, so the token
minting lives outside the guarded tree and `ingest.py` never names the header at all.

On Cloud Run the identity comes from the metadata server; there is no key to store or rotate.
Off Cloud Run (local dev, tests) the metadata server is absent and this returns no header —
the connector is then expected to be reachable without one, which is true of a local process.
"""

from __future__ import annotations

import logging
import time

import httpx

log = logging.getLogger("tendercraft.engine")

_METADATA_TOKEN_URL = (
    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/"
    "identity?audience="
)

# Tokens last an hour; re-minting per request would add a metadata round trip to every call.
_CACHE: dict[str, tuple[str, float]] = {}
_TTL_S = 2700.0


def headers_for(audience: str) -> dict[str, str]:
    """Bearer headers for `audience`, or {} when not running on Cloud Run."""
    if not audience:
        return {}
    cached = _CACHE.get(audience)
    now = time.monotonic()
    if cached and now < cached[1]:
        return {"Authorization": f"Bearer {cached[0]}"}

    try:
        response = httpx.get(
            f"{_METADATA_TOKEN_URL}{audience}",
            headers={"Metadata-Flavor": "Google"},
            timeout=5.0,
        )
        response.raise_for_status()
    except httpx.HTTPError:
        # Expected off-platform. Logged at debug so a genuine on-platform failure is still
        # findable, without making every local run look broken.
        log.debug("no metadata server; calling %s unauthenticated", audience)
        return {}

    token = response.text.strip()
    _CACHE[audience] = (token, now + _TTL_S)
    return {"Authorization": f"Bearer {token}"}
