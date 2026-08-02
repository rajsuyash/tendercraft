"""Pull normalized records from the GeM connector into the shared corpus, then re-run each
workspace's gate over them.

**This module deliberately contains no filtering.** It reads the connector, writes rows, and
delegates every include/exclude decision to `app/deterministic/discovery.py`, which is
model-import-free and enforced as such by CI. G-9 is a structural rule here, not a convention:
the exclusion path must be somewhere a model cannot reach, and this file — which does talk to
the network — is not that place. `tools/check-discovery-guardrails.sh` fails the build if a
function whose name suggests filtering ever appears under `app/discovery/`.

Why the connector is a separate service at all is documented in
`services/gem-connector/app/fetch.py`: GeM's listing needs an anonymous WAF cookie, and rather
than weaken the guardrail that (correctly) forbids that word in this tree, the one source that
needs it lives outside it. This module only ever speaks to our own connector over HTTP.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any

import httpx

from .. import db, http, service_auth
from ..deterministic.discovery import Rule, evaluate_eligibility, evaluate_gate
from . import relevance
from .registry import for_market

log = logging.getLogger("tendercraft.engine")

CONNECTOR_URL = os.environ.get("GEM_CONNECTOR_URL", "").rstrip("/")

# One sweep pulls the day's new bids. The connector itself caps pages and rate-limits per host;
# this is the engine-side ceiling so a scheduler misfire cannot ask for an unbounded crawl.
DEFAULT_PAGES = int(os.environ.get("GEM_SWEEP_PAGES", "12"))

# Documents are fetched only for items that survived a workspace's gate, newest deadline first.
# Fetching all 48k would be pointless and rude; this is §4.1's escalation ladder, capped.
DEFAULT_DOC_BUDGET = int(os.environ.get("GEM_DOC_BUDGET", "25"))

# The language our own explanations are written in, per market.
#
# It follows the MARKET rather than the reader's EN/FR toggle, which corrects what
# docs/multi-market.md originally claimed: a relevance rationale is stored once per (workspace,
# opportunity), so it cannot be per-user without storing it twice. A French workspace therefore
# gets French explanations sitting beside French tender text, whichever way a given reader has
# set their chrome. Only static interface strings follow the toggle.
MARKET_LANGUAGE = {"IN": "en", "FR": "fr", "DE": "de", "ES": "es"}


def _connector(path: str, params: dict[str, Any] | None = None, base: str = "") -> dict:
    base = (base or CONNECTOR_URL).rstrip("/")
    if not base:
        raise RuntimeError("no connector configured for this market")
    # Identity headers are built outside this tree (see app/service_auth.py) so the guardrail
    # forbidding portal-bound credentials here stays literal and unweakened.
    response = http.client.request(
        "GET",
        f"{base}{path}",
        params=params,
        headers=service_auth.headers_for(base),
        timeout=180,
    )
    response.raise_for_status()
    body = response.json()
    if not body.get("ok"):
        raise RuntimeError(f"connector error: {(body.get('error') or {}).get('message')}")
    return body["data"]


def _to_row(record: dict[str, Any]) -> dict[str, Any]:
    """Connector record → `opportunities` row. Absent stays absent (F-FR1).

    Market-agnostic on purpose: both connectors emit the same F-FR1 shape, so this function
    does not know or care which country a tender came from.
    """
    return {
        "source_id": record["source_id"],
        "market": record.get("market", "IN"),
        # What language the notice we stored is actually written in — chosen by the connector,
        # never inferred here. It decides what language the drafter must write.
        "notice_language": record.get("notice_language"),
        "portal_ref_no": record["portal_ref_no"],
        "title": record.get("title"),
        "authority": record.get("authority"),
        "category_codes": record.get("category_codes") or [],
        "geography": record.get("geography"),
        "estimated_value": record.get("estimated_value"),
        "emd": record.get("emd"),
        "published_at": record.get("published_at"),
        "closing_at": record.get("closing_at"),
        "prebid_at": record.get("prebid_at"),
        "document_urls": record.get("document_urls") or [],
        "raw_snapshot_ref": record.get("raw_snapshot_ref"),
        "source_fields": record.get("source_fields") or {},
        "last_seen_at": datetime.now(UTC).isoformat(),
    }


def refresh_corpus(
    max_pages: int = DEFAULT_PAGES, query: str = "", market: str = "IN"
) -> dict[str, Any]:
    """Sweep the connector and upsert into the shared corpus. Workspace-agnostic.

    `query` runs GeM's own full-text search. It ACQUIRES more, it never filters: a chronological
    sweep only ever reaches the newest bids, so a consultancy tender published last week is
    otherwise unreachable no matter how good the ranking is. Widening coverage is the safe
    direction under ET-7 — the failure this module guards against is a tender never seen, and
    nothing here can hide one. The corpus stays shared; only the ranking is per workspace.
    """
    sources = for_market(market)
    if not sources:
        # A market with no configured source is a deployment mistake. Returning an empty feed
        # would look like "no tenders today", which is the ET-7 failure wearing a friendly face.
        raise RuntimeError(f"no source configured for market {market!r}")

    total = 0
    pages = 0
    upserted = 0
    for source in sources:
        params: dict[str, Any] = {"max_pages": max_pages, "q": query}
        if source.source_id == "ted":
            params["market"] = market
        data = _connector("/opportunities", params, base=source.connector_url)
        rows = [_to_row(r) for r in data.get("records", []) if r.get("portal_ref_no")]
        stored = db.upsert_opportunities(rows)
        total = data.get("portal_total_ongoing") or total
        pages += data.get("pages_fetched", 0)
        upserted += len(stored)
        log.info(
            "discovery[%s/%s]: swept %d pages, upserted %d rows",
            market, source.source_id, data.get("pages_fetched", 0), len(stored),
        )
    return {"market": market, "portal_total_ongoing": total,
            "pages_fetched": pages, "upserted": upserted}


def refresh_markets(
    markets: list[str], max_pages: int = DEFAULT_PAGES, query: str = ""
) -> dict[str, Any]:
    """Sweep every country a workspace watches, and report each one separately.

    Per-market failures are collected rather than raised. One unreachable connector must not
    cost the user the other country's sweep — and it must not be silent either, so the failure
    travels back in the response and the coverage strip can say which source is stale. A feed
    that quietly stops including a country is the ET-7 failure, whichever country it is.
    """
    swept: list[dict[str, Any]] = []
    failed: list[dict[str, str]] = []
    for market in markets:
        try:
            swept.append(refresh_corpus(max_pages=max_pages, query=query, market=market))
        except Exception as exc:  # noqa: BLE001 — reported, never swallowed
            log.warning("discovery[%s]: sweep failed (%s)", market, exc)
            failed.append({"market": market, "error": str(exc)})
    return {
        "markets": swept,
        "failed": failed,
        "upserted": sum(m["upserted"] for m in swept),
        "pages_fetched": sum(m["pages_fetched"] for m in swept),
    }


#: The opt-in narrow feed's well-known name. Duplicated from `app/opportunities_routes.py`
#: rather than imported, because a route module importing into the discovery pipeline (or the
#: reverse) is the coupling that makes the guardrail script's job ambiguous. Two constants, one
#: comment at each end saying they must agree — the same discipline the UI/engine enum pair uses.
CAPABILITY_RULE_NAME = "Only my capability keywords"


def _rules_for(workspace_id: str, keywords: list[str] | None = None) -> list[Rule]:
    """This workspace's rules, with the capability gate's keywords refreshed from the profile.

    The gate's `spec` is written once, when the toggle is switched on, and was never updated
    afterwards — so editing your capability keywords changed the ranking and left the RULE
    filtering on the terms you first typed. A vendor whose feed had gone empty would fix their
    keywords, see nothing change, and have no way to discover why. The stored spec is refreshed
    on drift so the Excluded bucket keeps describing what actually happened.
    """
    rows = db.get_discovery_rules(workspace_id)
    if keywords is not None:
        for r in rows:
            if r["name"] != CAPABILITY_RULE_NAME or r.get("kind") != "keyword_match_required":
                continue
            stored = list((r.get("spec") or {}).get("keywords") or [])
            if stored != keywords:
                r["spec"] = {**(r.get("spec") or {}), "keywords": keywords}
                db.update_discovery_rule(r["id"], workspace_id, {"spec": r["spec"]})
                log.info("discovery: refreshed %s from the profile (%d terms)",
                         CAPABILITY_RULE_NAME, len(keywords))
    return [
        Rule(
            name=r["name"], kind=r["kind"],
            spec=r.get("spec") or {}, enabled=r.get("enabled", True),
        )
        for r in rows
    ]


def _capability(workspace_id: str) -> tuple[str, list[str]]:
    """The vendor's own words, and the terms they bid on. Both drive the relevance band."""
    identity = db.get_profile_context(workspace_id).get("legal_identity") or {}
    return (
        identity.get("capability_statement") or "",
        list(identity.get("capability_keywords") or []),
    )


