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
    _require_triage_clear(tender_id, user)
    return ok(service.screening_matrix(tender_id, user.authority_id))


def _require_triage_clear(tender_id: str, user: AuthedUser) -> None:
    """F15-AC4. A matrix computed over a partial set of files reads as complete and is not.

    Refusing is the safe failure: the officer sees a named count and a link to the pile.
    Rendering the matrix anyway would show a finished-looking screen that a bidder can be
    disqualified from.
    """
    from .intake import triage_blocked

    pending = triage_blocked(tender_id, user.authority_id)
    if pending:
        raise ApiError(409, "TRIAGE_PENDING",
                       f"{pending} uploaded file(s) are not yet attributed to a bidder")


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


# ── archive ────────────────────────────────────────────────────────────────────
class ArchiveIn(BaseModel):
    archived: bool
    # A reason is required to archive and ignored to restore. Removing a live procurement from
    # the officer's board is a decision someone should have to justify in one line, and an audit
    # row that records only "archived" explains nothing to whoever reads it a year later.
    reason: str | None = Field(default=None, max_length=1000)


@router.post("/api/tenders/{tender_id}/archive")
def archive(tender_id: str, body: ArchiveIn, user: CurrentUser) -> dict:
    """Archive or restore a tender.

    Archiving is the ONLY removal this product has, and it existed as a database state with no
    way to reach it: `db.tenders()` has always filtered `state != 'archived'` and nothing could
    set that value. The dashboard therefore accumulated abandoned tenders with no product-level
    way to clear them — the demo's own board had one, and it had to be archived with hand-written
    SQL.

    It is deliberately not a delete. `audit_events` is append-only, so a tender that has been
    audited cannot be removed at all — the cascade is refused even to the service role — and a
    procurement record that could be erased is not a record. Archiving hides it from the board
    and keeps every row.

    Reversible, and the restore is audited too: a tender that quietly reappeared would be as
    hard to explain as one that quietly vanished.
    """
    require_write(user)
    if not user.is_officer:
        raise ApiError(403, "NOT_OFFICER", "only an officer or chair may archive a tender")
    ev = _tender_or_404(tender_id, user)

    reason = (body.reason or "").strip()
    if body.archived and not reason:
        raise ApiError(422, "REASON_REQUIRED", "state why this tender is being archived")

    if bool(ev.get("state") == "archived") == body.archived:
        # Already in the requested state. Report it rather than writing a second audit row that
        # says nothing happened.
        return ok({"state": ev.get("state"), "changed": False})

    state = "archived" if body.archived else "active"
    db.update_tender(tender_id, user.authority_id, {"state": state})
    db.audit(user.authority_id, tender_id, user.user_id,
             "tender_archived" if body.archived else "tender_restored",
             "tender", tender_id, {"reason": reason} if body.archived else {})
    return ok({"state": state, "changed": True})


# ── audit ──────────────────────────────────────────────────────────────────────
@router.get("/api/tenders/{tender_id}/audit")
def audit_trail(tender_id: str, user: CurrentUser) -> dict:
    _tender_or_404(tender_id, user)
    sc = db.scores(tender_id, user.authority_id)
    # Resolved to names here rather than in the page: this panel is the one an auditor is
    # invited to read, and "97208a6c…" is not an accountable person. The report already joins
    # members for exactly this reason; the audit trail was the screen that never did.
    names = {m["user_id"]: m.get("full_name") for m in db.members(user.authority_id)}
    by_evaluator: dict[str, list] = {}
    for s in sc:
        by_evaluator.setdefault(s["evaluator_id"], []).append(s)
    deference = []
    for uid, rows in by_evaluator.items():
        with_ai = [r for r in rows if r.get("ai_proposed_mark") is not None]
        same = [r for r in with_ai
                if Decimal(str(r["pre_reveal_mark"])) == Decimal(str(r["ai_proposed_mark"]))]
        deference.append({
            "evaluator_id": uid,
            # Falls back to the id rather than to blank: an unnamed row must still be traceable.
            "evaluator": names.get(uid) or uid,
            "scored": len(rows), "with_proposal": len(with_ai),
            "matched_proposal": len(same),
            "rate": round(len(same) / len(with_ai), 2) if with_ai else None,
        })
    # Loudest first — the whole point of the panel is to surface an evaluator who is deferring.
    deference.sort(key=lambda d: (d["rate"] is None, -(d["rate"] or 0)))
    # The events carry actor_id; nothing was resolving it, so every row on the audit screen
    # rendered without an actor at all. An append-only log that cannot say WHO is not an audit
    # trail — and this is the screen the demo points at when it says "every action with actor
    # and timestamp". Same `names` map the deference panel above already uses.
    events = [
        {**e, "actor": names.get(e.get("actor_id")) or e.get("actor_id")}
        for e in db.audit_events(tender_id, user.authority_id)
    ]
    return ok({"events": events, "deference": deference})


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



