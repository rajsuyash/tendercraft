"""Proposal generation + retrieval endpoints (Module B). Generation runs on a locked TOM."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from pipeline.drafter import draft_response
from pipeline.retrieval import chunk_docs, select_evidence
from pipeline.section_drafter import draft_section

from . import db, docx_export, sections
from .auth import AuthedUser, get_current_user
from .deterministic.drafting import mandatory_coverage
from .envelope import ApiError, ok

router = APIRouter()
CurrentUser = Annotated[AuthedUser, Depends(get_current_user)]


@router.get("/api/library")
def list_library(user: CurrentUser) -> dict:
    today = datetime.now(UTC).date().isoformat()
    docs = db.get_valid_library_docs(user.tenant_id, today)
    return ok({"documents": docs, "count": len(docs)})


def do_generate(tenant_id: str, tender_id: str) -> dict:
    """Draft every criterion from the library and persist responses. Caller ensures the TOM
    is locked. Reused by both /generate and the readiness /prepare orchestration."""
    criteria = db.get_criteria(tender_id, tenant_id)
    today = datetime.now(UTC).date().isoformat()
    evidence = db.get_valid_library_docs(tenant_id, today)
    chunks = chunk_docs(
        [{"id": d["id"], "name": d["name"], "text": d.get("text_content", "")} for d in evidence]
    )
    # A doc the bidder attached to a specific item pins that item's evidence (reliable cites).
    pinned_by = {
        d["criterion_id"]: d.get("document_id")
        for d in db.get_readiness_decisions(tender_id, tenant_id)
        if d.get("document_id")
    }

    proposal = db.create_proposal(tenant_id, tender_id)

    # Draft all criteria concurrently — each is an independent model call; sequential would
    # blow the request budget on a large tender (retry cap keeps cost bounded per call). Each
    # criterion sees only its selected evidence (pinned doc or top-K relevant), not the whole pile.
    def _draft(c: dict):
        ev = select_evidence(c["verbatim_text"], chunks, pinned_by.get(c["id"]))
        return draft_response(c["verbatim_text"], ev)

    with ThreadPoolExecutor(max_workers=6) as pool:
        drafts = list(pool.map(_draft, criteria))

    coverage_rows: list[dict] = []
    total_flags = 0
    for c, drafted in zip(criteria, drafts, strict=True):
        db.upsert_response(
            tenant_id, proposal["id"], c["id"],
            {
                "draft_text": drafted.draft_text,
                "sentences": drafted.sentences,
                "draft_status": drafted.draft_status,
                "flags": drafted.flags,
            },
        )
        total_flags += len(drafted.flags)
        coverage_rows.append(
            {"requirement_level": c["requirement_level"], "draft_status": drafted.draft_status}
        )

    return {
        "proposal_id": proposal["id"],
        "responses": len(criteria),
        "mandatory_coverage": mandatory_coverage(coverage_rows),
        "open_flags": total_flags,
    }


def do_generate_sections(tenant_id: str, tender_id: str) -> dict:
    """Build the full long-form document: assemble the tabular sections, draft the narrative
    ones concurrently. Separate from do_generate because /prepare is the readiness hot path
    and must not grow nine model calls."""
    proposal = db.get_proposal_by_tender(tender_id, tenant_id)
    if not proposal:
        raise ApiError(404, "NO_PROPOSAL", "generate the per-criterion responses first")

    tender = db.get_tender(tender_id, tenant_id) or {}
    criteria = db.get_criteria(tender_id, tenant_id)
    responses = db.get_responses(proposal["id"], tenant_id)
    today = datetime.now(UTC).date().isoformat()
    docs = db.get_valid_library_docs(tenant_id, today)
    profile = db.get_profile_context(tenant_id)
    chunks = chunk_docs(
        [{"id": d["id"], "name": d["name"], "text": d.get("text_content", "")} for d in docs]
    )
    cv_docs = [d for d in docs if (d.get("doc_type") or "") == "cv"]

    # Tender context every narrative section is written against — the criteria ARE the brief.
    context = "\n".join(
        [
            f"Tender: {tender.get('title', '')} ({tender.get('tender_number') or 'no number'})",
            f"Authority: {tender.get('authority') or 'not stated'}",
            "Requirements extracted from the tender document:",
            *(f"- [{c.get('requirement_level')}] {c.get('verbatim_text', '')}" for c in criteria),
        ]
    )

    assembled = {
        "compliance_pq": sections.assemble_compliance_pq(
            profile, profile.get("certifications") or [], today
        ),
        "project_citations": sections.assemble_project_citations(
            profile.get("experience_records") or []
        ),
        "team_composition": sections.assemble_team(cv_docs),
        "cvs": sections.assemble_cvs(cv_docs),
        "deployment": sections.assemble_deployment(cv_docs),
        "deviations": sections.assemble_deviations(),
        "compliance_matrix": sections.assemble_compliance_matrix(criteria, responses),
        "annexures": sections.assemble_annexures(docs, today),
    }

    def _narrative(spec: sections.SectionSpec):
        ev = select_evidence(f"{spec.evidence_query} {spec.heading}", chunks, top_k=12)
        return draft_section(
            spec.key, spec.heading, spec.target_words, context, ev, spec.needs_bidder_evidence
        )

    narrative_specs = [sections.SPEC_BY_KEY[k] for k in sections.NARRATIVE_KEYS]
    with ThreadPoolExecutor(max_workers=5) as pool:
        drafted = list(pool.map(_narrative, narrative_specs))
    drafted_by_key = {d.key: d for d in drafted}

    total_words = 0
    written: list[dict] = []
    for spec in sections.SECTION_SPECS:
        if spec.key in assembled:
            a = assembled[spec.key]
            row = {
                "heading": spec.heading, "order_index": spec.order, "kind": "assembled",
                "body_md": a.body_md,
                "sentences": [
                    {"text": s.text, "citations": list(s.citations), "cls": str(s.cls),
                     "source_ref": s.source_ref, "is_transcluded": s.is_transcluded}
                    for s in a.sentences
                ],
                "status": "drafted", "confidence": 1.0, "flags": [],
                "word_count": len(a.body_md.split()),
            }
        else:
            d = drafted_by_key[spec.key]
            row = {
                "heading": spec.heading, "order_index": spec.order, "kind": "narrative",
                "body_md": d.body_md, "sentences": d.sentences, "status": d.status,
                "confidence": d.confidence, "flags": d.flags, "word_count": d.word_count,
            }
        db.upsert_section(tenant_id, proposal["id"], spec.key, row)
        total_words += row["word_count"]
        written.append({"key": spec.key, "heading": spec.heading, "kind": row["kind"],
                        "status": row["status"], "words": row["word_count"],
                        "flags": len(row["flags"])})

    return {
        "proposal_id": proposal["id"],
        "sections": written,
        "total_words": total_words,
        "placeholders": sum(1 for s in written if s["status"] == "placeholder"),
        "open_flags": sum(s["flags"] for s in written),
    }


@router.post("/api/tenders/{tender_id}/sections/generate")
def generate_sections(tender_id: str, user: CurrentUser) -> dict:
    tender = db.get_tender(tender_id, user.tenant_id)
    if not tender:
        raise ApiError(404, "TENDER_NOT_FOUND", "tender not found in your workspace")
    if tender.get("status") not in ("locked", "exported"):
        raise ApiError(409, "TOM_NOT_LOCKED", "lock the TOM before generating the document")
    return ok(do_generate_sections(user.tenant_id, tender_id))


@router.get("/api/tenders/{tender_id}/sections")
def get_sections(tender_id: str, user: CurrentUser) -> dict:
    proposal = db.get_proposal_by_tender(tender_id, user.tenant_id)
    if not proposal:
        raise ApiError(404, "NO_PROPOSAL", "generate a proposal first")
    rows = db.get_sections(proposal["id"], user.tenant_id)
    return ok({
        "proposal_id": proposal["id"],
        "sections": rows,
        "total_words": sum(r.get("word_count") or 0 for r in rows),
    })


@router.post("/api/tenders/{tender_id}/generate")
def generate_proposal(tender_id: str, user: CurrentUser) -> dict:
    tender = db.get_tender(tender_id, user.tenant_id)
    if not tender:
        raise ApiError(404, "TENDER_NOT_FOUND", "tender not found in your workspace")
    if tender.get("status") != "locked":
        raise ApiError(409, "TOM_NOT_LOCKED", "lock the TOM before generating a proposal")
    return ok(do_generate(user.tenant_id, tender_id))


@router.get("/api/tenders/{tender_id}/proposal")
def get_proposal(tender_id: str, user: CurrentUser) -> dict:
    proposal = db.get_proposal_by_tender(tender_id, user.tenant_id)
    if not proposal:
        raise ApiError(404, "NO_PROPOSAL", "generate a proposal first")
    responses = db.get_responses(proposal["id"], user.tenant_id)
    return ok({"proposal": proposal, "responses": responses})


def _load_export_context(tender_id: str, user: CurrentUser):
    from . import export_service

    proposal = db.get_proposal_by_tender(tender_id, user.tenant_id)
    if not proposal:
        raise ApiError(404, "NO_PROPOSAL", "generate a proposal first")
    criteria = db.get_criteria(tender_id, user.tenant_id)
    responses = db.get_responses(proposal["id"], user.tenant_id)
    approvals = db.get_approvals(proposal["id"], user.tenant_id)
    doc_sections = db.get_sections(proposal["id"], user.tenant_id)
    return export_service, proposal, criteria, responses, approvals, doc_sections


def _matrix_payload(decision, rows) -> dict:
    return {
        "exportable": decision.exportable,
        "hard_blockers": list(decision.hard_blockers),
        "override_blockers": list(decision.override_blockers),
        "override_used": decision.override_used,
        "mandatory_coverage": decision.resolved_mandatory_fraction,
        "rows": [
            {
                "criterion_id": r.criterion_id,
                "requirement_level": r.requirement_level.value,
                "status": r.status.value,
                "has_uncited_financial_claim": r.has_uncited_financial_claim,
            }
            for r in rows
        ],
    }


@router.get("/api/tenders/{tender_id}/compliance-matrix")
def compliance_matrix(tender_id: str, user: CurrentUser) -> dict:
    export_service, proposal, criteria, responses, approvals, doc_sections = _load_export_context(
        tender_id, user
    )
    decision, rows = export_service.evaluate(
        criteria, responses, proposal.get("approvals_required", 2), len(approvals),
        sections=doc_sections,
    )
    return ok({**_matrix_payload(decision, rows), "approvals": approvals,
               "approvals_required": proposal.get("approvals_required", 2)})


@router.post("/api/proposals/{proposal_id}/approve")
def approve(proposal_id: str, user: CurrentUser, stage: str = "review") -> dict:
    # proposal_id comes from the path, so prove ownership BEFORE any write — the write
    # itself runs as the service role and RLS will not stop a foreign id.
    if not db.get_proposal(proposal_id, user.tenant_id):
        raise ApiError(404, "PROPOSAL_NOT_FOUND", "proposal not found in your workspace")
    db.add_approval(user.tenant_id, proposal_id, stage, user.user_id)
    db.write_audit(user.tenant_id, user.user_id, "approval", "proposal", proposal_id,
                   after={"stage": stage})
    return ok({"proposal_id": proposal_id, "stage": stage})


@router.post("/api/proposals/{proposal_id}/sections/{key}/approve")
def approve_section(proposal_id: str, key: str, user: CurrentUser) -> dict:
    """Human sign-off on one narrative section.

    This is the control that replaces cite-or-flag for AI-authored approach prose: nothing
    exists to cite a forward commitment against, so a person signs it instead (B-FR4).
    """
    # Not exploitable today (the PATCH filters by tenant, so a foreign id no-ops) — but a
    # silent success on a failed authorization is still wrong. 404 instead.
    if not db.get_proposal(proposal_id, user.tenant_id):
        raise ApiError(404, "PROPOSAL_NOT_FOUND", "proposal not found in your workspace")
    when = datetime.now(UTC).isoformat()
    db.approve_section(user.tenant_id, proposal_id, key, user.user_id, when)
    db.write_audit(user.tenant_id, user.user_id, "section_approval", "proposal", proposal_id,
                   after={"section": key})
    return ok({"proposal_id": proposal_id, "section": key, "approved_at": when})


@router.get("/api/tenders/{tender_id}/export/docx")
def export_docx(tender_id: str, user: CurrentUser, override: bool = False) -> Response:
    """Download the assembled proposal as .docx.

    The gate runs FIRST — not one byte of python-docx executes for a proposal that may not
    export. This is the only endpoint returning bytes on success; every error path still
    returns the {ok,data,error} envelope (documented in docs/conventions.md).
    """
    export_service, proposal, criteria, responses, approvals, doc_sections = _load_export_context(
        tender_id, user
    )
    if not doc_sections:
        raise ApiError(409, "NO_SECTIONS", "generate the proposal document first")

    decision, _rows = export_service.evaluate(
        criteria, responses, proposal.get("approvals_required", 2), len(approvals),
        admin_override=override, sections=doc_sections,
    )
    if not decision.exportable:
        blockers = list(decision.hard_blockers) + list(decision.override_blockers)
        raise ApiError(409, "EXPORT_BLOCKED", " | ".join(blockers))

    tender = db.get_tender(tender_id, user.tenant_id) or {}
    legal = (db.get_profile_context(user.tenant_id).get("legal_identity")) or {}
    fully_approved = all(
        s.get("approved_at") for s in doc_sections if s.get("kind") == "narrative"
    )

    blob = docx_export.render({
        "tender": tender,
        "bidder": {"name": tender.get("bidder_name") or "Bidder",
                   "cin": legal.get("cin"), "gst": legal.get("gst")},
        "generated_on": datetime.now(UTC).date().isoformat(),
        "approved": fully_approved,
        "sections": [
            {"key": s.get("key"), "heading": s.get("heading"), "body_md": s.get("body_md"),
             "kind": s.get("kind"), "status": s.get("status"),
             "approved": bool(s.get("approved_at"))}
            for s in doc_sections
        ],
    })

    if fully_approved:
        # B-FR4/G-3: the watermark coming OFF is itself an audited event.
        db.write_audit(user.tenant_id, user.user_id, "watermark_removed", "proposal",
                       proposal["id"], after={"sections": len(doc_sections)})
    db.write_audit(user.tenant_id, user.user_id, "export_download", "proposal", proposal["id"],
                   after={"bytes": len(blob), "override_used": decision.override_used})

    safe = re.sub(r"[^A-Za-z0-9_-]+", "-", str(tender.get("tender_number") or tender_id)).strip("-")
    return Response(
        content=blob,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"content-disposition": f'attachment; filename="{safe}-technical-proposal.docx"'},
    )


@router.post("/api/tenders/{tender_id}/export")
def export_proposal(tender_id: str, user: CurrentUser, override: bool = False) -> dict:
    export_service, proposal, criteria, responses, approvals, doc_sections = _load_export_context(
        tender_id, user
    )
    decision, rows = export_service.evaluate(
        criteria, responses, proposal.get("approvals_required", 2), len(approvals),
        admin_override=override, sections=doc_sections,
    )
    if not decision.exportable:
        blockers = list(decision.hard_blockers) + list(decision.override_blockers)
        raise ApiError(409, "EXPORT_BLOCKED", " | ".join(blockers))

    from datetime import UTC, datetime

    when = datetime.now(UTC).isoformat()
    db.mark_exported(proposal["id"], user.tenant_id, when)
    db.write_audit(user.tenant_id, user.user_id, "export", "proposal", proposal["id"],
                   after={"override_used": decision.override_used})
    return ok({"proposal_id": proposal["id"], "exported_at": when,
               "override_used": decision.override_used})
