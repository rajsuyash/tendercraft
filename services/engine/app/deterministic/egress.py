"""Pure arithmetic for the Supabase egress ledger.

**Bytes received is what Supabase bills.** Bytes sent are nearly free, so nothing here counts
a request body — only the response. The engine had no instrument at all until this module:
the 2026-09-14 quota incident (`docs/known-pitfalls.md`, "Test debris is not inert") was
found by an email from the vendor, because a job doing 98% useless work raises nothing.

Everything in this file is a pure function over typed inputs, per `docs/conventions.md` — the
mutable accumulator, the contextvar and the log line live in `app/http.py`, beside the client
whose traffic they describe. Keeping the two halves apart is what lets this one carry the
100% branch gate honestly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

#: Ceiling on distinct keys per bucket map. This is a long-running Cloud Run container and a
#: dict appended to on every DB call is a slow leak — route labels are normalised below, so in
#: practice the count stays small, but "in practice" is not a bound.
MAX_BUCKETS = 64

#: Where everything past MAX_BUCKETS lands. Named, so an overflowing ledger says so out loud
#: rather than quietly dropping the bytes.
OVERFLOW_KEY = "other"

UNKNOWN_KEY = "unknown"

_UUID = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


@dataclass(frozen=True)
class Ledger:
    """One UTC day of Supabase response bytes, attributed two ways."""

    day: date
    calls: int = 0
    total_bytes: int = 0
    by_table: dict[str, int] = field(default_factory=dict)
    by_route: dict[str, int] = field(default_factory=dict)


def new_ledger(day: date) -> Ledger:
    return Ledger(day=day)


def _add(buckets: dict[str, int], key: str, nbytes: int) -> dict[str, int]:
    """A NEW bucket map with `nbytes` added to `key`, bounded at MAX_BUCKETS."""
    name = key or UNKNOWN_KEY
    out = dict(buckets)
    if name not in out and len(out) >= MAX_BUCKETS:
        name = OVERFLOW_KEY
    out[name] = out.get(name, 0) + nbytes
    return out


def record(ledger: Ledger, *, day: date, table: str, route: str, nbytes: int) -> Ledger:
    """Add one call to the ledger, rolling over to a fresh one at UTC midnight.

    Rollover is decided by the day the CALLER passes, not by reading a clock in here — the
    caller holds the lock and must see one instant for both the comparison and the new
    ledger's stamp, or a call at 23:59:59.999 is filed under a day already reported.
    """
    base = ledger if day == ledger.day else new_ledger(day)
    return Ledger(
        day=day,
        calls=base.calls + 1,
        total_bytes=base.total_bytes + nbytes,
        by_table=_add(base.by_table, table, nbytes),
        by_route=_add(base.by_route, route, nbytes),
    )


def table_of(path: str) -> str:
    """The PostgREST table a `_rest` path names. Every path in db.py is a bare table today."""
    return path.split("?", 1)[0].strip("/") or UNKNOWN_KEY


def route_label(method: str, path: str) -> str:
    """A BOUNDED attribution key for a request path.

    `/api/tenders/<uuid>/analysis` must not mint a bucket per tender — an unbounded key set is
    the leak MAX_BUCKETS exists to catch, and it would make the by-route table unreadable
    besides. Identifying segments collapse to `{id}`, which is what a route template would
    have given us had one been resolved this early in the middleware chain.
    """
    collapsed = ["{id}" if _is_identifier(s) else s for s in path.split("/") if s]
    return f"{method} /{'/'.join(collapsed)}"


def _is_identifier(segment: str) -> bool:
    return bool(_UUID.match(segment)) or segment.isdigit()


def summary(ledger: Ledger) -> dict:
    """The shape `GET /internal/cron/health` reports. Biggest consumer first, both tables."""
    return {
        "day": ledger.day.isoformat(),
        "calls": ledger.calls,
        "bytes": ledger.total_bytes,
        "by_table": _ranked(ledger.by_table),
        "by_route": _ranked(ledger.by_route),
    }


def _ranked(buckets: dict[str, int]) -> dict[str, int]:
    return dict(sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0])))
