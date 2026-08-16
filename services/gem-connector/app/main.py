"""GeM connector — FastAPI app.

Acquisition only. This service holds **no tenant data, no workspace rules, and no product
logic**: it turns GeM's public listing into F-FR1 records and hands them to the engine, which
owns everything a customer can see. That split is what makes the shared corpus safe — one
crawl, no per-tenant state out here, nothing to leak across workspaces because nothing
workspace-shaped is ever stored.

Exclusion lives in `services/engine/app/deterministic/discovery.py` (phase 4) and nowhere else:
this service must never gain a filter, because a filter here is a filter no user authored
(G-9 / F-AC6).

The `{ok,data,error}` envelope is duplicated from the engine rather than imported. Separate
container, separate deploy — and per the wall precedent in CLAUDE.md, copying twenty lines
beats coupling two services' release cycles.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .document import eligibility_for
from .fetch import BotChallengeDetected, FetchRefused, GuardedFetcher
from .listing import build_payload, extract_csrf_token, normalize, normalize_ref, parse_page
from .results import (
    BASE_URL,
    RESULT_STATUSES,
    build_results_payload,
    parse_result_page,
    result_path,
    result_stage,
)

log = logging.getLogger("tendercraft.gem")

# 300 pages at 10 items each — a day of new GeM bids with headroom. A sweep is bounded so a
# parser bug cannot turn into thousands of requests at a government portal.
MAX_PAGES_PER_SWEEP = 300


def ok(data: Any = None) -> dict[str, Any]:
    return {"ok": True, "data": data, "error": None}


def err(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "data": None, "error": {"code": code, "message": message}}


class ApiError(Exception):
    """Raise in a handler; the registered handler renders the envelope. `code` is a stable
    string the caller switches on, per docs/conventions.md's error taxonomy."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def sweep(
    fetcher: GuardedFetcher,
    *,
    max_pages: int,
    stop_at_refs: frozenset[str] = frozenset(),
    search: str = "",
) -> dict[str, Any]:
    """Bootstrap an anonymous session, page the listing, return F-FR1 records.

    `stop_at_refs` is the incremental-sweep hook: paging stops once a page yields nothing new,
    so a daily run costs ~150-300 requests rather than the ~4,850 a full enumeration of all
    48k ongoing bids would take.

    Cookies are acquired per sweep and dropped at the end — never persisted, never reused
    across runs (see fetch.py's module docstring on why that distinction matters for G-8).
    """
    fetcher.reset_session()

    landing = fetcher.get("/all-bids")
    # Checked before anything is parsed: if GeM is challenging us, the run ends here.
    from .fetch import assert_no_bot_challenge

    assert_no_bot_challenge(landing.text, "/all-bids")
    token = extract_csrf_token(landing.text)

    records: list[dict[str, Any]] = []
    seen_this_run: set[str] = set()
    total_found = 0
    pages_fetched = 0

    for page in range(1, max_pages + 1):
        body = build_payload(page, search) | {"csrf_bd_gem_nk": token}
        response = fetcher.post_form("/all-bids-data", body)
        pages_fetched += 1
        total_found, docs = parse_page(response.text)
        if not docs:
            break

        fresh = 0
        for doc in docs:
            record = normalize(doc)
            ref = record["portal_ref_no"]
            if ref is None:
                # A listing row with no bid number cannot be deduped, so it cannot be trusted
                # not to duplicate. Surfaced as a parse anomaly rather than silently dropped.
                log.warning("listing row with no bid number on page %d — skipped", page)
                continue
            if ref in seen_this_run or ref in stop_at_refs:
                continue
            seen_this_run.add(ref)
            records.append(record)
            fresh += 1

        if fresh == 0:
            # Every item on this page was already known: the incremental frontier.
            break

    return {
        "source_id": "gem_bidplus",
        "search": search,
        "portal_total_ongoing": total_found,
        "pages_fetched": pages_fetched,
        "count": len(records),
        "records": records,
    }