# ── bulk intake (F14/F15/F16) ──────────────────────────────────────────────────
@router.post("/api/tenders/{tender_id}/bids/bulk")
async def upload_bulk(tender_id: str, user: CurrentUser,
                      files: Annotated[list[UploadFile], File()]) -> dict:
    """Drop the whole portal download — many files, or one ZIP holding them.

    Runs in a threadpool for the same reason the single upload does: parsing, OCR and a model
    call per file are blocking, and a 25-file archive would hold the event loop for minutes.
    """
    require_write(user)
    ev = _tender_or_404(tender_id, user)
    if not ev.get("framework_locked_at"):
        raise ApiError(409, "FRAMEWORK_NOT_LOCKED",
                       "lock the published framework before uploading bids")
    if ev.get("technical_locked_at"):
        raise ApiError(409, "TECHNICAL_LOCKED", "technical scores are locked")

    payloads: list[tuple[str, bytes]] = []
    for f in files:
        data = await f.read()
        if data:
            payloads.append((f.filename or "unnamed", data))
    if not payloads:
        raise ApiError(400, "EMPTY_FILE", "no readable files in the upload")

    return ok(await run_in_threadpool(_ingest_bulk, tender_id, user, payloads))


def _ingest_bulk(tender_id: str, user: AuthedUser,
                 payloads: list[tuple[str, bytes]]) -> dict:
    from .config import get_settings
    from .intake import expand, ingest_one, intake_state

    s = get_settings()
    expanded: list[tuple[str, bytes]] = []
    rejected: list[str] = []
    for name, data in payloads:
        # An oversized archive raises here and fails the whole request on purpose: the officer
        # must know their upload was refused, not discover later that files are missing.
        found, refused = expand(name, data, max_files=s.archive_max_files,
                                max_bytes=s.archive_max_bytes)
        expanded.extend(found)
        rejected.extend(refused)

    outcomes = [ingest_one(tender_id, user.authority_id, user.user_id, name, data)
                for name, data in expanded]

    db.audit(user.authority_id, tender_id, user.user_id, "bulk_intake", "tender", tender_id,
             {"uploaded": len(payloads), "files": len(expanded),
              "failed": sum(1 for o in outcomes if o.status == "failed"),
              "duplicates": sum(1 for o in outcomes if o.duplicate),
              "rejected_entries": rejected})

    state = intake_state(tender_id, user.authority_id)
    return {
        "received": len(expanded),
        "ingested": sum(1 for o in outcomes if o.status == "extracted"),
        "duplicates": sum(1 for o in outcomes if o.duplicate),
        "failed": [{"filename": o.filename, "error_code": o.error_code, "detail": o.detail}
                   for o in outcomes if o.status == "failed"],
        # Archive entries we refused to read. Named, never silently dropped (F14-ERR3).
        "rejected_entries": rejected,
        **state,
    }


@router.get("/api/tenders/{tender_id}/intake")
def intake(tender_id: str, user: CurrentUser) -> dict:
    """Per-file rows plus the triage count. One read model for both intake screens."""
    from .intake import intake_state

    _tender_or_404(tender_id, user)
    return ok(intake_state(tender_id, user.authority_id))


