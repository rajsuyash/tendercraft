"""HTTP surface. Thin — the gates live in deterministic/, the reads in service.py.

Every endpoint that touches a price calls gates.financial_readable() first. That is the one
line whose failure invalidates a tender, so it appears here explicitly rather than being
implied by a query.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from . import db, service
from .auth import AuthedUser, get_current_user, require_write
from .deterministic import gates
from .envelope import ApiError, ok

router = APIRouter()
CurrentUser = Annotated[AuthedUser, Depends(get_current_user)]


def _tender_or_404(tender_id: str, user: AuthedUser) -> dict:
    ev = db.tender(tender_id, user.authority_id)
    if not ev:
        raise ApiError(404, "TENDER_NOT_FOUND", "tender not found in your authority")
    return ev


# ── identity ───────────────────────────────────────────────────────────────────
@router.get("/api/me")
def me(user: CurrentUser) -> dict:
    a = db.authority(user.authority_id)
    return ok({"user_id": user.user_id, "authority_id": user.authority_id,
               "authority_name": a["name"] if a else None, "role": user.role})


# ── the member's queue ─────────────────────────────────────────────────────────
@router.get("/api/my-scoring")
def my_scoring(user: CurrentUser) -> dict:
    """What this evaluator personally still has to score.

    A TEC member is not an officer: they should land on their own work, not on a portfolio
    view. Composed from existing reads rather than a new table — assignment in this product is
    "every responsive bid in a tender you sit on", so there is nothing extra to store.
    """
    out = []
    for ev in db.tenders(user.authority_id):
        crits = [c for c in db.criteria(ev["id"], user.authority_id) if c["kind"] == "technical"]
        responsive = [b for b in db.bids(ev["id"], user.authority_id) if b.get("responsive")]
        if not crits or not responsive:
            continue
        mine = [s for s in db.scores(ev["id"], user.authority_id)
                if s["evaluator_id"] == user.user_id]
        filed = any(c["user_id"] == user.user_id for c in db.coi(ev["id"], user.authority_id))
        total = len(crits) * len(responsive)
        out.append({
            "tender_id": ev["id"],
            "title": ev["title"],
            "tender_number": ev.get("tender_number"),
            "coi_filed": filed,
            "locked": ev.get("technical_locked_at") is not None,
            "bids": [{"bid_id": b["id"], "bidder_name": b["bidder_name"],
                      "scored": sum(1 for s in mine if s["bid_id"] == b["id"]),
                      "criteria": len(crits)} for b in responsive],
            "scored": len(mine),
            "total": total,
        })
    return ok({"tenders": out})


@router.get("/api/members")
def members(user: CurrentUser) -> dict:
    a = db.authority(user.authority_id)
    return ok({"authority": a, "members": db.members(user.authority_id)})


# ── tenders ────────────────────────────────────────────────────────────────
@router.get("/api/dashboard")
def dashboard(user: CurrentUser) -> dict:
    return ok({"tenders": service.dashboard(user.authority_id)})


@router.get("/api/tenders")
def list_tenders(user: CurrentUser) -> dict:
    return ok({"tenders": db.tenders(user.authority_id)})


@router.get("/api/tenders/{tender_id}")
def get_tender(tender_id: str, user: CurrentUser) -> dict:
    ev = _tender_or_404(tender_id, user)
    crits = db.criteria(tender_id, user.authority_id)
    return ok({
        "tender": ev,
        "criteria": crits,
        "unconfirmed": sum(1 for c in crits if not c["confirmed"]),
        "bids": db.bids(tender_id, user.authority_id),
        "members": db.members(user.authority_id),
        "coi": db.coi(tender_id, user.authority_id),
    })


class TenderIn(BaseModel):
    title: str = Field(min_length=3, max_length=500)
    tender_number: str | None = Field(default=None, max_length=120)
    technical_weight: int = Field(default=70, ge=0, le=100)
    financial_weight: int = Field(default=30, ge=0, le=100)
    qualifying_marks: int = Field(default=60, ge=0, le=1000)
    quorum: int = Field(default=3, ge=1, le=15)
    tie_break_rule: str | None = Field(default=None, max_length=1000)


@router.post("/api/tenders")
def create_tender(body: TenderIn, user: CurrentUser) -> dict:
    require_write(user)
    if not user.is_officer:
        raise ApiError(403, "NOT_OFFICER", "only an officer may open a tender")
    if body.technical_weight + body.financial_weight != 100:
        raise ApiError(422, "WEIGHTS_INVALID", "technical and financial weights must total 100")
    row = db.create_tender(user.authority_id, body.model_dump())
    db.audit(user.authority_id, row["id"], user.user_id, "tender_created", "tender", row["id"],
             {"title": body.title})
    return ok({"tender": row})


@router.post("/api/tenders/{tender_id}/document")
async def upload_document(tender_id: str, user: CurrentUser,
                          file: Annotated[UploadFile, File()]) -> dict:
    """Upload the published RFP and extract the criteria it states.

    Runs in a threadpool: pypdf parsing and a model call per page are blocking, and holding the
    event loop for a 200-page tender would stall every other request on the process.
    """
    require_write(user)
    ev = _tender_or_404(tender_id, user)
    if ev.get("framework_locked_at"):
        raise ApiError(409, "FRAMEWORK_LOCKED", "the framework is locked and cannot be changed")

    data = await file.read()
    if not data:
        raise ApiError(400, "EMPTY_FILE", "the uploaded file is empty")
    return ok(await run_in_threadpool(_ingest_document, tender_id, user, data))


def _ingest_document(tender_id: str, user: AuthedUser, data: bytes) -> dict:
    from .ingest import map_pages, parse_pdf_pages, split_legible
    from .pipeline.extractor import extract_from_page

    pages = parse_pdf_pages(data)
    legible, illegible = split_legible(pages)
    per_page = map_pages(extract_from_page, legible)

    rows, order = [], 0
    for found in per_page:
        for c in found:
            order += 1
            rows.append({
                "kind": c.kind, "text": c.text, "max_marks": c.max_marks,
                "compare_kind": c.compare_kind, "compare_op": c.compare_op,
                "compare_value": c.compare_value, "anchor_page": c.anchor_page,
                "anchor_clause": c.anchor_clause, "confidence": c.confidence,
                # Nothing is pre-confirmed. A model-extracted criterion that governs a public
                # tender is confirmed by a person or it does not count.
                "confirmed": False, "order_index": order,
            })
    saved = db.insert_criteria(user.authority_id, tender_id, rows)
    db.audit(user.authority_id, tender_id, user.user_id, "document_ingested", "tender",
             tender_id, {"pages": len(pages), "illegible": len(illegible),
                         "criteria_found": len(saved)})
    return {
        "pages": len(pages),
        "illegible_pages": illegible,
        "criteria_found": len(saved),
        "low_confidence": sum(1 for r in rows if r["confidence"] < 0.80),
    }


class CriterionIn(BaseModel):
    kind: Literal["pq", "technical"] = "pq"
    text: str = Field(min_length=3, max_length=4000)
    max_marks: int = Field(default=0, ge=0, le=1000)
    compare_kind: Literal["numeric", "date", "boolean", "qualitative"] = "qualitative"
    compare_op: Literal[">=", "<=", "=", "present"] | None = None
    compare_value: str | None = Field(default=None, max_length=200)
    anchor_page: int | None = None
    anchor_clause: str | None = Field(default=None, max_length=40)
    confirmed: bool = True


def _guard_framework(tender_id: str, user: AuthedUser) -> None:
    require_write(user)
    ev = _tender_or_404(tender_id, user)
    if ev.get("framework_locked_at"):
        raise ApiError(409, "FRAMEWORK_LOCKED", "the framework is locked and cannot be changed")


@router.post("/api/tenders/{tender_id}/criteria")
def add_criterion(tender_id: str, body: CriterionIn, user: CurrentUser) -> dict:
    """Manual entry — the fallback when extraction misses one, or the RFP is a scan."""
    _guard_framework(tender_id, user)
    existing = db.criteria(tender_id, user.authority_id)
    row = {**body.model_dump(), "confidence": 1.0, "order_index": len(existing) + 1}
    saved = db.insert_criteria(user.authority_id, tender_id, [row])
    return ok({"criterion": saved[0] if saved else None})


@router.put("/api/tenders/{tender_id}/criteria/{criterion_id}")
def edit_criterion(tender_id: str, criterion_id: str, body: CriterionIn,
                   user: CurrentUser) -> dict:
    """Confirm or correct one extracted criterion. Confirming sets confidence to 1.0 — a human
    has now vouched for it, and the sub-0.80 flag should stop nagging."""
    _guard_framework(tender_id, user)
    patch = body.model_dump()
    if patch.get("confirmed"):
        patch["confidence"] = 1.0
    db.update_criterion(criterion_id, user.authority_id, patch)
    return ok({"criteria": db.criteria(tender_id, user.authority_id)})


@router.delete("/api/tenders/{tender_id}/criteria/{criterion_id}")
def remove_criterion(tender_id: str, criterion_id: str, user: CurrentUser) -> dict:
    _guard_framework(tender_id, user)
    db.delete_criterion(criterion_id, user.authority_id)
    return ok({"criteria": db.criteria(tender_id, user.authority_id)})


@router.post("/api/tenders/{tender_id}/bids")
async def upload_bid(tender_id: str, user: CurrentUser,
                     file: Annotated[UploadFile, File()],
                     bidder_name: str = Form(...),
                     amount_inr: float | None = Form(default=None)) -> dict:
    """Upload one bidder's proposal and extract their answer to each published criterion.

    The framework must be locked first. Extracting answers against criteria that could still
    change would mean re-running everything, and worse, would let the criteria be tuned after
    seeing what the bidders said.
    """
    require_write(user)
    ev = _tender_or_404(tender_id, user)
    if not ev.get("framework_locked_at"):
        raise ApiError(409, "FRAMEWORK_NOT_LOCKED",
                       "lock the published framework before uploading bids")
    if ev.get("technical_locked_at"):
        raise ApiError(409, "TECHNICAL_LOCKED", "technical scores are locked")

    data = await file.read()
    if not data:
        raise ApiError(400, "EMPTY_FILE", "the uploaded file is empty")
    return ok(await run_in_threadpool(
        _ingest_bid, tender_id, user, data, bidder_name.strip(), amount_inr))


def _ingest_bid(tender_id: str, user: AuthedUser, data: bytes,
                bidder_name: str, amount: float | None) -> dict:
    from .ingest import parse_pdf_pages, split_legible
    from .pipeline.responder import extract_response

    pages = parse_pdf_pages(data)
    legible, illegible = split_legible(pages)
    bid = db.create_bid(user.authority_id, tender_id, bidder_name)
    crits = db.criteria(tender_id, user.authority_id)

    rows, found = [], 0
    for c in crits:
        r = extract_response(c["id"], c["text"], c.get("compare_value"), legible)
        if r.stated_value is None:
            # No row at all. screening.py reads a missing response as `Not stated`, which is a
            # verdict requiring a human — never an automatic failure.
            continue
        found += 1
        rows.append({"bid_id": bid["id"], "criterion_id": c["id"],
                     "stated_value": r.stated_value, "excerpt": r.excerpt,
                     "anchor_page": r.anchor_page})
    db.upsert_responses(user.authority_id, rows)

    # The financial envelope is written now and sealed by policy until the technical lock.
    if amount is not None and amount > 0:
        db.insert_financial(user.authority_id, bid["id"], amount)

    db.audit(user.authority_id, tender_id, user.user_id, "bid_uploaded", "bid", bid["id"],
             {"bidder": bidder_name, "pages": len(pages), "illegible": len(illegible),
              "criteria_answered": found, "criteria_total": len(crits)})
    return {"bid_id": bid["id"], "bidder_name": bidder_name, "pages": len(pages),
            "illegible_pages": illegible, "criteria_total": len(crits),
            "criteria_answered": found, "not_stated": len(crits) - found}


class ResponseIn(BaseModel):
    stated_value: str | None = Field(default=None, max_length=500)
    excerpt: str | None = Field(default=None, max_length=2000)
    anchor_page: int | None = None


@router.put("/api/tenders/{tender_id}/bids/{bid_id}/responses/{criterion_id}")
def edit_response(tender_id: str, bid_id: str, criterion_id: str, body: ResponseIn,
                  user: CurrentUser) -> dict:
    """The officer confirms or corrects one extracted value before screening trusts it."""
    require_write(user)
    ev = _tender_or_404(tender_id, user)
    if ev.get("technical_locked_at"):
        raise ApiError(409, "TECHNICAL_LOCKED", "technical scores are locked")
    db.upsert_responses(user.authority_id, [{
        "bid_id": bid_id, "criterion_id": criterion_id,
        "stated_value": body.stated_value, "excerpt": body.excerpt,
        "anchor_page": body.anchor_page}])
    db.audit(user.authority_id, tender_id, user.user_id, "response_corrected", "bid", bid_id,
             {"criterion_id": criterion_id, "stated_value": body.stated_value})
    return ok(service.screening_matrix(tender_id, user.authority_id))


@router.post("/api/tenders/{tender_id}/framework/lock")
def lock_framework(tender_id: str, user: CurrentUser) -> dict:
    """Irreversible. After this you evaluate against what was published — a criterion cannot
    be invented or reweighted once bids are open."""
    require_write(user)
    ev = _tender_or_404(tender_id, user)
    if ev.get("framework_locked_at"):
        return ok({"already_locked": True, "locked_at": ev["framework_locked_at"]})
    if not user.is_officer:
        raise ApiError(403, "NOT_OFFICER", "only an officer may lock the framework")

    crits = db.criteria(tender_id, user.authority_id)
    unconfirmed = [c for c in crits if not c["confirmed"]]
    if unconfirmed:
        raise ApiError(409, "FRAMEWORK_UNCONFIRMED",
                       f"{len(unconfirmed)} criteria are not confirmed")
    if ev["technical_weight"] + ev["financial_weight"] != 100:
        raise ApiError(409, "WEIGHTS_INVALID", "technical and financial weights must total 100")

    from datetime import UTC, datetime
    now = datetime.now(UTC).isoformat()
    db.update_tender(tender_id, user.authority_id,
                         {"framework_locked_at": now, "framework_locked_by": user.user_id})
    db.audit(user.authority_id, tender_id, user.user_id, "framework_locked", "tender",
             tender_id, {"criteria": len(crits)})
    return ok({"locked_at": now})


# ── committee ──────────────────────────────────────────────────────────────────
class CoiIn(BaseModel):
    has_interest: bool
    detail: str | None = Field(default=None, max_length=2000)


@router.post("/api/tenders/{tender_id}/coi")
def file_coi(tender_id: str, body: CoiIn, user: CurrentUser) -> dict:
    _tender_or_404(tender_id, user)
    db.upsert_coi({"authority_id": user.authority_id, "tender_id": tender_id,
                   "user_id": user.user_id, "has_interest": body.has_interest,
                   "detail": body.detail})
    db.audit(user.authority_id, tender_id, user.user_id, "coi_filed", "user", user.user_id,
             {"has_interest": body.has_interest})
    return ok({"filed": True})


# ── screening (the activation surface) ─────────────────────────────────────────
@router.get("/api/tenders/{tender_id}/screening")
def screening(tender_id: str, user: CurrentUser) -> dict:
    _tender_or_404(tender_id, user)
    return ok(service.screening_matrix(tender_id, user.authority_id))


class ResponsivenessIn(BaseModel):
    responsive: bool
    reason: str = Field(min_length=1, max_length=2000)


@router.put("/api/tenders/{tender_id}/bids/{bid_id}/responsiveness")
def set_responsiveness(tender_id: str, bid_id: str, body: ResponsivenessIn,
                       user: CurrentUser) -> dict:
    """Removing a bidder from a public tender always carries a written reason."""
    require_write(user)
    _tender_or_404(tender_id, user)
    if not body.reason.strip():
        raise ApiError(422, "REASON_REQUIRED", "a written reason is required")
    db.set_responsive(bid_id, user.authority_id, {
        "responsive": body.responsive, "responsive_reason": body.reason.strip(),
        "screened_by": user.user_id})
    db.audit(user.authority_id, tender_id, user.user_id, "responsiveness_decision", "bid", bid_id,
             {"responsive": body.responsive, "reason": body.reason.strip()})
    return ok(service.screening_matrix(tender_id, user.authority_id))


# ── scoring ────────────────────────────────────────────────────────────────────
class ScoreIn(BaseModel):
    bid_id: str
    criterion_id: str
    pre_reveal_mark: float
    final_mark: float
    rationale: str = Field(min_length=1, max_length=4000)
    ai_proposed_mark: float | None = None


@router.get("/api/tenders/{tender_id}/proposal")
def score_proposal(tender_id: str, user: CurrentUser, bid_id: str, criterion_id: str,
                   own_mark: float | None = None) -> dict:
    """Blind-first (F7-AC3).

    The proposal is not merely hidden in the UI — it is not IN the response until the
    evaluator has committed their own mark. Anchoring otherwise makes the model the de facto
    decider while the audit trail claims a human authored the score.
    """
    _tender_or_404(tender_id, user)
    if own_mark is None:
        raise ApiError(409, "OWN_MARK_REQUIRED",
                       "record your own mark before the proposal is revealed")
    from .pipeline.proposer import propose
    crit = next((c for c in db.criteria(tender_id, user.authority_id)
                 if c["id"] == criterion_id), None)
    if not crit:
        raise ApiError(404, "CRITERION_NOT_FOUND", "criterion not found")
    resp = next((r for r in db.responses(tender_id, user.authority_id)
                 if r["bid_id"] == bid_id and r["criterion_id"] == criterion_id), None)
    return ok(propose(crit, resp))


@router.post("/api/tenders/{tender_id}/scores")
def submit_score(tender_id: str, body: ScoreIn, user: CurrentUser) -> dict:
    require_write(user)
    ev = _tender_or_404(tender_id, user)
    if ev.get("technical_locked_at"):
        raise ApiError(409, "TECHNICAL_LOCKED", "technical scores are locked")
    if not any(c["user_id"] == user.user_id for c in db.coi(tender_id, user.authority_id)):
        raise ApiError(409, "COI_NOT_FILED", "file your conflict-of-interest declaration first")

    crit = next((c for c in db.criteria(tender_id, user.authority_id)
                 if c["id"] == body.criterion_id), None)
    if not crit:
        raise ApiError(404, "CRITERION_NOT_FOUND", "criterion not found")
    if not (0 <= body.final_mark <= (crit["max_marks"] or 0)):
        raise ApiError(422, "MARK_OUT_OF_RANGE",
                       f"mark must be between 0 and {crit['max_marks']}")

    bid = next((b for b in db.bids(tender_id, user.authority_id) if b["id"] == body.bid_id), None)
    if not bid:
        raise ApiError(404, "BID_NOT_FOUND", "bid not found in this tender")
    if not bid.get("responsive"):
        raise ApiError(409, "BID_NON_RESPONSIVE", "a non-responsive bid cannot be scored")

    db.upsert_score({
        "authority_id": user.authority_id, "tender_id": tender_id, "bid_id": body.bid_id,
        "criterion_id": body.criterion_id, "evaluator_id": user.user_id,
        "pre_reveal_mark": body.pre_reveal_mark, "ai_proposed_mark": body.ai_proposed_mark,
        "final_mark": body.final_mark, "rationale": body.rationale.strip(),
        "amended_after_reveal": body.pre_reveal_mark != body.final_mark,
    })
    db.audit(user.authority_id, tender_id, user.user_id, "score_submitted", "bid", body.bid_id, {
        "criterion_id": body.criterion_id, "pre_reveal": body.pre_reveal_mark,
        "ai_proposed": body.ai_proposed_mark, "final": body.final_mark,
        "deferred_to_ai": body.ai_proposed_mark is not None
        and body.pre_reveal_mark == body.ai_proposed_mark,
    })
    return ok({"saved": True})


@router.get("/api/tenders/{tender_id}/technical")
def technical(tender_id: str, user: CurrentUser) -> dict:
    _tender_or_404(tender_id, user)
    return ok(service.technical_state(tender_id, user.authority_id))


class ConsensusIn(BaseModel):
    bid_id: str
    criterion_id: str
    agreed_mark: float
    note: str = Field(min_length=1, max_length=4000)


@router.put("/api/tenders/{tender_id}/consensus")
def record_consensus(tender_id: str, body: ConsensusIn, user: CurrentUser) -> dict:
    """The chair records ONE agreed mark for a disputed criterion. Individual marks are
    retained — this writes a separate row and never mutates a member's score."""
    require_write(user)
    ev = _tender_or_404(tender_id, user)
    if ev.get("technical_locked_at"):
        raise ApiError(409, "TECHNICAL_LOCKED", "technical scores are locked")
    if not user.is_chair and not user.is_officer:
        raise ApiError(403, "NOT_CHAIR", "only the chair may record a consensus mark")
    crit = next((c for c in db.criteria(tender_id, user.authority_id)
                 if c["id"] == body.criterion_id), None)
    if not crit or not (0 <= body.agreed_mark <= (crit["max_marks"] or 0)):
        raise ApiError(422, "MARK_OUT_OF_RANGE", "consensus mark is outside the criterion range")
    db.upsert_consensus({
        "authority_id": user.authority_id, "tender_id": tender_id, "bid_id": body.bid_id,
        "criterion_id": body.criterion_id, "agreed_mark": body.agreed_mark,
        "note": body.note.strip(), "chair_id": user.user_id})
    db.audit(user.authority_id, tender_id, user.user_id, "consensus_recorded", "bid", body.bid_id,
             {"criterion_id": body.criterion_id, "agreed_mark": body.agreed_mark,
              "note": body.note.strip()})
    return ok(service.technical_state(tender_id, user.authority_id))


