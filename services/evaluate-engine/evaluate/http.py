"""One pooled HTTP client.

Module-level httpx.get() builds a fresh client per call — a new TCP+TLS handshake for every
query. keepalive_expiry defaults to FIVE SECONDS, which makes pooling help within a request
and not between them. The bidder product paid for both lessons in production; this starts
with the fix.
"""

from __future__ import annotations

import atexit

import httpx

client = httpx.Client(
    timeout=httpx.Timeout(15.0, connect=5.0),
    limits=httpx.Limits(
        max_keepalive_connections=20, max_connections=50, keepalive_expiry=300.0
    ),
)
atexit.register(client.close)