class AttributionIn(BaseModel):
    # None is a real answer meaning "this file belongs to no bidder" — a covering note, a
    # duplicate, a portal receipt. It settles the file rather than leaving it in the pile.
    bid_id: str | None = None
    new_bidder_name: str | None = Field(default=None, max_length=300)
    document_type: str | None = Field(default=None, max_length=60)
    envelope: str | None = Field(default=None, pattern="^(technical|financial|unknown)$")


@router.put("/api/tenders/{tender_id}/intake/{file_id}/attribution")
def confirm_attribution(tender_id: str, file_id: str, body: AttributionIn,
                        user: CurrentUser) -> dict:
    """A human settles one file. Always wins over the proposal, and is always audited."""
    from .intake import intake_state

    require_write(user)
    _tender_or_404(tender_id, user)

    files = {f["id"]: f for f in db.bid_files(tender_id, user.authority_id)}
    if file_id not in files:
        raise ApiError(404, "FILE_NOT_FOUND", "file not found in this tender")

    bid_id = body.bid_id
    if body.new_bidder_name:
        name = body.new_bidder_name.strip()
        existing = db.bid_by_name(tender_id, user.authority_id, name)
        bid_id = existing["id"] if existing else db.create_bid(
            user.authority_id, tender_id, name)["id"]
    elif bid_id is not None:
        # Never bind a caller-supplied id without checking it belongs to this tender AND
        # authority. The bidder product paid for this exact bug class.
        if not db.get_bid(bid_id, tender_id, user.authority_id):
            raise ApiError(404, "BID_NOT_FOUND", "bid not found in this tender")

    db.upsert_attribution(user.authority_id, {
        "file_id": file_id,
        "confirmed_bid_id": bid_id,
        "confirmed_document_type": body.document_type,
        "confirmed_envelope": body.envelope,
        "confirmed_by": user.user_id,
        "confirmed_at": "now()",
    })
    db.audit(user.authority_id, tender_id, user.user_id, "attribution_confirmed", "bid_file",
             file_id, {"filename": files[file_id]["filename"], "bid_id": bid_id,
                       "envelope": body.envelope})
    return ok(intake_state(tender_id, user.authority_id))


# ── required documents & presence (F17/F18) ────────────────────────────────────
@router.get("/api/tenders/{tender_id}/documents")
def documents(tender_id: str, user: CurrentUser) -> dict:
    """Bidders × required documents. The printed checklist, filled in."""
    from .documents import presence_matrix

    _tender_or_404(tender_id, user)
    return ok(presence_matrix(tender_id, user.authority_id))


class RequirementIn(BaseModel):
    label: str = Field(min_length=2, max_length=300)
    mandatory: bool = True
    accepted_types: list[str] = Field(default_factory=list)
    original_required: bool = False
    criterion_id: str | None = None


class RegisterIn(BaseModel):
    requirements: list[RequirementIn]


@router.put("/api/tenders/{tender_id}/documents/register")
def set_register(tender_id: str, body: RegisterIn, user: CurrentUser) -> dict:
    """Author the checklist. Frozen once any file has been attributed (F17-AC2)."""
    from .documents import presence_matrix

    require_write(user)
    _tender_or_404(tender_id, user)
    if db.bid_files(tender_id, user.authority_id):
        raise ApiError(409, "REGISTER_FROZEN",
                       "bids have already been received; changing the checklist now would "
                       "change who qualifies, retroactively")

    labels = [r.label.strip() for r in body.requirements]
    if len(set(labels)) != len(labels):
        raise ApiError(422, "DUPLICATE_REQUIREMENT", "two requirements share a label")

    rows = [{
        "label": r.label.strip(), "mandatory": r.mandatory,
        "accepted_types": r.accepted_types, "original_required": r.original_required,
        "criterion_id": r.criterion_id, "order_index": i + 1,
    } for i, r in enumerate(body.requirements)]
    saved = db.replace_required_documents(user.authority_id, tender_id, rows)
    db.audit(user.authority_id, tender_id, user.user_id, "register_set", "tender", tender_id,
             {"requirements": len(saved)})
    return ok(presence_matrix(tender_id, user.authority_id))


