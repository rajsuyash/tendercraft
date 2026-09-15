#!/usr/bin/env python3
"""Rename tenders whose stored title is the old filename fallback.

    services/engine/.venv/bin/python tools/backfill-tender-titles.py           # dry run
    services/engine/.venv/bin/python tools/backfill-tender-titles.py --apply   # write

WHY A SCRIPT AND NOT A MIGRATION. `display_title` runs once at ingest and its result is
stored in `tenders.title`, so changing the function only affects new uploads. This is a
one-off data correction, and it is narrow on purpose.

WHY IT IS NARROW — this is the important part. **The stored column has lost its provenance.**
Once `display_title` collapsed "parsed title" and "filename fallback" into one string, nothing
records which one a given row holds. So the obvious backfill — recompute every row from
`tender_number`/`authority` — destroys real titles. Measured on this database before writing
a single row:

    Supply of 500 Desktop Computers      ->  GEM/2026/B/5127401 · National Informatics Centre
    e-Office Software Implementation     ->  MAHA/IT/2026/4415 · MahaIT
    Selection of Agency for Conducting…  ->  National Bank for Agriculture and Rural Dev…

Three genuinely parsed titles replaced by reference numbers. The blanket rule touched 14 of
21 rows; this one touches 6, and leaves every title above alone.

THE RULE. A stored title ending in a document extension is the unambiguous signature of the
old fallback — `display_title` never produced one from parsed metadata, and no tender is
actually *called* "something.pdf". Anything else is left untouched, including a filename a
human chose that happens to lack an extension: a wrong rename is worse than a stale one,
because the stale one is at least the name the user has been looking at.
"""

from __future__ import annotations

import pathlib
import re
import sys

import httpx

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "services" / "engine"))
from app.deterministic.tender_meta import TenderMeta, display_title  # noqa: E402

#: The signature of the old fallback. Narrow by design — see the module docstring.
FILENAME = re.compile(r"\.(pdf|xlsx|xlsm|csv)$", re.I)


def client() -> httpx.Client:
    env: dict[str, str] = {}
    root = pathlib.Path(__file__).resolve().parents[1]
    for line in (root / ".env").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k] = v.strip().strip('"').strip("'")
    key = env.get("SUPABASE_SERVICE_JWT") or env["SUPABASE_SERVICE_ROLE_KEY"]
    return httpx.Client(
        base_url=env["NEXT_PUBLIC_SUPABASE_URL"] + "/rest/v1",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        timeout=60,
    )


def main(apply: bool) -> None:
    c = client()
    rows = c.get("/tenders?select=id,title,tender_number,authority&limit=2000").json()
    if not isinstance(rows, list):
        raise SystemExit(f"read failed: {rows}")

    planned: list[tuple[str, str, str]] = []
    for r in rows:
        old = r["title"] or ""
        if not FILENAME.search(old):
            continue
        new = display_title(
            TenderMeta(tender_number=r["tender_number"], authority=r["authority"]), old
        )
        if new != old:
            planned.append((r["id"], old, new))

    print(f"{len(rows)} tenders · {len(planned)} match the filename signature\n")
    for _, old, new in planned:
        print(f"  {old[:58]:60} ->  {new}")

    if not planned:
        print("\nnothing to do.")
        return
    if not apply:
        print(f"\nDRY RUN. Re-run with --apply to write these {len(planned)} rows.")
        return

    written = 0
    for tender_id, old, new in planned:
        resp = c.patch(
            f"/tenders?id=eq.{tender_id}",
            json={"title": new},
            headers={"Prefer": "return=minimal"},
        )
        if resp.status_code >= 300:
            # Reported per row rather than aborting: a partial write that says which rows
            # landed is recoverable; one that stops silently halfway is not.
            print(f"  !! {tender_id}: {resp.status_code} {resp.text[:120]}")
            continue
        written += 1
    print(f"\nwrote {written} of {len(planned)} rows.")

    # Re-read rather than trusting the write. A PATCH that returns 204 and changed nothing
    # is the failure this check exists to catch.
    after = c.get("/tenders?select=id,title&limit=2000").json()
    by_id = {r["id"]: r["title"] for r in after}
    wrong = [(old, new, by_id.get(i)) for i, old, new in planned if by_id.get(i) != new]
    if wrong:
        print(f"!! {len(wrong)} rows did not take the new value:")
        for old, new, got in wrong:
            print(f"   expected {new!r}, found {got!r} (was {old!r})")
        raise SystemExit(1)
    print("verified: every planned row now holds its new title.")


if __name__ == "__main__":
    main("--apply" in sys.argv)
