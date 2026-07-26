"""HTTP surface. Thin — the gates live in deterministic/, the reads in service.py.

Every endpoint that touches a price calls gates.financial_readable() first. That is the one
line whose failure invalidates a tender, so it appears here explicitly rather than being
implied by a query.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from . import db, service
from .auth import AuthedUser, get_current_user, require_write
from .deterministic import gates
from .envelope import ApiError, ok

router = APIRouter()
CurrentUser = Annotated[AuthedUser, Depends(get_current_user)]


def _eval_or_404(eval_id: str, user: AuthedUser) -> dict:
    ev = db.evaluation(eval_id, user.authority_id)
    if not ev:
        raise ApiError(404, "EVALUATION_NOT_FOUND", "evaluation not found in your authority")
    return ev


# ── identity ───────────────────────────────────────────────────────────────────
@router.get("/api/me")
def me(user: CurrentUser) -> dict:
    a = db.authority(user.authority_id)
    return ok({"user_id": user.user_id, "authority_id": user.authority_id,
               "authority_name": a["name"] if a else None, "role": user.role})


# ── evaluations ────────────────────────────────────────────────────────────────
@router.get("/api/evaluations")
def list_evaluations(user: CurrentUser) -> dict:
    return ok({"evaluations": db.evaluations(user.authority_id)})


@router.get("/api/evaluations/{eval_id}")
def get_evaluation(eval_id: str, user: CurrentUser) -> dict:
    ev = _eval_or_404(eval_id, user)
    crits = db.criteria(eval_id, user.authority_id)
    return ok({
        "evaluation": ev,
        "criteria": crits,
        "unconfirmed": sum(1 for c in crits if not c["confirmed"]),
        "bids": db.bids(eval_id, user.authority_id),
        "members": db.members(user.authority_id),
        "coi": db.coi(eval_id, user.authority_id),
    })


@router.post("/api/evaluations/{eval_id}/framework/lock")
def lock_framework(eval_id: str, user: CurrentUser) -> dict:
    """Irreversible. After this you evaluate against what was published — a criterion cannot
    be invented or reweighted once bids are open."""
    require_write(user)
    ev = _eval_or_404(eval_id, user)
    if ev.get("framework_locked_at"):
        return ok({"already_locked": True, "locked_at": ev["framework_locked_at"]})
    if not user.is_officer:
        raise ApiError(403, "NOT_OFFICER", "only an officer may lock the framework")

    crits = db.criteria(eval_id, user.authority_id)
    unconfirmed = [c for c in crits if not c["confirmed"]]
    if unconfirmed:
        raise ApiError(409, "FRAMEWORK_UNCONFIRMED",
                       f"{len(unconfirmed)} criteria are not confirmed")
    if ev["technical_weight"] + ev["financial_weight"] != 100:
        raise ApiError(409, "WEIGHTS_INVALID", "technical and financial weights must total 100")

    from datetime import UTC, datetime
    now = datetime.now(UTC).isoformat()
    db.update_evaluation(eval_id, user.authority_id,
                         {"framework_locked_at": now, "framework_locked_by": user.user_id})
    db.audit(user.authority_id, eval_id, user.user_id, "framework_locked", "evaluation", eval_id,
             {"criteria": len(crits)})
    return ok({"locked_at": now})


# ── committee ──────────────────────────────────────────────────────────────────
class CoiIn(BaseModel):
    has_interest: bool
    detail: str | None = Field(default=None, max_length=2000)


@router.post("/api/evaluations/{eval_id}/coi")
def file_coi(eval_id: str, body: CoiIn, user: CurrentUser) -> dict:
    _eval_or_404(eval_id, user)
    db.upsert_coi({"authority_id": user.authority_id, "evaluation_id": eval_id,
                   "user_id": user.user_id, "has_interest": body.has_interest,
                   "detail": body.detail})
    db.audit(user.authority_id, eval_id, user.user_id, "coi_filed", "user", user.user_id,
             {"has_interest": body.has_interest})
    return ok({"filed": True})


# ── screening (the activation surface) ─────────────────────────────────────────
@router.get("/api/evaluations/{eval_id}/screening")
def screening(eval_id: str, user: CurrentUser) -> dict:
    _eval_or_404(eval_id, user)
    return ok(service.screening_matrix(eval_id, user.authority_id))


class ResponsivenessIn(BaseModel):
    responsive: bool
    reason: str = Field(min_length=1, max_length=2000)


@router.put("/api/evaluations/{eval_id}/bids/{bid_id}/responsiveness")
def set_responsiveness(eval_id: str, bid_id: str, body: ResponsivenessIn,
                       user: CurrentUser) -> dict:
    """Removing a bidder from a public tender always carries a written reason."""
    require_write(user)
    _eval_or_404(eval_id, user)
    if not body.reason.strip():
        raise ApiError(422, "REASON_REQUIRED", "a written reason is required")
    db.set_responsive(bid_id, user.authority_id, {
        "responsive": body.responsive, "responsive_reason": body.reason.strip(),
        "screened_by": user.user_id})
    db.audit(user.authority_id, eval_id, user.user_id, "responsiveness_decision", "bid", bid_id,
             {"responsive": body.responsive, "reason": body.reason.strip()})
    return ok(service.screening_matrix(eval_id, user.authority_id))


# ── scoring ────────────────────────────────────────────────────────────────────
class ScoreIn(BaseModel):
    bid_id: str
    criterion_id: str
    pre_reveal_mark: float
    final_mark: float
    rationale: str = Field(min_length=1, max_length=4000)
    ai_proposed_mark: float | None = None


@router.get("/api/evaluations/{eval_id}/proposal")
def score_proposal(eval_id: str, user: CurrentUser, bid_id: str, criterion_id: str,
                   own_mark: float | None = None) -> dict:
    """Blind-first (F7-AC3).

    The proposal is not merely hidden in the UI — it is not IN the response until the
    evaluator has committed their own mark. Anchoring otherwise makes the model the de facto
    decider while the audit trail claims a human authored the score.
    """
    _eval_or_404(eval_id, user)
    if own_mark is None:
        raise ApiError(409, "OWN_MARK_REQUIRED",
                       "record your own mark before the proposal is revealed")
    from .pipeline.proposer import propose
    crit = next((c for c in db.criteria(eval_id, user.authority_id)
                 if c["id"] == criterion_id), None)
    if not crit:
        raise ApiError(404, "CRITERION_NOT_FOUND", "criterion not found")
    resp = next((r for r in db.responses(eval_id, user.authority_id)
                 if r["bid_id"] == bid_id and r["criterion_id"] == criterion_id), None)
    return ok(propose(crit, resp))


@router.post("/api/evaluations/{eval_id}/scores")
def submit_score(eval_id: str, body: ScoreIn, user: CurrentUser) -> dict:
    require_write(user)
    ev = _eval_or_404(eval_id, user)
    if ev.get("technical_locked_at"):
        raise ApiError(409, "TECHNICAL_LOCKED", "technical scores are locked")
    if not any(c["user_id"] == user.user_id for c in db.coi(eval_id, user.authority_id)):
        raise ApiError(409, "COI_NOT_FILED", "file your conflict-of-interest declaration first")

    crit = next((c for c in db.criteria(eval_id, user.authority_id)
                 if c["id"] == body.criterion_id), None)
    if not crit:
        raise ApiError(404, "CRITERION_NOT_FOUND", "criterion not found")
    if not (0 <= body.final_mark <= (crit["max_marks"] or 0)):
        raise ApiError(422, "MARK_OUT_OF_RANGE",
                       f"mark must be between 0 and {crit['max_marks']}")

    bid = next((b for b in db.bids(eval_id, user.authority_id) if b["id"] == body.bid_id), None)
    if not bid:
        raise ApiError(404, "BID_NOT_FOUND", "bid not found in this evaluation")
    if not bid.get("responsive"):
        raise ApiError(409, "BID_NON_RESPONSIVE", "a non-responsive bid cannot be scored")

    db.upsert_score({
        "authority_id": user.authority_id, "evaluation_id": eval_id, "bid_id": body.bid_id,
        "criterion_id": body.criterion_id, "evaluator_id": user.user_id,
        "pre_reveal_mark": body.pre_reveal_mark, "ai_proposed_mark": body.ai_proposed_mark,
        "final_mark": body.final_mark, "rationale": body.rationale.strip(),
        "amended_after_reveal": body.pre_reveal_mark != body.final_mark,
    })
    db.audit(user.authority_id, eval_id, user.user_id, "score_submitted", "bid", body.bid_id, {
        "criterion_id": body.criterion_id, "pre_reveal": body.pre_reveal_mark,
        "ai_proposed": body.ai_proposed_mark, "final": body.final_mark,
        "deferred_to_ai": body.ai_proposed_mark is not None
        and body.pre_reveal_mark == body.ai_proposed_mark,
    })
    return ok({"saved": True})


@router.get("/api/evaluations/{eval_id}/technical")
def technical(eval_id: str, user: CurrentUser) -> dict:
    _eval_or_404(eval_id, user)
    return ok(service.technical_state(eval_id, user.authority_id))


class ConsensusIn(BaseModel):
    bid_id: str
    criterion_id: str
    agreed_mark: float
    note: str = Field(min_length=1, max_length=4000)


@router.put("/api/evaluations/{eval_id}/consensus")
def record_consensus(eval_id: str, body: ConsensusIn, user: CurrentUser) -> dict:
    """The chair records ONE agreed mark for a disputed criterion. Individual marks are
    retained — this writes a separate row and never mutates a member's score."""
    require_write(user)
    ev = _eval_or_404(eval_id, user)
    if ev.get("technical_locked_at"):
        raise ApiError(409, "TECHNICAL_LOCKED", "technical scores are locked")
    if not user.is_chair and not user.is_officer:
        raise ApiError(403, "NOT_CHAIR", "only the chair may record a consensus mark")
    crit = next((c for c in db.criteria(eval_id, user.authority_id)
                 if c["id"] == body.criterion_id), None)
    if not crit or not (0 <= body.agreed_mark <= (crit["max_marks"] or 0)):
        raise ApiError(422, "MARK_OUT_OF_RANGE", "consensus mark is outside the criterion range")
    db.upsert_consensus({
        "authority_id": user.authority_id, "evaluation_id": eval_id, "bid_id": body.bid_id,
        "criterion_id": body.criterion_id, "agreed_mark": body.agreed_mark,
        "note": body.note.strip(), "chair_id": user.user_id})
    db.audit(user.authority_id, eval_id, user.user_id, "consensus_recorded", "bid", body.bid_id,
             {"criterion_id": body.criterion_id, "agreed_mark": body.agreed_mark,
              "note": body.note.strip()})
    return ok(service.technical_state(eval_id, user.authority_id))


