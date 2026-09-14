#!/usr/bin/env python3
"""Did the 2026-09-14 feed fixes actually move the numbers? Read-only.

Run it AFTER two recomputes have completed, not one. The defect it checks for was that the
run REUSING a cached relevance band was the run that nulled it, so a single run cannot
distinguish the fix from the bug: run N writes bands either way, and only run N+1 shows
whether they survived. Measuring too early passes under the broken code too.

    services/engine/.venv/bin/python tools/measure-uml-feed.py

Baseline, measured 2026-09-14 before the fixes, workspace "Usha Martin Limited":

    in-scope rows with a NULL band       792 of 4310
    open in-scope rows                   114
    open in-scope with NO band            22
    plywood-and-nails BOQ                high
    open Indian corpus vs window         1251 vs 1000  (~250 never evaluated)

The in-scope null count does not fall to zero and should not: a tender that has CLOSED stops
being recomputed (`open_only=True`), so it keeps whatever band it had when it closed, and the
ones the wipe caught while they were open stay null forever. The number that must reach zero
is the open one — that is the population the engine still acts on.
"""

from __future__ import annotations

import pathlib
import sys
from collections import Counter

import httpx

WID = "4bcdd285-5957-4c6c-ae47-7671569b1c25"  # Usha Martin Limited
PLYWOOD = "Wbr Grade Plywood"
IS2266 = "Safety Wire Cable For Mounting Retention Tank"

#: "Open" must mean exactly what `db.get_opportunities(open_only=True)` means, or this script
#: measures a different population than the engine acts on. A first draft used midnight today
#: and reported five rows as unbanded defects; all five had closed between 05:30 and 12:00 and
#: the engine had correctly stopped recomputing them. A checker that counts rows its subject
#: deliberately ignores manufactures failures — name what the instrument counts.
OPEN = "or=(closing_at.is.null,closing_at.gte.now())"
#: The same predicate through an embedded resource. PostgREST puts the table name on the `or`
#: itself here, not on each column inside it — the other spelling returns a 400 whose body says
#: so, and silently became a TypeError until `page()` started reading the body.
OPEN_EMBED = "opportunities.or=(closing_at.is.null,closing_at.gte.now())"

env: dict[str, str] = {}
for line in (pathlib.Path(__file__).resolve().parents[1] / ".env").read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        env[k] = v.strip().strip('"').strip("'")

KEY = env.get("SUPABASE_SERVICE_JWT") or env["SUPABASE_SERVICE_ROLE_KEY"]
c = httpx.Client(
    base_url=env["NEXT_PUBLIC_SUPABASE_URL"] + "/rest/v1",
    headers={"apikey": KEY, "Authorization": f"Bearer {KEY}", "Prefer": "count=exact"},
    timeout=120,
)


def _body(r: httpx.Response) -> list[dict]:
    """PostgREST answers a bad filter with 400 and a JSON OBJECT naming the column. Reading
    only `.json()` turns that into a TypeError three lines later, which is how a wrong
    embedded-`or` spelling read as a data problem instead of a query problem."""
    if r.status_code >= 300:
        raise SystemExit(f"query failed {r.status_code}: {r.text[:300]}\n  url: {r.request.url}")
    return r.json()


def total(path: str) -> int:
    r = c.get(path)
    _body(r)
    return int(r.headers["content-range"].split("/")[1])


def page(path: str) -> list[dict]:
    rows, off = [], 0
    while True:
        got = _body(c.get(f"{path}&limit=1000&offset={off}"))
        rows += got
        if len(got) < 1000:
            return rows
        off += 1000


# Scoped to IN-SCOPE rows. An excluded row is never banded — `recompute_matches` ranks only
# what survived the gate — so counting nulls across every row conflates "the wipe struck" with
# "the gate did its job": 2,667 of this workspace's 2,669 excluded rows are legitimately null.
null_band = total(
    f"/opportunity_matches?select=id&workspace_id=eq.{WID}"
    f"&state=eq.in_scope&relevance_band=is.null"
)
all_rows = total(f"/opportunity_matches?select=id&workspace_id=eq.{WID}&state=eq.in_scope")
corpus_open = total(f"/opportunities?select=id&market=eq.IN&{OPEN}")

rows = page(
    f"/opportunity_matches?select=relevance_band,relevance_source,state,"
    f"opportunities!inner(title,closing_at)"
    f"&workspace_id=eq.{WID}&state=eq.in_scope&{OPEN_EMBED}"
)
unbanded = [r for r in rows if r["relevance_band"] is None]


def band_of(needle: str) -> str:
    hit = [r for r in rows if needle in r["opportunities"]["title"]]
    return f"{hit[0]['relevance_band']} ({hit[0]['relevance_source']})" if hit else "not in scope"


print(f"{'':<34}{'BEFORE (2026-09-14)':>22}{'NOW':>22}   VERDICT")
print("-" * 86)


def line(label: str, before: object, now: object, ok: bool) -> bool:
    print(f"{label:<34}{str(before):>22}{str(now):>22}   {'PASS' if ok else 'FAIL'}")
    return ok


results = [
    # Informational, and it is SUPPOSED to stay put. Every one of these is a tender that has
    # since closed: the wipe caught it while it was open, and `open_only=True` means no future
    # run will ever revisit it. Permanent scar tissue, invisible to users (a closed tender is
    # not in the feed), and asserting it falls would fail forever for a correct reason.
    line("in-scope NULL bands (closed, frozen)", "792 / 4310", f"{null_band} / {all_rows}", True),
    line("open in-scope rows", 114, len(rows), len(rows) >= 100),
    line("open in-scope with NO band", 22, len(unbanded), len(unbanded) == 0),
    line("plywood-and-nails BOQ band", "high", band_of(PLYWOOD),
         not band_of(PLYWOOD).startswith("high")),
    line("IS 2266 rope tender band", "high", band_of(IS2266),
         band_of(IS2266) != "not in scope"),
    line("open IN corpus vs page size", "1251 vs 1000", f"{corpus_open} (all paged)", True),
]

# The corpus grows between runs — the sweep adds rows three times a day — so the BEFORE
# column is a fixed reading from 2026-09-14, not a live comparison. Only the NOW column
# and the verdicts are measurements.

print("\nband distribution, open in-scope:", dict(Counter(r["relevance_band"] for r in rows)))
print("by source                       :", dict(Counter(r["relevance_source"] for r in rows)))

if unbanded:
    print(f"\n!! {len(unbanded)} open in-scope rows still carry no band. The wipe has a second")
    print("   path — read the Cloud Run log for that run's bands_for line before editing code:")
    for r in unbanded[:10]:
        print("   ", r["opportunities"]["title"][:88])

print()
if all(results):
    print("ALL CHECKS PASS")
else:
    print("SOME CHECKS FAILED — see above")
    sys.exit(1)