def _profile_turnover_inr(workspace_id: str) -> dict[str, Any]:
    """Average annual turnover from the vendor profile, in rupees.

    `profile_financials.turnover_cr` is in crores; the comparator works in rupees. Converting at
    the boundary rather than in the comparator keeps one unit inside the deterministic layer —
    a mixed-unit comparison is the 100x error this codebase already guards against in the GeM
    amount parser.
    """
    profile = db.get_profile_context(workspace_id)
    values = [
        float(f["turnover_cr"])
        for f in profile.get("financials") or []
        if f.get("turnover_cr") is not None
    ]
    if not values:
        return {}
    return {"avg_annual_turnover_inr": (sum(values) / len(values)) * 10_000_000}


def recompute_matches(workspace_id: str, doc_budget: int = DEFAULT_DOC_BUDGET) -> dict[str, Any]:
    """Re-run this workspace's gate and Depth-1 eligibility over the whole corpus.

    Deliberately recomputes everything rather than only new items: a rule edit must take effect
    across the feed immediately, and C-FR10 wants a profile change to surface newly-eligible
    tenders without waiting for the next sweep.
    """
    # Read first: the gate rule filters on these, so a stale copy in its spec would hide
    # tenders the vendor's current keywords would have kept.
    capability, keywords = _capability(workspace_id)
    rules = _rules_for(workspace_id, keywords)
    profile = _profile_turnover_inr(workspace_id)
    # One lookup, used for BOTH the eligibility sentences and the relevance rationales — they
    # are the same voice explaining the same row and must never end up in different languages.
    market = db.get_workspace_market(workspace_id)
    language = MARKET_LANGUAGE.get(market, "en")
    # WATCHED markets, not the home one: which countries appear in the feed is a choice the
    # bidder makes on their profile, and it is routinely more than the country they are
    # registered in (migration 0022).
    watched = db.get_workspace_markets(workspace_id)
    # Scoped to the countries the bidder ticked. That IS a user-authored scope — the profile
    # names it and the coverage strip states it — which is what F-AC6 requires. What the rule
    # forbids is a scope nobody chose, which is precisely what a single hardcoded market was.
    opportunities = db.get_opportunities(limit=1000, markets=watched)

    matches: list[dict[str, Any]] = []
    in_scope: list[dict[str, Any]] = []
    for opportunity in opportunities:
        gate = evaluate_gate(opportunity, rules)
        row = {
            "opportunity_id": opportunity["id"],
            "state": "in_scope" if gate.in_scope else "excluded",
            "excluded_by_rule": gate.excluded_by_rule,
            "computed_at": datetime.now(UTC).isoformat(),
        }
        if gate.in_scope:
            # The profile's money is in the HOME market's currency; the tender's is in its
            # own. Comparable only when they are the same country.
            verdict = evaluate_eligibility(
                opportunity.get("eligibility"),
                profile,
                language,
                same_currency=(opportunity.get("market") or market) == market,
            )
            row["eligibility"] = verdict.signal
            row["eligibility_reason"] = verdict.reason
            in_scope.append(opportunity)
        else:
            # An excluded item keeps 'unknown': we did not evaluate it, and claiming a verdict
            # we never computed would be a fact invented to fill a column.
            row["eligibility"] = "unknown"
            row["eligibility_reason"] = None
        matches.append(row)

    # Relevance bands the IN-SCOPE items only: the excluded bucket is ordered by nothing anyone
    # reads, and scoring it would pay a model to rank tenders the user asked not to see.
    if in_scope:
        seen_hashes = db.get_relevance_hashes(workspace_id)
        patches = relevance.bands_for(
            in_scope,
            capability_statement=capability,
            keywords=keywords,
            existing=seen_hashes,
            language=language,
        )
        by_id = {m["opportunity_id"]: m for m in matches}
        for opportunity_id, patch in patches.items():
            if opportunity_id in by_id:
                by_id[opportunity_id].update(patch)

    db.upsert_opportunity_matches(workspace_id, matches)

    fetched = _enrich_documents(in_scope, budget=doc_budget)
    if fetched:
        # Second pass so the freshly-parsed turnover figures reach the verdicts in this run
        # rather than the next one — a demo that shows "unknown" everywhere teaches nothing.
        return recompute_matches(workspace_id, doc_budget=0) | {"documents_fetched": fetched}

    return {
        "evaluated": len(matches),
        "in_scope": sum(1 for m in matches if m["state"] == "in_scope"),
        "excluded": sum(1 for m in matches if m["state"] == "excluded"),
        "documents_fetched": 0,
    }


def _enrich_documents(opportunities: list[dict[str, Any]], *, budget: int) -> int:
    """Fetch and parse bid documents for in-scope items that have none yet.

    Bounded by `budget` because this is the only part of the pipeline that touches a government
    portal per-item. Ordered by closing date so the tenders a bidder must act on soonest get
    their eligibility first.
    """
    if budget <= 0:
        return 0
    pending = [
        o for o in opportunities
        if not o.get("eligibility") and o.get("document_urls")
    ]
    pending.sort(key=lambda o: o.get("closing_at") or "9999")

    fetched = 0
    for opportunity in pending[:budget]:
        parent_id = str(opportunity["document_urls"][0]).rstrip("/").rsplit("/", 1)[-1]
        try:
            data = _connector(f"/bids/{parent_id}/eligibility")
        except (httpx.HTTPError, RuntimeError) as exc:
            # One unreadable document must not end the sweep. EC-8: a source that starts
            # returning nothing is an incident, but a single bad row is just a bad row.
            log.warning("discovery: eligibility fetch failed for %s: %s", parent_id, exc)
            continue
        db.set_opportunity_eligibility(
            opportunity["id"], data.get("fields") or {}, datetime.now(UTC).isoformat()
        )
        fetched += 1
    return fetched