@router.post("/api/evaluations/{eval_id}/technical/lock")
def lock_technical(eval_id: str, user: CurrentUser) -> dict:
    """The gate that governs the financial envelope. Irreversible in the demo."""
    require_write(user)
    ev = _eval_or_404(eval_id, user)
    if ev.get("technical_locked_at"):
        return ok({"already_locked": True, "locked_at": ev["technical_locked_at"]})
    if not user.is_officer:
        raise ApiError(403, "NOT_OFFICER", "only an officer or chair may lock technical scores")

    state = service.technical_state(eval_id, user.authority_id)
    if state["blockers"]:
        b = state["blockers"][0]
        raise ApiError(409, b["code"], b["detail"])

    from datetime import UTC, datetime
    now = datetime.now(UTC).isoformat()
    db.update_evaluation(eval_id, user.authority_id,
                         {"technical_locked_at": now, "technical_locked_by": user.user_id})
    db.audit(user.authority_id, eval_id, user.user_id, "technical_locked", "evaluation", eval_id,
             {"qualified": [b["bidder_name"] for b in state["bids"] if b["qualified"]]})
    return ok({"locked_at": now})


# ── financial (THE gate) ───────────────────────────────────────────────────────
@router.get("/api/evaluations/{eval_id}/financial")
def financial(eval_id: str, user: CurrentUser) -> dict:
    ev = _eval_or_404(eval_id, user)
    if not gates.financial_readable(ev.get("technical_locked_at")):
        # No amount, no bidder names with prices, nothing. The 409 body carries only what is
        # still outstanding — never a hint of a figure.
        state = service.technical_state(eval_id, user.authority_id)
        raise ApiError(409, "FINANCIAL_SEALED",
                       "financial envelopes are sealed until technical scores are locked: "
                       + ("; ".join(b["detail"] for b in state["blockers"]) or "lock pending"))
    tech = service.technical_state(eval_id, user.authority_id)
    prices = {f["bid_id"]: f for f in db.financials(eval_id, user.authority_id)}
    return ok({"bids": [{
        "bid_id": b["bid_id"], "bidder_name": b["bidder_name"],
        "technically_qualified": b["qualified"],
        # A disqualified bidder's price is never returned — permanently (F9-AC3).
        "amount_inr": (str(prices[b["bid_id"]]["amount_inr"])
                       if b["qualified"] and b["bid_id"] in prices else None),
        "opened_at": prices.get(b["bid_id"], {}).get("opened_at"),
    } for b in tech["bids"]]})