def sweep_results(
    fetcher: GuardedFetcher,
    *,
    search: str,
    status: str = "bid_awarded",
    max_pages: int = 5,
    max_results: int = 40,
) -> dict[str, Any]:
    """Published bid results, with the awarded price ladder for each (UML ask 5).

    Two requests per result — the listing page, then that bid's own result page — so this is
    deliberately bounded much tighter than the listing sweep. `max_results` is the real cap;
    a category with 45,000 awards is a backfill job, not one HTTP call.

    A result page that yields no ladder is KEPT with `ladder: []` rather than dropped. The bid
    is genuinely at an earlier stage, and silently omitting it would make a price history look
    denser than the evidence supports.
    """
    fetcher.reset_session()
    landing = fetcher.get("/all-bids")
    from .fetch import assert_no_bot_challenge

    assert_no_bot_challenge(landing.text, "/all-bids")
    token = extract_csrf_token(landing.text)

    out: list[dict[str, Any]] = []
    total_found = 0
    for page in range(1, max_pages + 1):
        body = build_results_payload(page, search, status) | {"csrf_bd_gem_nk": token}
        total_found, docs = parse_page(fetcher.post_form("/all-bids-data", body).text)
        if not docs:
            break
        for doc in docs:
            if len(out) >= max_results:
                break
            path = result_path(doc)
            page_html = fetcher.get(f"/{path}").text
            # The result page is a public page like any other: if the portal starts
            # challenging us here, the run stops rather than adapting (G-8).
            assert_no_bot_challenge(page_html, path)
            result = parse_result_page(page_html)
            out.append({
                "portal_ref_no": normalize_ref(_one(doc, "b_bid_number")),
                "category": _one(doc, "b_category_name"),
                "quantity": _one(doc, "b_total_quantity"),
                "department": _one(doc, "ba_official_details_deptName"),
                "bid_end_date": _one(doc, "final_end_date_sort"),
                "stage": result_stage(doc),
                # Facts, plus a deep link for the prose — §8 of docs/discovery/source-gem.md.
                "source_url": f"{BASE_URL}/{path}",
                **result.as_dict(),
            })
        if len(out) >= max_results:
            break

    return {
        "source_id": "gem_bidplus",
        "search": search,
        "status": status,
        "portal_total_matching": total_found,
        "count": len(out),
        "results": out,
    }


def bid_status(fetcher: GuardedFetcher, *, ref: str) -> dict[str, Any]:
    """How far ONE bid has got through evaluation (UML ask 4).

    GeM publishes the evaluation lifecycle on the same un-captcha'd surface as the price
    ladder: Not Evaluated -> Technical Evaluation -> Financial Evaluation -> Bid Award, carried
    on `b_buyer_status`. So a seller can be told their bid entered technical evaluation without
    anyone logging in to their account.

    **What this does NOT do, and must never claim to.** It reports the STAGE. The text of a
    clarification or a document request lives behind the GeM seller login, which we will not
    hold (G-1) and will not automate (G-8). The stage transition is the alarm clock, not the
    letter — and a feature that implied otherwise would be worse than none, because a bidder
    would stop checking their own portal inbox.

    Searched one stage at a time because `byStatus` takes a single value; the first hit wins,
    most-advanced first, so a bid that has been awarded is not reported as merely evaluated.
    """
    fetcher.reset_session()
    landing = fetcher.get("/all-bids")
    from .fetch import assert_no_bot_challenge

    assert_no_bot_challenge(landing.text, "/all-bids")
    token = extract_csrf_token(landing.text)

    normalized = normalize_ref(ref)
    # Most advanced first: the stages are cumulative on the portal, so asking in this order
    # means the first match is the CURRENT stage rather than an earlier one it also satisfies.
    for status in ("bid_awarded", "fin_evaluated", "tech_evaluated"):
        body = build_results_payload(1, ref, status) | {"csrf_bd_gem_nk": token}
        _, docs = parse_page(fetcher.post_form("/all-bids-data", body).text)
        for doc in docs:
            if normalize_ref(_one(doc, "b_bid_number")) != normalized:
                # Full-text search, so a query can return neighbours. Only an exact reference
                # match may set a stage — reporting the wrong bid's progress is worse than
                # reporting none (F-FR6: no fuzzy matching on a dedup key).
                continue
            return {
                "portal_ref_no": normalized,
                "stage": result_stage(doc),
                "matched_status": status,
                "category": _one(doc, "b_category_name"),
                "source_url": f"{BASE_URL}/{result_path(doc)}",
                "found": True,
            }

    # Not at any published stage. That is a fact about the bid, not a failure of the lookup.
    return {"portal_ref_no": normalized, "stage": "not_evaluated", "matched_status": None,
            "category": None, "source_url": None, "found": False}


def _one(doc: dict, key: str):  # noqa: ANN202
    """Solr wraps every field in a list."""
    v = doc.get(key)
    return v[0] if isinstance(v, list) and v else (None if isinstance(v, list) else v)