@router.post("/api/tenders/{tender_id}/technical/lock")
def lock_technical(tender_id: str, user: CurrentUser) -> dict:
    """The gate that governs the financial envelope. Irreversible in the demo."""
    require_write(user)
    ev = _tender_or_404(tender_id, user)
    if ev.get("technical_locked_at"):
        return ok({"already_locked": True, "locked_at": ev["technical_locked_at"]})
    if not user.is_officer:
        raise ApiError(403, "NOT_OFFICER", "only an officer or chair may lock technical scores")

    state = service.technical_state(tender_id, user.authority_id)
    if state["blockers"]:
        b = state["blockers"][0]
        raise ApiError(409, b["code"], b["detail"])

    from datetime import UTC, datetime
    now = datetime.now(UTC).isoformat()
    db.update_tender(tender_id, user.authority_id,
                         {"technical_locked_at": now, "technical_locked_by": user.user_id})
    db.audit(user.authority_id, tender_id, user.user_id, "technical_locked", "tender",
             tender_id, {"qualified": [b["bidder_name"] for b in state["bids"] if b["qualified"]]})
    return ok({"locked_at": now})


# ── financial (THE gate) ───────────────────────────────────────────────────────
@router.get("/api/tenders/{tender_id}/financial")
def financial(tender_id: str, user: CurrentUser) -> dict:
    ev = _tender_or_404(tender_id, user)
    if not gates.financial_readable(ev.get("technical_locked_at")):
        # No amount, no bidder names with prices, nothing. The 409 body carries only what is
        # still outstanding — never a hint of a figure.
        state = service.technical_state(tender_id, user.authority_id)
        raise ApiError(409, "FINANCIAL_SEALED",
                       "financial envelopes are sealed until technical scores are locked: "
                       + ("; ".join(b["detail"] for b in state["blockers"]) or "lock pending"))
    tech = service.technical_state(tender_id, user.authority_id)
    prices = {f["bid_id"]: f for f in db.financials(tender_id, user.authority_id)}
    return ok({"bids": [{
        "bid_id": b["bid_id"], "bidder_name": b["bidder_name"],
        "technically_qualified": b["qualified"],
        # A disqualified bidder's price is never returned — permanently (F9-AC3).
        "amount_inr": (str(prices[b["bid_id"]]["amount_inr"])
                       if b["qualified"] and b["bid_id"] in prices else None),
        "opened_at": prices.get(b["bid_id"], {}).get("opened_at"),
    } for b in tech["bids"]]})