@router.post("/api/evaluations/{eval_id}/financial/open")
def open_financial(eval_id: str, user: CurrentUser) -> dict:
    require_write(user)
    ev = _eval_or_404(eval_id, user)
    if not gates.financial_readable(ev.get("technical_locked_at")):
        db.audit(user.authority_id, eval_id, user.user_id, "financial_open_refused",
                 "evaluation", eval_id, {"reason": "technical scores not locked"})
        raise ApiError(409, "FINANCIAL_SEALED", "technical scores are not locked")
    from datetime import UTC, datetime
    now = datetime.now(UTC).isoformat()
    tech = service.technical_state(eval_id, user.authority_id)
    opened = []
    for b in tech["bids"]:
        if b["qualified"]:
            db.open_financial(b["bid_id"], user.authority_id,
                              {"opened_at": now, "opened_by": user.user_id})
            opened.append(b["bidder_name"])
    db.audit(user.authority_id, eval_id, user.user_id, "financial_opened", "evaluation",
             eval_id, {"bidders": opened})
    return ok({"opened": opened})


# ── result ─────────────────────────────────────────────────────────────────────
@router.get("/api/evaluations/{eval_id}/result")
def result(eval_id: str, user: CurrentUser) -> dict:
    ev = _eval_or_404(eval_id, user)
    if not gates.financial_readable(ev.get("technical_locked_at")):
        raise ApiError(409, "FINANCIAL_SEALED", "technical scores are not locked")
    return ok(service.result(eval_id, user.authority_id))