@router.post("/api/tenders/{tender_id}/documents/derive")
def derive_documents(tender_id: str, user: CurrentUser) -> dict:
    """Propose the checklist from the published criteria. Deterministic keyword matching —
    no model call. The officer edits it before it counts."""
    from .documents import derive_register, presence_matrix

    require_write(user)
    _tender_or_404(tender_id, user)
    if db.bid_files(tender_id, user.authority_id):
        raise ApiError(409, "REGISTER_FROZEN", "bids have already been received")

    proposed = derive_register(db.criteria(tender_id, user.authority_id))
    if not proposed:
        # Never fabricate. An empty proposal is a real answer: nothing in the criteria named a
        # recognisable document, and "supporting documents as applicable" is a row every bidder
        # fails and nobody can satisfy.
        raise ApiError(422, "NOTHING_DERIVABLE",
                       "no recognisable document requirements in the published criteria — "
                       "add them by hand")
    saved = db.replace_required_documents(user.authority_id, tender_id, proposed)
    db.audit(user.authority_id, tender_id, user.user_id, "register_derived", "tender",
             tender_id, {"requirements": len(saved)})
    return ok(presence_matrix(tender_id, user.authority_id))


class PresenceOverrideIn(BaseModel):
    verdict: Literal["present", "missing", "needs_review"]
    reason: str = Field(min_length=3, max_length=1000)


@router.put("/api/tenders/{tender_id}/documents/{requirement_id}/{bid_id}")
def override_presence(tender_id: str, requirement_id: str, bid_id: str,
                      body: PresenceOverrideIn, user: CurrentUser) -> dict:
    """A human corrects one cell — e.g. the EMD arrived as a physical demand draft.

    A reason is mandatory. An override with no 'why' is not an explanation, and this cell can
    be the difference between a bid standing and being rejected.
    """
    from .documents import presence_matrix

    require_write(user)
    _tender_or_404(tender_id, user)
    if not db.get_requirement(requirement_id, tender_id, user.authority_id):
        raise ApiError(404, "REQUIREMENT_NOT_FOUND", "requirement not found in this tender")
    if not db.get_bid(bid_id, tender_id, user.authority_id):
        raise ApiError(404, "BID_NOT_FOUND", "bid not found in this tender")

    db.upsert_document_override(user.authority_id, {
        "requirement_id": requirement_id, "bid_id": bid_id,
        "override_verdict": body.verdict, "override_reason": body.reason.strip(),
        "overridden_by": user.user_id, "overridden_at": "now()",
    })
    db.audit(user.authority_id, tender_id, user.user_id, "presence_overridden",
             "required_document", requirement_id,
             {"bid_id": bid_id, "verdict": body.verdict, "reason": body.reason.strip()})
    return ok(presence_matrix(tender_id, user.authority_id))


# ── technical compliance matrix (F19–F21) ──────────────────────────────────────
@router.get("/api/tenders/{tender_id}/compliance")
def compliance(tender_id: str, user: CurrentUser) -> dict:
    """Every bid against every technical requirement, with page anchors.

    This is EVIDENCE, not a verdict: nothing here writes to responsiveness_decisions, scores or
    consensus_marks, and `not_found` never means non-compliance (F20-AC3/AC4).
    """
    _tender_or_404(tender_id, user)
    return ok(service.compliance_matrix(tender_id, user.authority_id))


# ── award & debrief (F27/F28) ──────────────────────────────────────────────────
@router.get("/api/tenders/{tender_id}/award")
def award(tender_id: str, user: CurrentUser) -> dict:
    """Award and regret letters, one per bidder, each filtered for its own recipient.

    The financial gate applies here too: these letters state an accepted price, so they cannot
    be produced before the technical lock any more than the result page can.
    """
    from .award import build_letters

    ev = _tender_or_404(tender_id, user)
    if not gates.financial_readable(ev.get("technical_locked_at")):
        raise ApiError(409, "FINANCIAL_SEALED",
                       "financial envelopes are sealed until technical scores are locked")
    return ok(build_letters(tender_id, user.authority_id))