@router.post("/api/tenders/{tender_id}/financial/open")
def open_financial(tender_id: str, user: CurrentUser) -> dict:
    require_write(user)
    ev = _tender_or_404(tender_id, user)
    if not gates.financial_readable(ev.get("technical_locked_at")):
        db.audit(user.authority_id, tender_id, user.user_id, "financial_open_refused",
                 "tender", tender_id, {"reason": "technical scores not locked"})
        raise ApiError(409, "FINANCIAL_SEALED", "technical scores are not locked")
    from datetime import UTC, datetime
    now = datetime.now(UTC).isoformat()
    tech = service.technical_state(tender_id, user.authority_id)
    opened = []
    for b in tech["bids"]:
        if b["qualified"]:
            db.open_financial(b["bid_id"], user.authority_id,
                              {"opened_at": now, "opened_by": user.user_id})
            opened.append(b["bidder_name"])
    db.audit(user.authority_id, tender_id, user.user_id, "financial_opened", "tender",
             tender_id, {"bidders": opened})
    return ok({"opened": opened})


# ── result ─────────────────────────────────────────────────────────────────────
@router.get("/api/tenders/{tender_id}/result")
def result(tender_id: str, user: CurrentUser) -> dict:
    ev = _tender_or_404(tender_id, user)
    if not gates.financial_readable(ev.get("technical_locked_at")):
        raise ApiError(409, "FINANCIAL_SEALED", "technical scores are not locked")
    return ok(service.result(tender_id, user.authority_id))


