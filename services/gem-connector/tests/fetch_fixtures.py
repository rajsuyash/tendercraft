"""Regenerate the golden bid-document fixtures. `uv run python -m tests.fetch_fixtures`

The fixtures are not committed (see fixtures/README.md — public repo, GeM reproduction clause),
so this script is how a developer or a CI cache obtains them. It goes through `GuardedFetcher`,
so it honours robots.txt and the same one-request-per-second cap as production: about six
requests total.

It selects by *template shape* rather than by id, because ids change as bids close. The three
shapes are the ones that broke the parser during development.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.document import fetch_bid_document, parse_bid_document
from app.fetch import GuardedFetcher
from app.main import sweep

FIXTURES = Path(__file__).parent / "fixtures"


def _shape(record: dict) -> str | None:
    fields = record["source_fields"]
    if fields.get("is_high_value"):
        return "high"
    if fields.get("is_boq"):
        return "boq"
    if fields.get("bid_type") == 1:
        return "services-bid"
    return None


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    FIXTURES.mkdir(parents=True, exist_ok=True)
    for stale in FIXTURES.glob("gem-*.pdf"):
        stale.unlink()

    fetcher = GuardedFetcher()
    try:
        records = sweep(fetcher, max_pages=6)["records"]
        chosen: dict[str, dict] = {}
        for record in records:
            shape = _shape(record)
            if shape and shape not in chosen and record["document_urls"]:
                chosen[shape] = record

        missing = {"high", "boq", "services-bid"} - chosen.keys()
        if missing:
            print(f"! no live bid found for shape(s): {sorted(missing)} — widen max_pages")

        for shape, record in chosen.items():
            parent_id = record["document_urls"][0].rsplit("/", 1)[-1]
            body = fetch_bid_document(fetcher, parent_id)
            path = FIXTURES / f"gem-{shape}-{parent_id}.pdf"
            path.write_bytes(body)
            parsed = parse_bid_document(body)
            print(
                f"✓ {path.name} ({len(body):,}B) "
                f"ref={record['portal_ref_no']} "
                f"turnover={parsed['min_avg_annual_turnover_inr']} "
                f"emd={parsed['emd_required']}/{parsed['emd_amount_inr']}"
            )
    finally:
        fetcher.close()


if __name__ == "__main__":
    main()
