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

# ponytail: HTTP/1.1 keepalive only. http2 would need the `h2` dep, and the win here is
# eliminating the handshake, not multiplexing — the engine's calls are sequential anyway.
client = httpx.Client(
    timeout=httpx.Timeout(15.0, connect=5.0),
    limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
)

atexit.register(client.close)
