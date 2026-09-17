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
import logging
import threading
from contextvars import ContextVar
from datetime import UTC, datetime

import httpx

from .deterministic import egress

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


# --- Egress ledger -----------------------------------------------------------------------
#
# Supabase bills bytes LEAVING the database, and until 2026-09-17 nothing here counted them:
# the org hit 12.89 GB against a 5.5 GB quota and the first symptom was the API returning 402.
# A downgrade decision needs a ledger, not an email that arrives after the quota is gone.
#
# The arithmetic is in `deterministic/egress.py`; this is the mutable half — one process-wide
# accumulator, its lock, and the contextvar that says which route or job issued the call.

log = logging.getLogger("tendercraft.egress")

#: Who is spending. Set by the request middleware (`main.py`) and by each cron handler; a call
#: from a background task or a script reads the default, which is honest rather than wrong.
egress_route: ContextVar[str] = ContextVar("egress_route", default="unattributed")

_ledger_lock = threading.Lock()
_ledger = egress.new_ledger(datetime.now(UTC).date())


def note_egress(method: str, path: str, nbytes: int) -> None:
    """Record one PostgREST response, and log the line the daily total is rebuilt from.

    Logged per call rather than only accumulated because the accumulator dies with the
    container — Cloud Run scales to zero, so the in-process number answers "today, on this
    instance" and the logs answer "this cycle, across all of them".
    """
    global _ledger
    table, route = egress.table_of(path), egress_route.get()
    with _ledger_lock:
        _ledger = egress.record(
            _ledger, day=datetime.now(UTC).date(), table=table, route=route, nbytes=nbytes
        )
        day_bytes, day_calls = _ledger.total_bytes, _ledger.calls
    # Table names and byte counts only — never a row, never a header (no secrets in logs).
    log.info(
        "supabase egress",
        extra={"fields": {"method": method, "table": table, "route": route,
                          "bytes": nbytes, "day_bytes": day_bytes, "day_calls": day_calls}},
    )


def egress_snapshot() -> dict:
    """Today's ledger, for `GET /internal/cron/health`."""
    with _ledger_lock:
        return egress.summary(_ledger)


def reset_egress(day: datetime | None = None) -> None:
    """Drop the accumulator. Tests only — nothing in the product forgets a measurement."""
    global _ledger
    with _ledger_lock:
        _ledger = egress.new_ledger((day or datetime.now(UTC)).date())