# ── authoring a tender (F22–F26) ───────────────────────────────────────────────
class DraftIn(BaseModel):
    title: str = Field(min_length=3, max_length=500)
    tender_number: str | None = Field(default=None, max_length=120)
    category: Literal["goods", "works", "services"] = "goods"
    scope: str | None = Field(default=None, max_length=8000)
    estimated_value: float | None = None
    estimated_annual_value: float | None = None
    submission_window_days: int | None = Field(default=None, ge=0, le=365)
    bid_structure: Literal["single", "two_envelope"] = "two_envelope"
    emd_amount: float | None = None
    emd_exemption_stated: bool = False
    pre_bid_meeting_at: str | None = None
    pre_bid_days_before_deadline: int | None = Field(default=None, ge=0, le=365)
    technical_weight: int = Field(default=70, ge=0, le=100)
    financial_weight: int = Field(default=30, ge=0, le=100)
    qualifying_marks: int | None = Field(default=None, ge=0, le=1000)
    quorum: int = Field(default=3, ge=1, le=15)


@router.get("/api/drafts")
def list_drafts(user: CurrentUser) -> dict:
    return ok({"drafts": db.drafts(user.authority_id)})


@router.post("/api/drafts")
def create_draft(body: DraftIn, user: CurrentUser) -> dict:
    require_write(user)
    if not user.is_officer:
        raise ApiError(403, "NOT_OFFICER", "only an officer may draft a tender")
    if body.technical_weight + body.financial_weight != 100:
        raise ApiError(422, "WEIGHTS_INVALID", "technical and financial weights must total 100")
    row = db.create_draft(user.authority_id, {**body.model_dump(), "created_by": user.user_id})
    return ok({"draft": row})


@router.get("/api/drafts/{draft_id}")
def get_draft(draft_id: str, user: CurrentUser) -> dict:
    from .drafts import draft_state

    return ok(draft_state(draft_id, user.authority_id))


@router.put("/api/drafts/{draft_id}")
def update_draft(draft_id: str, body: DraftIn, user: CurrentUser) -> dict:
    from .drafts import draft_state, invalidate_signoffs

    require_write(user)
    d = db.draft(draft_id, user.authority_id)
    if not d:
        raise ApiError(404, "DRAFT_NOT_FOUND", "draft not found in your authority")
    if d["state"] == "published":
        raise ApiError(409, "DRAFT_PUBLISHED",
                       "a published draft is what bidders received and cannot be edited")
    if body.technical_weight + body.financial_weight != 100:
        raise ApiError(422, "WEIGHTS_INVALID", "technical and financial weights must total 100")

    db.update_draft(draft_id, user.authority_id, body.model_dump())
    invalidate_signoffs(draft_id, user.authority_id)
    return ok(draft_state(draft_id, user.authority_id))


class DraftCriterionIn(BaseModel):
    kind: Literal["pq", "technical"] = "pq"
    text: str = Field(min_length=3, max_length=4000)
    max_marks: int = Field(default=0, ge=0, le=1000)
    evaluation_method: str | None = Field(default=None, max_length=2000)
    compare_kind: Literal["numeric", "date", "boolean", "qualitative"] = "qualitative"
    compare_op: str | None = Field(default=None, max_length=10)
    compare_value: str | None = Field(default=None, max_length=200)
    compare_field: str | None = Field(default=None, max_length=60)


class DraftCriteriaIn(BaseModel):
    criteria: list[DraftCriterionIn]


@router.put("/api/drafts/{draft_id}/criteria")
def set_draft_criteria(draft_id: str, body: DraftCriteriaIn, user: CurrentUser) -> dict:
    from .drafts import draft_state, invalidate_signoffs

    require_write(user)
    d = db.draft(draft_id, user.authority_id)
    if not d:
        raise ApiError(404, "DRAFT_NOT_FOUND", "draft not found in your authority")
    if d["state"] == "published":
        raise ApiError(409, "DRAFT_PUBLISHED", "a published draft cannot be edited")

    rows = [{**c.model_dump(), "order_index": i + 1} for i, c in enumerate(body.criteria)]
    db.replace_draft_criteria(user.authority_id, draft_id, rows)
    invalidate_signoffs(draft_id, user.authority_id)
    return ok(draft_state(draft_id, user.authority_id))