def create_app() -> FastAPI:
    app = FastAPI(title="TenderCraft GeM Connector", version="0.1.0")

    async def _refused(_: Any, exc: Exception) -> JSONResponse:
        # A guardrail refusal is not a server fault and must not read as one — it is the
        # system working. 409 so a caller can distinguish it from a portal outage.
        code = "BOT_CHALLENGE" if isinstance(exc, BotChallengeDetected) else "FETCH_REFUSED"
        log.warning("fetch refused: %s", exc)
        return JSONResponse(status_code=409, content=err(code, str(exc)))

    async def _validation(_: Any, __: Exception) -> JSONResponse:
        return JSONResponse(status_code=422, content=err("VALIDATION_ERROR", "invalid request"))

    async def _unhandled(_: Any, exc: Exception) -> JSONResponse:
        log.exception("unhandled error", exc_info=exc)
        return JSONResponse(status_code=500, content=err("INTERNAL", "internal error"))

    async def _api_error(_: Any, exc: Exception) -> JSONResponse:
        assert isinstance(exc, ApiError)
        return JSONResponse(status_code=exc.status, content=err(exc.code, exc.message))

    app.add_exception_handler(ApiError, _api_error)
    app.add_exception_handler(FetchRefused, _refused)
    app.add_exception_handler(RequestValidationError, _validation)
    app.add_exception_handler(Exception, _unhandled)

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return ok({"service": "gem-connector", "status": "up"})

    @app.get("/opportunities")
    def opportunities(
        max_pages: int = Query(default=30, ge=1, le=MAX_PAGES_PER_SWEEP),
        known_refs: str = Query(
            default="", description="comma-separated normalized refs to stop at"
        ),
        q: str = Query(default="", description="GeM full-text query; widens coverage only"),
    ) -> dict[str, Any]:
        """Sync on purpose: the sweep sleeps between requests to honour the rate cap, and
        sleeping inside an async handler stalls the event loop (docs/known-pitfalls.md).
        FastAPI runs sync handlers in a threadpool."""
        stop_at = frozenset(r.strip() for r in known_refs.split(",") if r.strip())
        fetcher = GuardedFetcher()
        try:
            return ok(sweep(fetcher, max_pages=max_pages, stop_at_refs=stop_at, search=q))
        finally:
            fetcher.close()

    @app.get("/bid-results")
    def bid_results(
        q: str = Query(description="GeM full-text query, e.g. a product category"),
        status: str = Query(default="bid_awarded",
                            description="bid_awarded | fin_evaluated | tech_evaluated"),
        max_results: int = Query(default=20, ge=1, le=100),
        max_pages: int = Query(default=5, ge=1, le=30),
    ) -> dict[str, Any]:
        """Published results with the awarded price ladder (UML ask 5).

        Costs two requests per result, so it is capped an order of magnitude tighter than the
        listing sweep. Sync for the same reason as `/opportunities`: the fetcher sleeps to
        honour the rate cap, and sleeping in an async handler stalls the loop.
        """
        if status not in RESULT_STATUSES:
            raise ApiError(400, "BAD_STATUS",
                           f"status must be one of {', '.join(RESULT_STATUSES)}")
        fetcher = GuardedFetcher()
        try:
            return ok(sweep_results(fetcher, search=q, status=status,
                                    max_pages=max_pages, max_results=max_results))
        finally:
            fetcher.close()

    @app.get("/bid-status")
    def bid_status_endpoint(
        ref: str = Query(min_length=6, max_length=60,
                         description="bid reference, e.g. GEM/2026/B/7876746"),
    ) -> dict[str, Any]:
        """The evaluation stage of one bid. Three portal requests worst case, one best."""
        fetcher = GuardedFetcher()
        try:
            return ok(bid_status(fetcher, ref=ref))
        finally:
            fetcher.close()

    @app.get("/bids/{parent_bid_id}/eligibility")
    def eligibility(parent_bid_id: int) -> dict[str, Any]:
        """The C-FR7 eligibility subset for one bid, parsed deterministically.

        `parent_bid_id` is `b_id_parent` from the listing record — the value already embedded in
        that record's `document_urls`. It is NOT the numeric part of the bid number: GeM answers
        an unknown id with 200, `content-type: application/pdf` and a zero-byte body, so a wrong
        id fails as "no eligibility fields found" unless something checks (it does — the `%PDF`
        guard in fetch_bid_document).

        No model is called. Every field here is a labelled row in a generated form, so these are
        facts with no confidence score to threshold — which is why Depth-1 triage on GeM costs
        one 100 KB fetch rather than an LLM extraction (source-gem.md finding 5).
        """
        fetcher = GuardedFetcher()
        try:
            return ok(
                {
                    "source_id": "gem_bidplus",
                    "parent_bid_id": parent_bid_id,
                    "extraction": "deterministic-parse",  # never "model"; nothing here is inferred
                    "fields": eligibility_for(fetcher, parent_bid_id),
                }
            )
        except ValueError as exc:
            # A non-PDF response is the portal telling us something, not a server fault.
            raise ApiError(502, "PORTAL_UNEXPECTED_RESPONSE", str(exc)) from exc
        finally:
            fetcher.close()

    return app


app = create_app()