class TieBreakIn(BaseModel):
    rule_applied: str = Field(min_length=1, max_length=1000)
    outcome: str = Field(min_length=1, max_length=1000)


@router.post("/api/tenders/{tender_id}/result/tie-break")
def tie_break(tender_id: str, body: TieBreakIn, user: CurrentUser) -> dict:
    """Software never picks the winner. A named human records the published rule and the
    outcome, and it goes to the audit trail."""
    require_write(user)
    _tender_or_404(tender_id, user)
    db.insert_tie_break({"authority_id": user.authority_id, "tender_id": tender_id,
                         "rule_applied": body.rule_applied.strip(),
                         "outcome": body.outcome.strip(), "actor_id": user.user_id})
    db.audit(user.authority_id, tender_id, user.user_id, "tie_break_recorded", "tender",
             tender_id, {"rule": body.rule_applied.strip(), "outcome": body.outcome.strip()})
    return ok(service.result(tender_id, user.authority_id))


# ── audit ──────────────────────────────────────────────────────────────────────
@router.get("/api/tenders/{tender_id}/audit")
def audit_trail(tender_id: str, user: CurrentUser) -> dict:
    _tender_or_404(tender_id, user)
    sc = db.scores(tender_id, user.authority_id)
    by_evaluator: dict[str, list] = {}
    for s in sc:
        by_evaluator.setdefault(s["evaluator_id"], []).append(s)
    deference = []
    for uid, rows in by_evaluator.items():
        with_ai = [r for r in rows if r.get("ai_proposed_mark") is not None]
        same = [r for r in with_ai
                if Decimal(str(r["pre_reveal_mark"])) == Decimal(str(r["ai_proposed_mark"]))]
        deference.append({
            "evaluator_id": uid, "scored": len(rows), "with_proposal": len(with_ai),
            "matched_proposal": len(same),
            "rate": round(len(same) / len(with_ai), 2) if with_ai else None,
        })
    return ok({"events": db.audit_events(tender_id, user.authority_id), "deference": deference})


# ── report ─────────────────────────────────────────────────────────────────────
@router.get("/api/tenders/{tender_id}/report")
def report(tender_id: str, user: CurrentUser) -> dict:
    from .report import build_report
    ev = _tender_or_404(tender_id, user)
    if not gates.financial_readable(ev.get("technical_locked_at")):
        raise ApiError(409, "RANKING_INCOMPLETE", "technical scores are not locked")
    return ok(build_report(tender_id, user.authority_id))


class QuorumIn(BaseModel):
    quorum: int = Field(ge=1, le=15)


@router.put("/api/tenders/{tender_id}/quorum")
def set_quorum(tender_id: str, body: QuorumIn, user: CurrentUser) -> dict:
    require_write(user)
    ev = _tender_or_404(tender_id, user)
    if ev.get("technical_locked_at"):
        raise ApiError(409, "TECHNICAL_LOCKED", "technical scores are locked")
    db.update_tender(tender_id, user.authority_id, {"quorum": body.quorum})
    db.audit(user.authority_id, tender_id, user.user_id, "quorum_set", "tender", tender_id,
             {"quorum": body.quorum})
    return ok({"quorum": body.quorum})

