"""TED connector — FastAPI app.

Acquisition only, exactly like its GeM sibling: no tenant data, no workspace rules, no product
logic, and above all no filter. Exclusion lives in
`services/engine/app/deterministic/discovery.py` and nowhere else, because a filter here would
be a filter no user authored (G-9 / F-AC6).

There is no `/bids/{id}/eligibility` endpoint here and the absence is deliberate. On GeM the
eligibility figures had to be reverse-engineered out of a `wkhtmltopdf` form; TED publishes CPV,
deadlines, procedure type and place of performance as structured fields, and the money lives in
the buyer's own tender documents rather than the notice. Nothing in this service parses a PDF.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .fetch import FetchRefused, GuardedFetcher
from .listing import build_body, normalize, parse_page

log = logging.getLogger("tendercraft.ted")

SEARCH_PATH = "/v3/notices/search"
PAGE_SIZE = 100
MAX_PAGES_PER_SWEEP = 60


def ok(data: Any = None) -> dict[str, Any]:
    return {"ok": True, "data": data, "error": None}


def err(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "data": None, "error": {"code": code, "message": message}}


def sweep(
    fetcher: GuardedFetcher,
    *,
    max_pages: int,
    market: str = "FR",
    stop_at_refs: frozenset[str] = frozenset(),
    search: str = "",
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    total_found = 0
    pages_fetched = 0

    for page in range(1, max_pages + 1):
        response = fetcher.post_json(SEARCH_PATH, build_body(page, PAGE_SIZE, market, search))
        pages_fetched += 1
        total_found, rows = parse_page(response.text)
        if not rows:
            break

        fresh = 0
        for row in rows:
            record = normalize(row, market)
            ref = record["portal_ref_no"]
            if ref is None:
                log.warning("TED notice with no publication number on page %d — skipped", page)
                continue
            if ref in seen or ref in stop_at_refs:
                continue
            seen.add(ref)
            records.append(record)
            fresh += 1

        if fresh == 0:
            break

    return {
        "source_id": "ted",
        "market": market,
        "search": search,
        "portal_total_ongoing": total_found,
        "pages_fetched": pages_fetched,
        "count": len(records),
        "records": records,
    }


def create_app() -> FastAPI:
    app = FastAPI(title="TenderCraft TED Connector", version="0.1.0")

    async def _refused(_: Any, exc: Exception) -> JSONResponse:
        log.warning("fetch refused: %s", exc)
        return JSONResponse(status_code=409, content=err("FETCH_REFUSED", str(exc)))

    async def _validation(_: Any, __: Exception) -> JSONResponse:
        return JSONResponse(status_code=422, content=err("VALIDATION_ERROR", "invalid request"))

    async def _unhandled(_: Any, exc: Exception) -> JSONResponse:
        log.exception("unhandled error", exc_info=exc)
        return JSONResponse(status_code=500, content=err("INTERNAL", "internal error"))

    app.add_exception_handler(FetchRefused, _refused)
    app.add_exception_handler(RequestValidationError, _validation)
    app.add_exception_handler(Exception, _unhandled)

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return ok({"service": "ted-connector", "status": "up"})

    @app.get("/opportunities")
    def opportunities(
        max_pages: int = Query(default=5, ge=1, le=MAX_PAGES_PER_SWEEP),
        market: str = Query(default="FR", pattern="^(FR|DE|ES|IT)$"),
        known_refs: str = Query(default=""),
        q: str = Query(default="", description="TED title query; widens coverage only"),
    ) -> dict[str, Any]:
        """Sync on purpose: the sweep sleeps between calls to honour the rate cap, and sleeping
        on the event loop would stall the container."""
        stop_at = frozenset(r.strip() for r in known_refs.split(",") if r.strip())
        fetcher = GuardedFetcher()
        try:
            return ok(
                sweep(
                    fetcher, max_pages=max_pages, market=market,
                    stop_at_refs=stop_at, search=q,
                )
            )
        finally:
            fetcher.close()

    return app


app = create_app()
