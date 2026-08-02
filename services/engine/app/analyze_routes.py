"""Analysis + profile endpoints (Module C). Analyze runs on a locked TOM only (A-FR5)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from . import analysis, authz, db, estimator, knowledge, rubric_service
from .auth import AuthedUser, get_current_user
from .deterministic import keywords as det_keywords
from .envelope import ApiError, ok

_CATEGORY_CLUSTER = "it-hardware"  # v0: single category cluster until classification lands

router = APIRouter()
log = logging.getLogger("tendercraft.engine")
CurrentUser = Annotated[AuthedUser, Depends(get_current_user)]


class Financial(BaseModel):
    fy_label: str = Field(min_length=2, max_length=12)
    turnover_cr: float = Field(ge=0)


class Experience(BaseModel):
    project_name: str = Field(min_length=2, max_length=300)
    client_type: Literal["govt", "psu", "private"] = "govt"
    value_cr: float | None = Field(default=None, ge=0)
    scope_tags: list[str] = Field(default_factory=list)
    completion_date: str | None = None


class Certification(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    cert_no: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None


class ProfileIn(BaseModel):
    """Everything the eligibility comparators read. Sent as a whole from one form."""

    # Capability drives the relevance band on the opportunity feed (F-FR11). Free prose because
    # what a bidder can say about themselves does not fit a taxonomy; the keywords beside it are
    # the deterministic half, and the only half permitted to gate the feed.
    #
    # NOTE `update_profile` dumps with exclude_none=True, so a null statement is DROPPED rather
    # than written — the form sends "" to clear it. The keyword list is never None, so it is
    # written on every save and clearing it works normally.
    capability_statement: str | None = None
    capability_keywords: list[str] = Field(default_factory=list)

    legal_name: str | None = None
    # Read on demand for keyword suggestions and shown on the profile. Not validated as a URL
    # here beyond a length cap: the fetcher rejects anything that is not http(s) with a public
    # host, and duplicating that judgement in a Pydantic type would put the SSRF decision in two
    # places. "" clears it, per the exclude_none note above.
    website_url: str | None = Field(default=None, max_length=500)
    #: Which library document is the annual report. The document itself is ingested through the
    #: ordinary knowledge path; this is only the pointer.
    annual_report_document_id: str | None = None
    cin: str | None = None
    pan: str | None = None
    gst: str | None = None
    udyam_registration: str | None = None
    net_worth_cr: float | None = Field(default=None, ge=0)
    oem_status: Literal["oem", "system_integrator", "trader"] | None = None
    financials: list[Financial] | None = None
    experience_records: list[Experience] | None = None
    certifications: list[Certification] | None = None


class KeywordSuggestIn(BaseModel):
    #: Optional override so a vendor can try a page before committing it to their profile —
    #: their products page is usually a better read than their homepage.
    website_url: str | None = Field(default=None, max_length=500)


@router.post("/api/profile/keyword-suggestions")
async def keyword_suggestions(body: KeywordSuggestIn, user: CurrentUser) -> dict:
    """Propose short keywords from the vendor's own statement, existing terms and website.

    **Saves nothing.** The response is a list of candidates for a human to tick, and that is a
    guardrail rather than a UX preference: capability keywords feed `keyword_match_required`,
    the one rule that can HIDE a tender, so a model writing them directly would be model-driven
    exclusion (G-9) reached by a longer route. The model proposes; a person accepts; the profile
    write goes through the ordinary PUT.

    The website is fetched ONLY here, only when asked, and only through the SSRF-hardened
    `knowledge.fetch_url_text`. A vendor's site is not ours to crawl on a schedule any more than
    a portal is (G-10).
    """
    authz.check(user, authz.DRAFT)
    identity = db.get_profile_context(user.workspace_id).get("legal_identity") or {}
    statement = identity.get("capability_statement") or ""
    existing = list(identity.get("capability_keywords") or [])
    url = (body.website_url or identity.get("website_url") or "").strip()

    # The annual report, if one is on file. A company's own report describes what it sells in
    # the vocabulary its market uses — which is what a tender title is written in, and what a
    # capability statement usually is not ("expertise in elevator" vs "elevator rope").
    report_text = ""
    report_id = identity.get("annual_report_document_id")
    if report_id:
        doc = next(
            (d for d in db.get_valid_library_docs(user.workspace_id, "0001-01-01")
             if d["id"] == report_id),
            None,
        )
        report_text = (doc or {}).get("text_content") or ""

    site_text, site_error = "", None
    if url:
        try:
            site_text = knowledge.fetch_url_text(url)
        except ApiError as exc:
            # A site that will not load must not fail the whole request — the statement and the
            # existing keywords are still worth reading. Report it so the screen can say which
            # sources were actually used rather than implying the site was one of them.
            site_error = exc.message
            log.warning("keywords: could not read %s (%s)", url, exc.message)

    def deterministic() -> list[dict]:
        return [
            {"keyword": k, "source": "existing", "evidence": "split from your existing keywords"}
            for k in det_keywords.split_long_tail(existing)
        ]

    used_fallback = False
    try:
        # Absolute: `app` and `pipeline` are SIBLING top-level packages, so a relative import
        # from inside `app` reaches beyond the top-level package and raises. `app/discovery/`
        # gets away with `...pipeline` only because it is one level deeper. Caught here as a
        # silent fallback the first time, which is exactly how a model feature ships switched
        # off — the log line was the only evidence.
        from pipeline import keywords as model_keywords

        suggestions = [
            {"keyword": s.keyword, "source": s.source, "evidence": s.evidence}
            for s in model_keywords.suggest(
                statement, existing, "\n\n".join(t for t in (site_text, report_text) if t)
            )
        ]
        # NOT a fallback trigger: the model returning nothing is a legitimate answer (a
        # statement with no product in it, or a page that tried to instruct it). Falling back
        # here would label a correct refusal as an outage on the vendor's screen.
    except Exception as exc:  # noqa: BLE001 — any model failure degrades, never 500s
        log.warning("keywords: model unavailable (%s) — deterministic split only", exc)
        suggestions, used_fallback = deterministic(), True

    # Never propose something they already have; the screen would look like it had found more
    # than it did.
    have = {k.strip().lower() for k in existing}
    suggestions = [s for s in suggestions if s["keyword"] not in have]

    return ok({
        "suggestions": suggestions,
        # What was actually read. A vendor who gave a website and got nothing from it should be
        # told, not left to assume we used it.
        "sources": {
            "capability_statement": bool(statement),
            "existing_keywords": len(existing),
            "website": bool(site_text),
            "website_url": url or None,
            "website_error": site_error,
            "annual_report": bool(report_text),
        },
        "deterministic_only": used_fallback,
    })


@router.get("/api/profile")
def get_profile(user: CurrentUser) -> dict:
    return ok(db.get_profile_context(user.workspace_id))


@router.put("/api/profile")
def update_profile(body: ProfileIn, user: CurrentUser) -> dict:
    """Write the vendor profile.

    This was the terminal dead end of the product: readiness told a bidder to fix an
    eligibility gap "in your Vendor Profile", and that page had no inputs. Every eligibility
    verdict is computed from these rows, so without a write path the readiness loop could
    never close and the only way past a gap was to waive it.

    Collections are omitted-means-unchanged, present-means-replace — so a form can send just
    the section it edited.
    """
    authz.check(user, authz.DRAFT)

    identity = body.model_dump(
        exclude_none=True,
        exclude={"financials", "experience_records", "certifications"},
    )
    if identity:
        db.upsert_vendor_profile(user.workspace_id, identity)

    for field, table in (
        ("financials", "profile_financials"),
        ("experience_records", "experience_records"),
        ("certifications", "certifications"),
    ):
        rows = getattr(body, field)
        if rows is not None:
            db.replace_profile_collection(
                user.workspace_id, table, [r.model_dump(exclude_none=True) for r in rows]
            )

    db.write_audit(user.workspace_id, user.user_id, "profile_updated", "vendor_profile",
                   user.workspace_id, after={"fields": sorted(identity)})
    return ok(db.get_profile_context(user.workspace_id))


@router.post("/api/tenders/{tender_id}/analyze")
def run_analysis(tender_id: str, user: CurrentUser) -> dict:
    tender = db.get_tender(tender_id, user.workspace_id)
    if not tender:
        raise ApiError(404, "TENDER_NOT_FOUND", "tender not found in your workspace")
    if tender.get("status") != "locked":
        # A-FR5: only a locked TOM is a stable basis for deterministic compliance
        raise ApiError(409, "TOM_NOT_LOCKED", "lock the TOM before running eligibility analysis")
    criteria = db.get_criteria(tender_id, user.workspace_id)
    profile = db.get_profile_context(user.workspace_id)
    result = analysis.analyze(criteria, profile)
    db.save_analysis(user.workspace_id, tender_id, result)
    return ok(result)


@router.get("/api/tenders/{tender_id}/analysis")
def get_analysis(tender_id: str, user: CurrentUser) -> dict:
    result = db.get_analysis(tender_id, user.workspace_id)
    if result is None:
        raise ApiError(404, "NO_ANALYSIS", "run eligibility analysis first")
    return ok(result)


def _rubric_for(tender_id: str, user: CurrentUser):
    proposal = db.get_proposal_by_tender(tender_id, user.workspace_id)
    if not proposal:
        raise ApiError(404, "NO_PROPOSAL", "generate a proposal first")
    doc_sections = db.get_sections(proposal["id"], user.workspace_id)
    if not doc_sections:
        raise ApiError(409, "NO_SECTIONS", "generate the proposal document first")
    return proposal, rubric_service.compute(
        doc_sections,
        db.get_criteria(tender_id, user.workspace_id),
        db.get_profile_context(user.workspace_id),
        db.get_valid_library_docs(user.workspace_id, datetime.now(UTC).date().isoformat()),
    )


@router.post("/api/tenders/{tender_id}/rubric")
def run_rubric(tender_id: str, user: CurrentUser) -> dict:
    """Score the DOCUMENT on technical competence.

    Never suppressed, unlike /estimate: this measures an artifact we fully observe rather
    than predicting an external committee, so it needs no historical outcomes (D-AC4 does
    not apply). See app/deterministic/rubric.py for why the two stay separate.
    """
    if not db.get_tender(tender_id, user.workspace_id):
        raise ApiError(404, "TENDER_NOT_FOUND", "tender not found in your workspace")
    _proposal, result = _rubric_for(tender_id, user)
    return ok(rubric_service.payload(result))


@router.post("/api/tenders/{tender_id}/estimate")
def run_estimate(tender_id: str, user: CurrentUser) -> dict:
    tender = db.get_tender(tender_id, user.workspace_id)
    if not tender:
        raise ApiError(404, "TENDER_NOT_FOUND", "tender not found in your workspace")
    analysis_result = db.get_analysis(tender_id, user.workspace_id)
    if analysis_result is None:
        raise ApiError(409, "NO_ANALYSIS", "run eligibility analysis before estimating a score")
    cluster = tender.get("authority") or "unknown"
    count = db.count_cluster_outcomes(user.workspace_id, cluster, _CATEGORY_CLUSTER)

    # Feed the measured document quality in, so the prediction is no longer based purely on
    # a pre-drafting eligibility pass-rate that never read the proposal.
    rubric_total = None
    try:
        _proposal, r = _rubric_for(tender_id, user)
        rubric_total = r.total
    except ApiError:
        pass  # no document yet — fall back to the eligibility-only basis

    result = estimator.estimate(count, analysis_result, rubric_total=rubric_total)
    db.save_estimate(user.workspace_id, tender_id, result)
    return ok(result)


@router.get("/api/tenders/{tender_id}/estimate")
def get_estimate(tender_id: str, user: CurrentUser) -> dict:
    result = db.get_estimate(tender_id, user.workspace_id)
    if result is None:
        raise ApiError(404, "NO_ESTIMATE", "run a score estimate first")
    return ok(result)
