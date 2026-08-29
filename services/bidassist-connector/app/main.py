"""BidAssist connector — FastAPI app.

Acquisition only, exactly like its GeM and TED siblings: no tenant data, no workspace rules,
no product logic, and above all no filter. Exclusion lives in
`services/engine/app/deterministic/discovery.py` and nowhere else, because a filter here would
be a filter no user authored (G-9 / F-AC6).

**One honest caveat about that last sentence, and it is the most important thing in this
service.** A `FEED_SOURCE_ID` is a saved query held on the vendor's side. The two we were
issued are visibly scoped — 120 sampled notices were, without exception, about wire rope — so
somebody has already decided what this feed does and does not contain, and it was not a user
of this product. That is a filter we do not control, cannot inspect, and did not author.

It is not made safe by ignoring it, so it is handled three ways: the sweep reports the feed id
it used, the registry entry records what the feed was observed to contain and when, and
`docs/discovery/source-bidassist.md` states plainly that feed scope is a vendor setting that
must be re-verified whenever Nexizo changes it. The alternative — treating an aggregator feed
as if it were the whole market — is how a bidder concludes there are no tenders this month.

There is no eligibility endpoint here. GeM's exists because its bid document had to be
reverse-engineered out of a `wkhtmltopdf` form; BidAssist ships structured fields, and what it
does not ship (turnover bars, EMD exemptions) is in the tender documents, which this service
does not parse.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import FastAPI, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .fetch import FetchRefused, GuardedFetcher, UpstreamError
from .listing import PAGE_SIZE, build_body, normalize, normalize_award, parse_page

log = logging.getLogger("tendercraft.bidassist")

TENDER_PATH = "/api/public/v1/tender/search"
AWARD_PATH = "/api/public/v1/tender-result/search"

# Both feeds ran out before page 40 when measured on 2026-08-29 (page 10 full, page 40 empty
# with last=True), so a full sweep is under 800 records and about 40 requests. That is cheap
# enough that the connector always sweeps the whole feed rather than trying to be incremental
# — which it could not do anyway: the vendor returns rows in no stable order, so there is no
# frontier to stop at and no cursor to resume from.
MAX_PAGES_PER_SWEEP = 60
DEFAULT_PAGES = 40


def ok(data: Any = None) -> dict[str, Any]:
    return {"ok": True, "data": data, "error": None}


def err(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "data": None, "error": {"code": code, "message": message}}


def sweep(
    fetcher: GuardedFetcher,
    *,
    path: str,
    feed_source_id: str,
    max_pages: int,
    convert,
    key: str,
    stop_at_refs: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """Page a feed to exhaustion (or to budget) and normalize every row.

    De-duplication is by the record's own key within one sweep only. Rows repeat across pages
    here — 100 fetched rows contained 96 distinct awards — which is what an unordered,
    offset-paged API does when its underlying set shifts mid-sweep. Dropping a repeat inside a
    sweep is bookkeeping; dropping a tender is not, so nothing else is ever discarded.
    """
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    pages_fetched = 0
    skipped_no_ref = 0
    is_last = False

    for page in range(max_pages):
        payload = fetcher.search(path, build_body(feed_source_id, page))
        pages_fetched += 1
        rows, is_last = parse_page(payload)
        if not rows:
            break

        for row in rows:
            record = convert(row)
            ref = record.get(key)
            if not ref:
                # No stable key means the row would re-insert itself on every sweep. Counted
                # and reported rather than silently dropped: a rising number here is the
                # source changing shape under us.
                skipped_no_ref += 1
                continue
            if ref in seen or ref in stop_at_refs:
                continue
            seen.add(ref)
            records.append(record)

        if is_last:
            break

    if not is_last:
        # A truncated sweep is a coverage gap, and a coverage gap that nobody logs reads as an
        # empty market. Same discipline as the price-history cap: no silent truncation.
        log.warning(
            "bidassist: stopped at the %d-page budget with last=False — feed may be truncated",
            pages_fetched,
        )

    return {
        "source_id": "bidassist",
        "market": "IN",
        # Reported so the corpus can attribute rows to the vendor-side saved query that
        # produced them. Feed scope is somebody else's setting; it must be visible.
        "feed_source_id": feed_source_id,
        "portal_total_ongoing": None,  # the vendor publishes no total, only a `last` flag
        "pages_fetched": pages_fetched,
        "complete": is_last,
        "skipped_without_ref": skipped_no_ref,
        "count": len(records),
        "records": records,
    }


def create_app() -> FastAPI:
    app = FastAPI(title="TenderCraft BidAssist Connector", version="0.1.0")

    async def _refused(_: Any, exc: Exception) -> JSONResponse:
        log.warning("fetch refused: %s", exc)
        return JSONResponse(status_code=409, content=err("FETCH_REFUSED", str(exc)))

    async def _upstream(_: Any, exc: Exception) -> JSONResponse:
        log.warning("upstream refused: %s", exc)
        return JSONResponse(status_code=502, content=err("UPSTREAM_REFUSED", str(exc)))

    async def _validation(_: Any, __: Exception) -> JSONResponse:
        return JSONResponse(status_code=422, content=err("VALIDATION_ERROR", "invalid request"))

    async def _unhandled(_: Any, exc: Exception) -> JSONResponse:
        log.exception("unhandled error", exc_info=exc)
        return JSONResponse(status_code=500, content=err("INTERNAL", "internal error"))

    app.add_exception_handler(FetchRefused, _refused)
    app.add_exception_handler(UpstreamError, _upstream)
    app.add_exception_handler(RequestValidationError, _validation)
    app.add_exception_handler(Exception, _unhandled)

    @app.get("/health")
    async def health() -> dict[str, Any]:
        # Reports whether the credential and feed ids are present without revealing them. A
        # connector that is up but unconfigured is the failure this endpoint exists to name.
        return ok({
            "service": "bidassist-connector",
            "status": "up",
            "key_configured": bool(os.environ.get("BIDASSIST_API_KEY", "").strip()),
            "tender_feed_configured": bool(os.environ.get("BIDASSIST_TENDER_FEED_ID", "").strip()),
            "award_feed_configured": bool(os.environ.get("BIDASSIST_AWARD_FEED_ID", "").strip()),
            "page_size": PAGE_SIZE,
        })

    @app.get("/opportunities")
    def opportunities(
        max_pages: int = Query(default=DEFAULT_PAGES, ge=1, le=MAX_PAGES_PER_SWEEP),
        known_refs: str = Query(default=""),
        feed: str = Query(default="", description="override the configured tender feed id"),
    ) -> dict[str, Any]:
        """Sync on purpose: the sweep sleeps between calls to honour the rate cap, and
        sleeping on the event loop would stall the container."""
        feed_id = feed.strip() or os.environ.get("BIDASSIST_TENDER_FEED_ID", "").strip()
        if not feed_id:
            raise UpstreamError("BIDASSIST_TENDER_FEED_ID is unset — nothing to sweep")
        stop_at = frozenset(r.strip() for r in known_refs.split(",") if r.strip())
        fetcher = GuardedFetcher()
        try:
            return ok(sweep(
                fetcher, path=TENDER_PATH, feed_source_id=feed_id, max_pages=max_pages,
                convert=normalize, key="portal_ref_no", stop_at_refs=stop_at,
            ))
        finally:
            fetcher.close()

    @app.get("/awards")
    def awards(
        max_pages: int = Query(default=DEFAULT_PAGES, ge=1, le=MAX_PAGES_PER_SWEEP),
        feed: str = Query(default="", description="override the configured award feed id"),
    ) -> dict[str, Any]:
        """Award results with the full L1..Ln ladder where the source publishes one.

        Named `/awards` rather than `/bid-results` so it is not mistaken for the GeM
        connector's endpoint of that name: the record shape is compatible, the coverage is
        not — this one spans ten portals and carries no MSE flag.
        """
        feed_id = feed.strip() or os.environ.get("BIDASSIST_AWARD_FEED_ID", "").strip()
        if not feed_id:
            raise UpstreamError("BIDASSIST_AWARD_FEED_ID is unset — nothing to sweep")
        fetcher = GuardedFetcher()
        try:
            return ok(sweep(
                fetcher, path=AWARD_PATH, feed_source_id=feed_id, max_pages=max_pages,
                convert=normalize_award, key="award_ref",
            ))
        finally:
            fetcher.close()

    return app


app = create_app()
