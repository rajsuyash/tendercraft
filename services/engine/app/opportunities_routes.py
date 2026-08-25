"""Opportunity feed endpoints (Module F, screens S14/S16).

Workspace scoping comes from the verified JWT, never the body — the shared corpus is public but
every decision about it is not. The Excluded bucket is a first-class response field rather than
a separate endpoint, because F-FR12 requires its count to be visible from the primary feed at
all times: a filter you cannot see is indistinguishable from a bug that ate your tenders.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from . import authz, db, mailer, notify_service
from .auth import AuthedUser, get_current_user
from .deterministic.discovery import RULE_KINDS
from .deterministic.price_history import summarise, to_award
from .discovery import ingest
from .discovery.registry import REGISTRY, for_market
from .envelope import ApiError, ok

router = APIRouter()
CurrentUser = Annotated[AuthedUser, Depends(get_current_user)]


class RuleIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: str
    spec: dict = Field(default_factory=dict)
    enabled: bool = True


#: The opt-in narrow feed. One well-known name so the toggle can find and remove its own rule,
#: and so the Excluded bucket says something a human wrote rather than something we generated.
CAPABILITY_RULE_NAME = "Only my capability keywords"


class MatchPatch(BaseModel):
    watched: bool | None = None
    assigned_to: str | None = None


@router.get("/api/opportunities")
async def list_opportunities(
    user: CurrentUser,
    state: Literal["in_scope", "excluded"] = "in_scope",
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    """The feed. Always returns BOTH counts, whichever bucket was asked for."""

    def work() -> dict:
        # One scope, read once and passed to every query below. Deriving it separately in each
        # would let the list and its own counters disagree the first time one of them changed.
        markets = db.get_workspace_markets(user.workspace_id)
        rows = db.get_feed(user.workspace_id, state, limit=limit, markets=markets)
        return {
            "state": state,
            "items": rows,
            "counts": {
                "in_scope": db.count_feed(user.workspace_id, "in_scope", markets),
                "excluded": db.count_feed(user.workspace_id, "excluded", markets),
                "likely_eligible": db.count_eligible(user.workspace_id, markets),
                # The one that earns its place on the strip: rare, and it means "do not spend
                # an afternoon on this". Kept alongside rather than replacing the other so the
                # response shape stays additive for anything already reading it.
                "below_turnover_bar": db.count_eligible(
                    user.workspace_id, markets, "likely_ineligible"
                ),
                # The denominator for the one above. Without it a zero reads as an all-clear
                # when it may mean nothing was measurable at all.
                "states_a_turnover_bar": db.count_comparable(user.workspace_id, markets),
            },
            "markets": markets,
            # When the CORPUS was last swept, per market. The header used to infer this from
            # the first row in the list, which is the age of one tender rather than of the
            # sweep — and a closed tender's timestamp never moves again.
            "last_swept": db.last_swept_at(markets),
            "rules": db.get_discovery_rules(user.workspace_id),
            # The roster the Owner column assigns from. Served here rather than fetched by the
            # page: the engine sits beside the database, so this is two co-located queries,
            # where a second web->engine call would be another full hop for the same rows.
            "members": db.get_workspace_members(user.workspace_id),
        }

    return ok(await run_in_threadpool(work))


@router.post("/api/opportunities/refresh")
async def refresh(
    user: CurrentUser,
    max_pages: int = Query(default=8, ge=1, le=60),
    q: str = Query(
        default="", max_length=80, description="portal full-text query; widens coverage"
    ),
) -> dict:
    """Sweep the connector, then re-run this workspace's gate.

    Sync work in a threadpool: the sweep sleeps between portal requests to honour the rate cap,
    and sleeping on the event loop would stall every other request in the container
    (docs/known-pitfalls.md).
    """

    def work() -> dict:
        # Every country the workspace watches, not just the one it is registered in.
        markets = db.get_workspace_markets(user.workspace_id)
        swept = ingest.refresh_markets(markets, max_pages=max_pages, query=q)
        matched = ingest.recompute_matches(user.workspace_id)
        return {"swept": swept, "matched": matched}

    try:
        return ok(await run_in_threadpool(work))
    except RuntimeError as exc:
        raise ApiError(503, "CONNECTOR_UNAVAILABLE", str(exc)) from exc


class MarketsIn(BaseModel):
    #: Validated against the registry below, not against a Literal: a market with no configured
    #: source would be a country the user can tick and never receive a tender from, which reads
    #: as a broken feed rather than as a missing connector.
    markets: list[str] = Field(min_length=1, max_length=8)


@router.get("/api/opportunities/markets")
async def list_markets(user: CurrentUser) -> dict:
    """Which countries can be watched, and which this workspace currently watches."""

    def work() -> dict:
        return {
            "available": [
                {"market": m, "sources": [s.source_id for s in for_market(m)]}
                for m in sorted({s.market for s in REGISTRY if s.connector_url})
            ],
            "watched": db.get_workspace_markets(user.workspace_id),
            "home": db.get_workspace_market(user.workspace_id),
        }

    return ok(await run_in_threadpool(work))


@router.put("/api/opportunities/markets")
async def set_markets(user: CurrentUser, body: MarketsIn) -> dict:
    """Choose which countries feed this workspace's opportunity list.

    Widening takes effect on the next sweep; narrowing takes effect immediately, because the
    match recompute below re-reads the corpus through the new scope. Both are re-run here so
    the user never has to know which of the two they just did.
    """
    requested = sorted({m.strip().upper() for m in body.markets if m.strip()})
    configured = {s.market for s in REGISTRY if s.connector_url}
    unknown = [m for m in requested if m not in configured]
    if unknown:
        raise ApiError(
            422,
            "MARKET_NOT_AVAILABLE",
            f"No source is configured for {', '.join(unknown)}. "
            f"Available: {', '.join(sorted(configured)) or 'none'}.",
        )
    if not requested:
        # Belt and braces with the DB check constraint. An empty feed reached by configuration
        # is indistinguishable from a broken one, and produces no error anywhere (ET-7).
        raise ApiError(422, "MARKET_REQUIRED", "Choose at least one country.")

    def work() -> dict:
        saved = db.set_workspace_markets(user.workspace_id, requested)
        matched = ingest.recompute_matches(user.workspace_id)
        return {"watched": saved, "matched": matched}

    return ok(await run_in_threadpool(work))


@router.post("/api/opportunities/keyword-gate")
async def set_keyword_gate(user: CurrentUser, on: bool = Query(...)) -> dict:
    """Turn the narrow feed on or off.

    It is a RULE, not a setting, on purpose: the check constraint on `opportunity_matches`
    refuses an exclusion that names no rule, so making this a boolean flag somewhere would have
    required a second, unnamed way to hide tenders. As a rule it appears in the Excluded bucket,
    names itself on every row it hides, and is undone by deleting it (G-9 / F-AC6).
    """

    def work() -> dict:
        existing = next(
            (r for r in db.get_discovery_rules(user.workspace_id)
             if r["name"] == CAPABILITY_RULE_NAME),
            None,
        )
        if not on:
            if existing:
                db.delete_discovery_rule(existing["id"], user.workspace_id)
            return {"enabled": False} | ingest.recompute_matches(user.workspace_id, doc_budget=0)

        identity = db.get_profile_context(user.workspace_id).get("legal_identity") or {}
        keywords = list(identity.get("capability_keywords") or [])
        if not keywords:
            # Refusing here rather than creating an inert rule: a rule that hides nothing but
            # claims to be filtering is a worse lie than an error message.
            raise ApiError(
                422,
                "NO_CAPABILITY_KEYWORDS",
                "Add capability keywords to your vendor profile before narrowing the feed",
            )
        db.create_discovery_rule(
            user.workspace_id,
            {"name": CAPABILITY_RULE_NAME, "kind": "keyword_match_required",
             "spec": {"keywords": keywords}, "enabled": True},
        )
        return {"enabled": True} | ingest.recompute_matches(user.workspace_id, doc_budget=0)

    return ok(await run_in_threadpool(work))


@router.post("/api/opportunities/rules")
async def create_rule(body: RuleIn, user: CurrentUser) -> dict:
    if body.kind not in RULE_KINDS:
        # Named explicitly rather than echoed from a validator: the closed set is mirrored in
        # the UI, and a drifted option should say which side drifted.
        raise ApiError(422, "UNKNOWN_RULE_KIND", f"rule kind '{body.kind}' is not supported")

    def work() -> dict:
        rule = db.create_discovery_rule(user.workspace_id, body.model_dump())
        # A new rule changes what the user can see, so the feed is recomputed before returning —
        # otherwise the rule appears to have done nothing until the next sweep.
        recomputed = ingest.recompute_matches(user.workspace_id, doc_budget=0)
        return {"rule": rule, "recomputed": recomputed}

    return ok(await run_in_threadpool(work))


@router.delete("/api/opportunities/rules/{rule_id}")
async def delete_rule(rule_id: str, user: CurrentUser) -> dict:
    def work() -> dict:
        db.delete_discovery_rule(rule_id, user.workspace_id)
        # Deleting a rule must return the hidden tenders immediately. Nothing stays excluded by
        # a rule that no longer exists — that would be an exclusion with no author (F-AC6).
        return ingest.recompute_matches(user.workspace_id, doc_budget=0)

    return ok(await run_in_threadpool(work))


@router.patch("/api/opportunities/{opportunity_id}")
async def patch_match(opportunity_id: str, body: MatchPatch, user: CurrentUser) -> dict:
    """Route a tender to a colleague, or star it for yourself.

    This is ask 1's actual pain in `docs/feedback/usha-martin.md` — *"identified manually and
    circulated to the respective Zonal Heads"*. The ask named a CRM; the sentence after it named
    routing, and routing needs no CRM. A signed outbound webhook is the escape hatch if a
    customer names their CRM.
    """
    authz.check(user, authz.DRAFT)
    # `exclude_unset`, not a None filter: clearing an assignment IS `assigned_to: null`, and
    # filtering every None made unassigning unreachable — the endpoint 422'd on it instead.
    patch = body.model_dump(exclude_unset=True)
    if not patch:
        raise ApiError(422, "EMPTY_PATCH", "no fields to update")
    assignee = patch.get("assigned_to")
    if assignee and not db.get_membership(assignee, user.workspace_id):
        # A tender routed to someone who cannot open it is the ask failing silently, which is
        # worse than refusing it — and it keeps a foreign user id out of the row (ET-6).
        raise ApiError(400, "NOT_A_MEMBER", "that person is not a member of this workspace")

    def work() -> dict:
        rows = db.set_match_flags(user.workspace_id, opportunity_id, patch)
        if not rows:
            # The row belongs to another workspace or does not exist. 404 either way: a
            # distinguishable 403 would confirm the opportunity exists in someone else's feed.
            raise ApiError(404, "NOT_FOUND", "opportunity not in this workspace's feed")
        notified = None
        if assignee:
            # After the write, and unable to raise: the routing is the thing that matters, and
            # a bouncing address must not leave the tender unassigned (notify_service).
            notified = notify_service.notify_assignee(
                user.workspace_id, opportunity_id, assignee, user.user_id,
            )
        return {"rows": rows, "notified": notified}

    return ok(await run_in_threadpool(work))


class NotificationSettingsIn(BaseModel):
    enabled: bool | None = None
    recipients: list[str] | None = None
    min_band: Literal["high", "medium", "low"] | None = None
    notify_assignee: bool | None = None


@router.get("/api/notifications/settings")
def get_notification_settings(user: CurrentUser) -> dict:
    """Alert configuration for this workspace. Off until someone turns it on."""
    saved = db.get_notification_settings(user.workspace_id) or {}
    return ok({
        "enabled": bool(saved.get("enabled")),
        "recipients": saved.get("recipients") or [],
        "min_band": saved.get("min_band") or "medium",
        "notify_assignee": saved.get("notify_assignee", True),
        # Whether this DEPLOYMENT can send at all, which is a different question from whether
        # this workspace wants alerts — and the one that explains a silent inbox.
        "smtp_configured": mailer.is_configured(),
        # 'resend' | 'smtp' | 'none'. Named so a support question is one screenshot, not a
        # log dig: "alerts are on but nothing arrives" has a different cause per transport.
        "transport": mailer.transport(),
    })


@router.put("/api/notifications/settings")
async def put_notification_settings(body: NotificationSettingsIn, user: CurrentUser) -> dict:
    authz.check(user, authz.DRAFT)
    patch = body.model_dump(exclude_unset=True)
    if not patch:
        raise ApiError(422, "EMPTY_PATCH", "no fields to update")
    for address in patch.get("recipients") or []:
        # Shape-checked, not validated against a registry: pydantic's EmailStr rejects reserved
        # TLDs including this project's own .test fixtures (docs/known-pitfalls.md).
        if "@" not in address or address.strip() != address:
            raise ApiError(422, "BAD_RECIPIENT", f"not an email address: {address!r}")

    def work() -> dict:
        saved = db.upsert_notification_settings(user.workspace_id, patch, user.user_id)
        db.write_audit(user.workspace_id, user.user_id, "notification_settings_changed",
                       "workspace", user.workspace_id, after=patch)
        return saved

    return ok(await run_in_threadpool(work))


@router.post("/api/notifications/dispatch")
async def dispatch_notifications(user: CurrentUser) -> dict:
    """Send the digest now. Idempotent — a second call sends nothing new.

    Exposed as an endpoint rather than a background timer so it can be driven by a scheduler
    (Cloud Scheduler, cron) without this service growing one, and so a user can press it and
    see the result rather than wondering whether it ran.
    """
    authz.check(user, authz.DRAFT)
    workspace = db.get_workspace(user.workspace_id) or {}
    try:
        return ok(await run_in_threadpool(
            notify_service.dispatch_digest, user.workspace_id,
            workspace.get("name") or "your workspace",
        ))
    except mailer.MailNotConfigured as exc:
        # A named code, not a 500: the UI can say "alerts are on but this deployment cannot
        # send", which is actionable, where a stack trace is not.
        raise ApiError(503, "SMTP_NOT_CONFIGURED", str(exc)) from exc


def _check_window(from_date: str, to_date: str) -> None:
    """Validate an ISO window at the boundary, or raise the envelope's own 400.

    Rejected rather than coerced: a date we cannot parse would otherwise become a blank filter,
    and a blank filter silently returns the WRONG window rather than none — the failure mode
    this whole feature exists to avoid.
    """
    for value in (from_date, to_date):
        if not value:
            continue
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ApiError(400, "BAD_DATE",
                           "from_date/to_date must be ISO YYYY-MM-DD") from exc
    if from_date and to_date and from_date > to_date:
        raise ApiError(400, "BAD_DATE", "from_date is after to_date")


@router.get("/api/price-history")
async def price_history(
    user: CurrentUser,
    q: str = Query(default="", max_length=80, description="product category, e.g. 'wire rope'"),
    limit: int = Query(default=60, ge=1, le=200),
    from_date: str = Query(default="", description="ISO YYYY-MM-DD, inclusive"),
    to_date: str = Query(default="", description="ISO YYYY-MM-DD, inclusive"),
) -> dict:
    """What this category has actually been winning at (UML ask 5).

    Reads the stored corpus only — refreshing is a separate, explicit action because it costs
    two portal requests per award. A user searching a category they have never swept sees an
    empty history with a "fetch from GeM" affordance rather than an unexplained pause.

    The window answers *"the last five years"* and, more usefully, lets two windows be
    compared — which is what *"understanding previous price trends"* actually requires.
    """
    _check_window(from_date, to_date)

    def work() -> dict:
        rows = db.search_award_results(q, limit=limit,
                                       from_date=from_date or None, to_date=to_date or None)
        awards = [to_award(r, r.get("award_prices") or []) for r in rows]
        return {
            "query": q,
            "summary": summarise(awards),
            "awards": [a.as_dict() for a in awards],
            # Said plainly rather than implied: this is a sample of a public corpus we have
            # pulled, not the market. The refresh endpoint is how it grows.
            "window": {"from": from_date or None, "to": to_date or None},
            "note": "Prices are what sellers bid on GeM, as published. "
                    "This is what has been fetched so far, not every award in the category.",
        }

    return ok(await run_in_threadpool(work))


@router.post("/api/price-history/refresh")
async def refresh_price_history(
    user: CurrentUser,
    q: str = Query(min_length=2, max_length=80),
    max_results: int = Query(default=40, ge=1, le=100),
    from_date: str = Query(default="", description="ISO YYYY-MM-DD, inclusive"),
    to_date: str = Query(default="", description="ISO YYYY-MM-DD, inclusive"),
    search_type: str = Query(default="fullText", description="fullText | exact"),
) -> dict:
    """Fetch more published results for a category from the portal.

    Explicit rather than automatic: two portal requests per award against a government site is
    not something to do on a page load, and the user should know a fetch is happening.

    Pass a window to reach BACK. The portal sweep is newest-first and capped, so repeating this
    call without one just re-reads the same recent awards — for an active category the older
    years are unreachable until asked for by date.

    `search_type=exact` when `q` is a registered category name (`/api/categories`): the portal
    filters, nothing is fetched to be discarded, and the same budget reaches years instead of
    weeks.
    """
    authz.check(user, authz.DRAFT)
    _check_window(from_date, to_date)
    if search_type not in ("fullText", "exact"):
        raise ApiError(400, "BAD_SEARCH_TYPE", "search_type must be fullText or exact")
    try:
        return ok(await run_in_threadpool(
            ingest.refresh_awards, q, max_results, "IN",
            from_date or None, to_date or None, search_type))
    except RuntimeError as exc:
        raise ApiError(503, "CONNECTOR_UNAVAILABLE", str(exc)) from exc


# ---------- the categories this seller is registered under (migration 0036) -----------------

@router.get("/api/categories")
async def list_categories(user: CurrentUser) -> dict:
    """The workspace's registered GeM categories, verified and not.

    This is the input side of both UML ask 1 and ask 5: a seller's registration list is the
    highest-precision statement of what they sell that exists, and GeM's own category mapping
    beats any keyword stem we could infer (docs/discovery/source-gem.md finding 7).
    """
    def work() -> dict:
        rows = db.list_workspace_categories(user.workspace_id)
        return {
            "categories": rows,
            "verified": sum(1 for r in rows if r.get("verified_at")),
            "unverified": sum(1 for r in rows if not r.get("verified_at")),
        }

    return ok(await run_in_threadpool(work))


@router.post("/api/categories")
async def add_category(
    user: CurrentUser,
    gem_name: str = Query(min_length=2, max_length=200),
    label: str = Query(default="", max_length=200),
    standard_code: str = Query(default="", max_length=40, description="e.g. IS 2266"),
) -> dict:
    """Register one category, checking the name against the portal as it is stored.

    The check is the point. `searchType=exact` is whole-field and case-sensitive, so a name
    retyped by a human usually matches nothing at all, and an unchecked row would sit there
    returning an empty price history forever with nothing to distinguish it from a category
    that genuinely has no awards. Verified at write time, the answer arrives while the person
    who knows the right spelling is still looking at the screen.

    A name the portal does not recognise is STORED, unverified. It is a fact about the name,
    not a rejection of the customer's category — they are registered under it either way, and
    a row that says "GeM does not match this" is more useful than a refusal.
    """
    authz.check(user, authz.DRAFT)
    try:
        probe = await run_in_threadpool(ingest.verify_category, gem_name)
    except RuntimeError as exc:
        raise ApiError(503, "CONNECTOR_UNAVAILABLE", str(exc)) from exc

    def work() -> dict:
        row = db.upsert_workspace_category(user.workspace_id, gem_name, {
            "label": label or None,
            "standard_code": standard_code or None,
            "verified_at": probe["verified_at"],
            "portal_award_total": probe["portal_award_total"],
        })
        return {"category": row, "recognised": probe["recognised"],
                "portal_award_total": probe["portal_award_total"],
                "note": None if probe["recognised"] else
                        "GeM does not match this name exactly. It is stored, but price history "
                        "cannot be swept for it until the portal's own spelling is used."}

    return ok(await run_in_threadpool(work))


@router.post("/api/opportunities/watch/check")
async def check_watched(
    user: CurrentUser,
    limit: int = Query(default=25, ge=1, le=100),
) -> dict:
    """Poll the watched bids for a change of evaluation stage (UML ask 4).

    Explicit rather than a background timer, for the same reason the digest is: up to three
    portal requests per watched bid is not a page-load side effect, and a user pressing it
    should see the result. A scheduler can call the same endpoint.
    """
    authz.check(user, authz.DRAFT)
    return ok(await run_in_threadpool(
        notify_service.check_watched_stages, user.workspace_id, limit,
    ))