class TieBreakIn(BaseModel):
    rule_applied: str = Field(min_length=1, max_length=1000)
    outcome: str = Field(min_length=1, max_length=1000)


@router.post("/api/evaluations/{eval_id}/result/tie-break")
def tie_break(eval_id: str, body: TieBreakIn, user: CurrentUser) -> dict:
    """Software never picks the winner. A named human records the published rule and the
    outcome, and it goes to the audit trail."""
    require_write(user)
    _eval_or_404(eval_id, user)
    db.insert_tie_break({"authority_id": user.authority_id, "evaluation_id": eval_id,
                         "rule_applied": body.rule_applied.strip(),
                         "outcome": body.outcome.strip(), "actor_id": user.user_id})
    db.audit(user.authority_id, eval_id, user.user_id, "tie_break_recorded", "evaluation",
             eval_id, {"rule": body.rule_applied.strip(), "outcome": body.outcome.strip()})
    return ok(service.result(eval_id, user.authority_id))


# ── audit ──────────────────────────────────────────────────────────────────────
@router.get("/api/evaluations/{eval_id}/audit")
def audit_trail(eval_id: str, user: CurrentUser) -> dict:
    _eval_or_404(eval_id, user)
    sc = db.scores(eval_id, user.authority_id)
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
    return ok({"events": db.audit_events(eval_id, user.authority_id), "deference": deference})


# ── report ─────────────────────────────────────────────────────────────────────
@router.get("/api/evaluations/{eval_id}/report")
def report(eval_id: str, user: CurrentUser) -> dict:
    from .report import build_report
    ev = _eval_or_404(eval_id, user)
    if not gates.financial_readable(ev.get("technical_locked_at")):
        raise ApiError(409, "RANKING_INCOMPLETE", "technical scores are not locked")
    return ok(build_report(eval_id, user.authority_id))


class QuorumIn(BaseModel):
    quorum: int = Field(ge=1, le=15)


@router.put("/api/evaluations/{eval_id}/quorum")
def set_quorum(eval_id: str, body: QuorumIn, user: CurrentUser) -> dict:
    require_write(user)
    ev = _eval_or_404(eval_id, user)
    if ev.get("technical_locked_at"):
        raise ApiError(409, "TECHNICAL_LOCKED", "technical scores are locked")
    db.update_evaluation(eval_id, user.authority_id, {"quorum": body.quorum})
    db.audit(user.authority_id, eval_id, user.user_id, "quorum_set", "evaluation", eval_id,
             {"quorum": body.quorum})
    return ok({"quorum": body.quorum})

