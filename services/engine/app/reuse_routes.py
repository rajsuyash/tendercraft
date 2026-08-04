"""Suggesting a prior answer, and the one path that may put one into a draft (G-FR3/G-AC6).

The value and the danger are the same fact: these are the client's own words, already accepted
by an evaluator. Reused verbatim they carry the voice a bid manager trusts — and any claim
inside them that has since lapsed. So a suggestion is re-run through today's gates twice:
once on GET, so the flags are visible BEFORE accepting, and once on accept, against the
evidence library as it stands at that moment.

`POST /api/proposals/{id}/reuse` is the only endpoint that writes reused text. Every call
records an answer_usages row plus an audit event, which is what makes G-AC6's "zero silent
insertions" a thing a test can assert rather than a promise.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from pipeline.retrieval import chunk_docs, select_evidence

from . import authz, db
from .auth import AuthedUser, get_current_user
from .deterministic.answer_reuse import rank_answers, stale_claims
from .deterministic.drafting import DraftSentence, validate_draft
from .deterministic.shred import split_sentences
from .deterministic.types import SectionKind
from .envelope import ApiError, ok
from .sections import SECTION_SPECS

router = APIRouter()
CurrentUser = Annotated[AuthedUser, Depends(get_current_user)]

_SECTION_KINDS = {s.key: s.kind for s in SECTION_SPECS}


class ReuseIn(BaseModel):
    answer_id: str
    target_kind: Literal["section", "criterion"]
    target: str  # a section key, or a criterion id


def _today() -> str:
    return date.today().isoformat()


def _cite(sentence: str, chunks: list[dict]) -> tuple[str, ...]:
    """Re-attach a citation from TODAY's library, or none at all.

    A reused sentence arrives with citations pointing at a bid we did not index — worthless
    here. So each sentence is re-matched against the current evidence chunks. select_evidence
    deliberately falls back to every document when nothing scores (it must never starve a
    criterion), which would hand back a confident-looking irrelevant citation, so the overlap
    is re-checked before the id is trusted. No overlap, no citation — and validate_draft then
    flags the sentence, which is the correct outcome for a claim we can no longer support.
    """
    best = select_evidence(sentence, chunks, top_k=1)
    if not best:
        return ()
    words = {w for w in sentence.lower().split() if len(w) >= 5}
    text = (best[0].get("text") or "").lower()
    return (best[0]["id"],) if any(w in text for w in words) else ()


def _revalidate(answer_text: str, chunks: list[dict], kind: SectionKind) -> dict:
    """Run a prior answer through the live cite-or-flag gates. Never mutates anything."""
    sentences = [
        DraftSentence(text=s, citations=_cite(s, chunks))
        for s in split_sentences(answer_text) if s.strip()
    ]
    result = validate_draft(sentences, {c["id"] for c in chunks}, kind)
    return {
        "status": result.status,
        "claim_verifiability": round(result.claim_verifiability, 3),
        "flags": [{"text": f.text, "reason": f.reason} for f in result.flags],
        "sentences": [
            {"text": s.text, "citations": list(s.citations), "cls": s.cls.value,
             "requires_citation": s.requires_citation, "is_financial": s.is_financial}
            for s in result.sentences
        ],
    }


def _library_chunks(workspace_id: str) -> list[dict]:
    docs = db.get_valid_library_docs(workspace_id, _today())
    return chunk_docs(
        [{"id": d["id"], "name": d["name"], "text": d.get("text_content", "")} for d in docs]
    )


def _suggest(workspace_id: str, requirement_text: str, section_key: str | None) -> dict:
    answers = db.get_answers_with_bids(workspace_id)
    ranked = rank_answers(requirement_text, answers, section_key=section_key)
    if not ranked:
        return {"suggestions": [], "corpus_size": len(answers)}

    expired = db.get_expired_library_docs(workspace_id, _today())
    chunks = _library_chunks(workspace_id)
    kind = _SECTION_KINDS.get(section_key or "", SectionKind.COMPLIANCE)
    return {
        "corpus_size": len(answers),
        "suggestions": [
            {
                "answer_id": s.answer_id,
                "requirement_text": s.requirement_text,
                "answer_text": s.answer_text,
                "score": s.score,
                # The receipt: never an anonymous paragraph.
                "provenance": {
                    "bid": s.bid_name, "authority": s.authority,
                    "submitted_on": s.submitted_on, "outcome": s.outcome,
                },
                "validation": _revalidate(s.answer_text, chunks, kind),
                # Named, dated, and specific — "unverified" with no reason gets dismissed.
                "stale_claims": [
                    {"quote": c.quote, "document": c.document, "expired_on": c.expired_on}
                    for c in stale_claims(s.answer_text, expired)
                ],
            }
            for s in ranked
        ],
    }


@router.get("/api/tenders/{tender_id}/criteria/{criterion_id}/suggestions")
async def suggest_for_criterion(
    tender_id: str, criterion_id: str, user: CurrentUser
) -> dict:
    """Prior answers for one requirement. Read-only — nothing enters a draft here."""
    criterion = await run_in_threadpool(
        db.get_criterion_in_tender, criterion_id, tender_id, user.workspace_id
    )
    if not criterion:
        raise ApiError(404, "CRITERION_NOT_FOUND", "criterion not found in this tender")
    # .get, not []: the guard's contract is "does this row exist and is it yours", and a
    # criterion with no text simply has nothing to match against — a 500 on the read path of
    # a suggestion panel is a far worse answer than "no suggestions".
    return ok(await run_in_threadpool(
        _suggest, user.workspace_id, criterion.get("verbatim_text") or "", None
    ))


@router.get("/api/proposals/{proposal_id}/sections/{key}/suggestions")
async def suggest_for_section(proposal_id: str, key: str, user: CurrentUser) -> dict:
    if not await run_in_threadpool(db.get_proposal, proposal_id, user.workspace_id):
        raise ApiError(404, "PROPOSAL_NOT_FOUND", "proposal not found in your workspace")
    spec = next((s for s in SECTION_SPECS if s.key == key), None)
    if not spec:
        raise ApiError(404, "SECTION_NOT_FOUND", f"no section named {key}")
    query = f"{spec.heading} {spec.evidence_query}".strip()
    return ok(await run_in_threadpool(_suggest, user.workspace_id, query, key))


def _apply(workspace_id: str, actor: str, proposal_id: str, answer: dict, body: ReuseIn) -> dict:
    chunks = _library_chunks(workspace_id)
    kind = (
        _SECTION_KINDS.get(body.target, SectionKind.NARRATIVE)
        if body.target_kind == "section" else SectionKind.COMPLIANCE
    )
    validation = _revalidate(answer["answer_text"], chunks, kind)

    if body.target_kind == "section":
        db.append_reused_section_text(
            workspace_id, proposal_id, body.target, answer["answer_text"], validation,
        )
    else:
        db.upsert_response(
            workspace_id, proposal_id, body.target,
            {
                "draft_text": answer["answer_text"],
                "sentences": validation["sentences"],
                "draft_status": validation["status"],
                "flags": validation["flags"],
            },
        )

    usage = db.record_answer_usage(
        workspace_id, answer["id"], proposal_id, f"{body.target_kind}:{body.target}", actor,
    )
    db.write_audit(
        workspace_id, actor, "answer_reused", "proposal", proposal_id,
        after={"answer_id": answer["id"], "target": f"{body.target_kind}:{body.target}",
               "flags": len(validation["flags"]), "status": validation["status"]},
    )
    return {
        "usage_id": usage["id"],
        "answer_id": answer["id"],
        "target": f"{body.target_kind}:{body.target}",
        "validation": validation,
        "accepted_at": datetime.now(UTC).isoformat(),
    }


@router.post("/api/proposals/{proposal_id}/reuse")
async def reuse_answer(proposal_id: str, body: ReuseIn, user: CurrentUser) -> dict:
    """Accept one suggested answer into a draft. The ONLY path that writes reused text.

    Nothing is inserted silently: this requires an explicit call naming the answer, it writes
    a usage row and an audit event, and the re-validation runs again here rather than trusting
    whatever the client saw — the library may have changed between the suggestion and the click.
    """
    authz.check(user, authz.DRAFT)
    proposal = await run_in_threadpool(db.get_proposal, proposal_id, user.workspace_id)
    if not proposal:
        raise ApiError(404, "PROPOSAL_NOT_FOUND", "proposal not found in your workspace")
    answer = await run_in_threadpool(db.get_answer, body.answer_id, user.workspace_id)
    if not answer:
        raise ApiError(404, "ANSWER_NOT_FOUND", "answer not found in your workspace")
    if body.target_kind == "section" and body.target not in _SECTION_KINDS:
        raise ApiError(404, "SECTION_NOT_FOUND", f"no section named {body.target}")
    # Every write that binds a caller-supplied id must first prove the id belongs to this
    # workspace: upsert_response would otherwise write a row keyed by a foreign criterion,
    # and _rest uses the service role, so RLS will not catch it (known-pitfalls, ET-6).
    if body.target_kind == "criterion":
        owned = await run_in_threadpool(
            db.get_criterion_in_tender, body.target, proposal["tender_id"], user.workspace_id
        )
        if not owned:
            raise ApiError(404, "CRITERION_NOT_FOUND", "criterion not found in this proposal")

    return ok(await run_in_threadpool(
        _apply, user.workspace_id, user.user_id, proposal_id, answer, body
    ))
