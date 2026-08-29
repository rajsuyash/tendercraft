"""Live smoke — run by hand against the real partner API, never in CI.

    BIDASSIST_API_KEY=... BIDASSIST_TENDER_FEED_ID=... BIDASSIST_AWARD_FEED_ID=... \
      uv run python tests/live_smoke.py

Not a pytest file on purpose: it costs the vendor real requests, it needs a credential, and a
test that silently no-ops without one is a test that proves nothing while looking green.
"""

from __future__ import annotations

import json
import os
import sys

from app.fetch import GuardedFetcher
from app.listing import normalize, normalize_award
from app.main import AWARD_PATH, TENDER_PATH, sweep

PAGES = int(os.environ.get("SMOKE_PAGES", "2"))


def main() -> int:
    tender_feed = os.environ.get("BIDASSIST_TENDER_FEED_ID", "").strip()
    award_feed = os.environ.get("BIDASSIST_AWARD_FEED_ID", "").strip()
    if not tender_feed or not award_feed:
        print("set BIDASSIST_TENDER_FEED_ID and BIDASSIST_AWARD_FEED_ID", file=sys.stderr)
        return 2

    fetcher = GuardedFetcher()
    try:
        tenders = sweep(fetcher, path=TENDER_PATH, feed_source_id=tender_feed,
                        max_pages=PAGES, convert=normalize, key="portal_ref_no")
        awards = sweep(fetcher, path=AWARD_PATH, feed_source_id=award_feed,
                       max_pages=PAGES, convert=normalize_award, key="award_ref")
    finally:
        fetcher.close()

    print(f"opportunities: {tenders['count']} records over {tenders['pages_fetched']} pages "
          f"(complete={tenders['complete']}, no-ref={tenders['skipped_without_ref']})")
    hosts: dict[str, int] = {}
    for r in tenders["records"]:
        host = r["source_fields"]["portal_host"] or "?"
        hosts[host] = hosts.get(host, 0) + 1
    print("  portals:", sorted(hosts.items(), key=lambda kv: -kv[1]))
    print("  sample:", json.dumps(tenders["records"][0], indent=1)[:700] if tenders["records"] else "-")

    laddered = [a for a in awards["records"] if a["participant_count"] > 1]
    print(f"\nawards: {awards['count']} records, {len(laddered)} with a multi-bidder ladder")
    if laddered:
        best = max(laddered, key=lambda a: a["participant_count"])
        print(f"  deepest ladder: {best['participant_count']} bidders — {best['title']!r}")
        for rung in best["ladder"][:5]:
            print(f"    L{rung['rank']}  {rung['seller'][:44]:46} {rung['total_price']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