class ReviewerIn(BaseModel):
    reviewer_role: Literal["legal", "finance", "technical", "procurement"]
    reviewer_id: str | None = None
    comment: str | None = Field(default=None, max_length=4000)


@router.post("/api/drafts/{draft_id}/review")
def add_reviewer(draft_id: str, body: ReviewerIn, user: CurrentUser) -> dict:
    """Reviewers are added together and see the draft at the same time — sequential routing is
    why the legal cell reviews late."""
    from .drafts import draft_state

    require_write(user)
    if not db.draft(draft_id, user.authority_id):
        raise ApiError(404, "DRAFT_NOT_FOUND", "draft not found in your authority")
    db.upsert_draft_review(user.authority_id, {
        "draft_id": draft_id, "reviewer_role": body.reviewer_role,
        "reviewer_id": body.reviewer_id, "comment": body.comment})
    db.update_draft(draft_id, user.authority_id, {"state": "in_review"})
    return ok(draft_state(draft_id, user.authority_id))


@router.post("/api/drafts/{draft_id}/review/{reviewer_role}/signoff")
def sign_off(draft_id: str, reviewer_role: str, user: CurrentUser) -> dict:
    from .drafts import draft_state

    require_write(user)
    if not db.draft(draft_id, user.authority_id):
        raise ApiError(404, "DRAFT_NOT_FOUND", "draft not found in your authority")
    db.upsert_draft_review(user.authority_id, {
        "draft_id": draft_id, "reviewer_role": reviewer_role,
        "reviewer_id": user.user_id, "signed_off_at": "now()", "invalidated_at": None})
    db.audit(user.authority_id, None, user.user_id, "draft_signed_off", "draft", draft_id,
             {"role": reviewer_role})
    return ok(draft_state(draft_id, user.authority_id))


class DismissIn(BaseModel):
    rule_id: str = Field(min_length=1, max_length=20)
    target_id: str | None = None
    reason: str = Field(min_length=5, max_length=2000)


@router.post("/api/drafts/{draft_id}/checks/dismiss")
def dismiss_finding(draft_id: str, body: DismissIn, user: CurrentUser) -> dict:
    """Advisory findings only. A blocking rule is not dismissible (D13) — if it could be
    waived by whoever is in a hurry, it was never a gate."""
    from .drafts import draft_state

    require_write(user)
    state = draft_state(draft_id, user.authority_id)
    match = next((f for f in state["findings"]
                  if f["rule_id"] == body.rule_id and f["target_id"] == body.target_id), None)
    if match is None:
        raise ApiError(404, "FINDING_NOT_FOUND", "no such open finding on this draft")
    if match["severity"] == "blocking":
        raise ApiError(409, "FINDING_BLOCKING",
                       "a blocking finding must be fixed, not dismissed")

    db.dismiss_finding(user.authority_id, {
        "draft_id": draft_id, "rule_id": body.rule_id, "target_id": body.target_id,
        "reason": body.reason.strip(), "dismissed_by": user.user_id})
    db.audit(user.authority_id, None, user.user_id, "finding_dismissed", "draft", draft_id,
             {"rule_id": body.rule_id, "reason": body.reason.strip()})
    return ok(draft_state(draft_id, user.authority_id))


@router.post("/api/drafts/{draft_id}/publish")
def publish_draft(draft_id: str, user: CurrentUser) -> dict:
    """Creates the tender WITH its framework. The criteria are never re-keyed."""
    from .drafts import publish

    require_write(user)
    if not user.is_officer:
        raise ApiError(403, "NOT_OFFICER", "only an officer may publish a tender")
    return ok(publish(draft_id, user.authority_id, user.user_id))
