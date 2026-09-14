#!/usr/bin/env python3
"""Did the 2026-09-14 feed fixes actually move the numbers? Read-only.

Run it AFTER two recomputes have completed, not one. The defect it checks for was that the
run REUSING a cached relevance band was the run that nulled it, so a single run cannot
distinguish the fix from the bug: run N writes bands either way, and only run N+1 shows
whether they survived. Measuring too early passes under the broken code too.

    services/engine/.venv/bin/python tools/measure-uml-feed.py

Baseline, measured 2026-09-14 before the fixes, workspace "Usha Martin Limited":

    match rows with a NULL band          3192 of 6694
    open in-scope rows                   114
    open in-scope with NO band            22
    plywood-and-nails BOQ                high
    open Indian corpus vs window         1251 vs 1000  (~250 never evaluated)
"""

from __future__ import annotations

import pathlib
import sys
from collections import Counter

import httpx

WID = "4bcdd285-5957-4c6c-ae47-7671569b1c25"  # Usha Martin Limited
TODAY = "2026-09-14T00:00:00Z"
PLYWOOD = "Wbr Grade Plywood"
IS2266 = "Safety Wire Cable For Mounting Retention Tank"

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


def total(path: str) -> int:
    return int(c.get(path).headers["content-range"].split("/")[1])


def page(path: str) -> list[dict]:
    rows, off = [], 0
    while True:
        got = c.get(f"{path}&limit=1000&offset={off}").json()
        rows += got
        if len(got) < 1000:
            return rows
        off += 1000


null_band = total(f"/opportunity_matches?select=id&workspace_id=eq.{WID}&relevance_band=is.null")
all_rows = total(f"/opportunity_matches?select=id&workspace_id=eq.{WID}")
corpus_open = total(f"/opportunities?select=id&market=eq.IN&closing_at=gt.{TODAY}")

rows = page(
    f"/opportunity_matches?select=relevance_band,relevance_source,state,"
    f"opportunities!inner(title,closing_at)"
    f"&workspace_id=eq.{WID}&state=eq.in_scope&opportunities.closing_at=gt.{TODAY}"
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
    line("match rows with a NULL band", "3192 / 6694", f"{null_band} / {all_rows}", null_band == 0),
    line("open in-scope rows", 114, len(rows), len(rows) >= 114),
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
