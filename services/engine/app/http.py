"""One pooled HTTP client for the engine's Supabase traffic.

Module-level `httpx.get()` / `httpx.request()` build a fresh client per call, which means a
new TCP + TLS handshake for every single DB query. A readiness request makes ~8 sequential
PostgREST calls, so that was ~8 handshakes serialised into one page render (measured: 2.5s
server-side for a handler that does no real work). One shared Client keeps the connections
alive across calls; the handshake is paid once per container, not once per query.

httpx.Client is thread-safe, which is what this needs — FastAPI runs the engine's sync
handlers in a threadpool.
"""

from __future__ import annotations

import atexit

import httpx

# keepalive_expiry is the setting that actually matters here, and httpx defaults it to FIVE
# SECONDS. At that default the pool only helps WITHIN one handler (the 4-8 calls a readiness
# request makes back to back) and every new request still pays a fresh handshake — measured
# in prod as /readiness improving 2.56s -> 1.80s and then stalling there. Idle app traffic is
# minutes apart, so the connection has to outlive the gap between requests, not just the gap
# between queries. 5 minutes comfortably covers a user clicking around.
#
# ponytail: HTTP/1.1 keepalive only. http2 would need the `h2` dep, and the win here is
# eliminating the handshake, not multiplexing — the engine's calls are sequential anyway.
client = httpx.Client(
    timeout=httpx.Timeout(15.0, connect=5.0),
    limits=httpx.Limits(
        max_keepalive_connections=20,
        max_connections=50,
        keepalive_expiry=300.0,
    ),
)

atexit.register(client.close)
