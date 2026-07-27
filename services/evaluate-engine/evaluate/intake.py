"""Bulk intake orchestration (F14/F15/F16). Blocking by design — callers use a threadpool.

This is the module that turns "a folder of files from the portal" into "rows an officer can
read". It is deliberately the only place that knows the order of operations:

    unpack → hash → parse → (OCR illegible pages) → propose attribution → create/attach bid

Two invariants live here and nowhere else, because they are easy to lose in a refactor:

1. **One file failing never stops the others** (F14-AC4). Every per-file step is wrapped; a
   failure writes a named error on that row and the loop continues. A batch that aborts halfway
   leaves the officer worse off than the Excel tracker.
2. **The envelope split happens per file, at ingest** (F14-AC2). A financial document is written
   to bid_financials — the sealed table — the moment it is recognised, never held in a general
   artifact "until later". Bulk intake is many chances to get this wrong, so it gets exactly one
   code path.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from . import db, ingest
from .config import get_settings
from .deterministic.attribution import Attribution, triage_pile
from .envelope import ApiError

log = logging.getLogger("tendercraft.evaluate.intake")


@dataclass(frozen=True)
class IntakeOutcome:
    filename: str
    file_id: str | None
    status: str
    duplicate: bool = False
    error_code: str | None = None
    detail: str | None = None


def expand(filename: str, data: bytes, *, max_files: int, max_bytes: int
           ) -> tuple[list[tuple[str, bytes]], list[str]]:
    """One upload → the files it actually contains, plus any archive entries we refused."""
    if ingest.is_archive(filename, data):
        rejected = ingest.rejected_entries(data)
        return ingest.unpack_archive(data, max_files=max_files, max_bytes=max_bytes), rejected
    return [(filename, data)], []


def _ocr_budget_remaining(tender_id: str, authority_id: str) -> int:
    """Pages left in this tender's vision-OCR allowance (ENV-9).

    Counted from what has already been spent rather than tracked in a counter column: a
    counter drifts the first time an upload fails halfway, and this number decides whether we
    bill.
    """
    spent = sum(len(f.get("ocr_pages") or []) for f in db.bid_files(tender_id, authority_id))
    return max(0, get_settings().ocr_max_pages - spent)


def _read_pages(filename: str, data: bytes, tender_id: str, authority_id: str
                ) -> tuple[list[tuple[int, str]], list[int], list[int], bool]:
    """(pages, ocr'd page numbers, still-illegible page numbers, budget_hit).

    OCR runs only on what the text-layer pass already gave up on — that is the cost control,
    and F16-AC3 asserts a text-layer PDF makes zero vision calls.
    """
    pages = ingest.parse_pages(filename, data)
    legible, illegible = ingest.split_legible(pages)
    if not illegible:
        return pages, [], [], False

    from .pipeline.ocr import ocr_pages

    budget = _ocr_budget_remaining(tender_id, authority_id)
    results = ocr_pages(data, illegible, budget=budget)

    recovered = {r.page_no: r.text for r in results if r.legible}
    merged = [(n, recovered.get(n, t)) for n, t in pages]
    still_illegible = [r.page_no for r in results if not r.legible]
    return (
        merged,
        sorted(recovered),
        sorted(still_illegible),
        any(r.budget_exceeded for r in results),
    )


def ingest_one(tender_id: str, authority_id: str, actor: str | None,
               filename: str, data: bytes) -> IntakeOutcome:
    """One file, end to end. Never raises for a per-file problem — records it and returns."""
    sha = ingest.sha256_of(data)

    existing = db.file_by_hash(tender_id, authority_id, sha)
    if existing:
        # Same bytes, already here. Re-uploading a folder after adding two files to it is
        # normal officer behaviour, not an error to shout about (F14-AC3).
        return IntakeOutcome(filename, existing["id"], existing["status"], duplicate=True)

    row = db.insert_bid_file(authority_id, tender_id, {
        "filename": filename, "sha256": sha, "byte_size": len(data),
        "mime": _mime_for(filename), "status": "normalising",
    })
    if not row:
        return IntakeOutcome(filename, None, "failed", error_code="DB_ERROR")
    file_id = row["id"]

    try:
        pages, ocr_pages_done, illegible, budget_hit = _read_pages(
            filename, data, tender_id, authority_id)
    except ApiError as exc:
        db.update_bid_file(file_id, authority_id, {
            "status": "failed", "error_code": exc.code, "error_detail": exc.message})
        return IntakeOutcome(filename, file_id, "failed", error_code=exc.code,
                             detail=exc.message)
    except Exception as exc:  # noqa: BLE001 — one bad file must never stop the batch
        log.exception("intake failed for %s", filename)
        db.update_bid_file(file_id, authority_id, {
            "status": "failed", "error_code": "PARSE_FAILED", "error_detail": str(exc)[:400]})
        return IntakeOutcome(filename, file_id, "failed", error_code="PARSE_FAILED")

    proposal = _propose(filename, pages)
    bid_id = _bid_for(tender_id, authority_id, proposal.bidder_name, proposal.confidence)

    db.upsert_attribution(authority_id, {
        "file_id": file_id,
        "proposed_bidder_name": proposal.bidder_name,
        "proposed_bid_id": bid_id,
        "proposed_document_type": proposal.document_type,
        "proposed_envelope": proposal.envelope,
        "confidence": str(proposal.confidence),
        "evidence_text": proposal.evidence_text,
        "anchor_page": proposal.anchor_page,
    })

    if bid_id:
        _apply_envelope(tender_id, authority_id, bid_id, proposal.envelope, pages)

    db.update_bid_file(file_id, authority_id, {
        "status": "extracted", "page_count": len(pages),
        "ocr_pages": ocr_pages_done, "illegible_pages": illegible,
        "error_code": "OCR_BUDGET_EXCEEDED" if budget_hit else None,
        "error_detail": ("the vision-OCR page budget for this tender was reached; "
                         "remaining scanned pages were not transcribed") if budget_hit else None,
    })

    db.audit(authority_id, tender_id, actor, "file_ingested", "bid_file", file_id, {
        "filename": filename, "pages": len(pages), "ocr_pages": len(ocr_pages_done),
        "illegible": len(illegible), "proposed_bidder": proposal.bidder_name,
        "confidence": str(proposal.confidence),
    })
    return IntakeOutcome(filename, file_id, "extracted")


def _apply_envelope(tender_id: str, authority_id: str, bid_id: str, envelope: str,
                    pages: list[tuple[int, str]]) -> None:
    """The split, per file, at ingest (F14-AC2).

    A financial document NEVER has its content extracted into bid_responses. Only its total is
    read, and that total is written straight to the sealed table where the RLS policy keyed on
    technical_locked_at makes it unreadable until F9 opens it. This is the one code path for
    financial content in bulk intake, so there is one place to get it wrong and one place to
    check.
    """
    if envelope == "financial":
        from .deterministic.money import extract_total

        amount, _page = extract_total(pages)
        # A null amount is written deliberately: the SEALED ROW must exist so the officer sees
        # a financial envelope was received, even when the figure needs a human to read it.
        db.insert_financial(authority_id, bid_id, float(amount) if amount is not None else None)
        return

    if envelope == "technical":
        _extract_responses(tender_id, authority_id, bid_id, pages)


def _extract_responses(tender_id: str, authority_id: str, bid_id: str,
                       pages: list[tuple[int, str]]) -> None:
    """Answer each published criterion from this document, so screening has something to read.

    Without this, a bulk upload produces bidders with no responses and the screening matrix
    renders every cell as `Not stated` — which looks like fifteen non-compliant bids rather
    than an ingestion that stopped halfway.
    """
    from .pipeline.responder import extract_response

    crits = db.criteria(tender_id, authority_id)
    if not crits:
        return
    legible, _ = ingest.split_legible(pages)
    if not legible:
        return

    rows = []
    for c in crits:
        try:
            r = extract_response(c["id"], c["text"], c.get("compare_value"), legible)
        except Exception:  # noqa: BLE001 — one criterion must not fail the file
            continue
        if r.stated_value is None:
            # No row at all: screening reads a missing response as `Not stated`, a verdict
            # requiring a human — never an automatic failure.
            continue
        rows.append({"bid_id": bid_id, "criterion_id": c["id"],
                     "stated_value": r.stated_value, "excerpt": r.excerpt,
                     "anchor_page": r.anchor_page})
    db.upsert_responses(authority_id, rows)


def _propose(filename: str, pages: list[tuple[int, str]]):
    from .pipeline.attributor import UNATTRIBUTED, propose

    try:
        return propose(filename, pages)
    except Exception:  # noqa: BLE001 — attribution never breaks an upload
        log.exception("attribution failed for %s", filename)
        return UNATTRIBUTED


def _bid_for(tender_id: str, authority_id: str, bidder_name: str | None,
             confidence: Decimal) -> str | None:
    """Find or create the bid this file belongs to — but only if we are confident enough.

    Creating a bid off a low-confidence guess would put a fictional bidder on the screening
    matrix, which is worse than leaving the file in triage: a phantom column looks like a real
    submission and someone has to work out that it is not.
    """
    if not bidder_name or confidence < get_settings().attribution_threshold:
        return None
    existing = db.bid_by_name(tender_id, authority_id, bidder_name)
    if existing:
        return existing["id"]
    created = db.create_bid(authority_id, tender_id, bidder_name)
    return created["id"] if created else None


def _mime_for(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return "application/pdf"
    if lower.endswith((".xlsx", ".xlsm")):
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if lower.endswith(".csv"):
        return "text/csv"
    return "application/octet-stream"


# ── read model ─────────────────────────────────────────────────────────────────
def _attribution_rows(tender_id: str, authority_id: str) -> list[dict]:
    return db.attributions(tender_id, authority_id)


def as_attributions(rows: list[dict]) -> list[Attribution]:
    return [
        Attribution(
            file_id=r["file_id"],
            proposed_bid_id=r.get("proposed_bid_id"),
            confidence=Decimal(str(r["confidence"])) if r.get("confidence") is not None else None,
            confirmed_bid_id=r.get("confirmed_bid_id"),
            confirmed_at=r.get("confirmed_at"),
        )
        for r in rows
    ]


def intake_state(tender_id: str, authority_id: str) -> dict:
    """Everything the intake screen and the triage screen render, from one query set."""
    files = db.bid_files(tender_id, authority_id)
    attr_rows = _attribution_rows(tender_id, authority_id)
    by_file = {r["file_id"]: r for r in attr_rows}
    bids = {b["id"]: b["bidder_name"] for b in db.bids(tender_id, authority_id)}
    threshold = get_settings().attribution_threshold
    pile = set(triage_pile(as_attributions(attr_rows), threshold))

    rows = []
    for f in files:
        a = by_file.get(f["id"], {})
        settled = a.get("confirmed_bid_id") or a.get("proposed_bid_id")
        rows.append({
            "file_id": f["id"], "filename": f["filename"], "status": f["status"],
            "page_count": f.get("page_count"), "byte_size": f.get("byte_size"),
            "mime": f.get("mime"),
            "error_code": f.get("error_code"), "error_detail": f.get("error_detail"),
            "ocr_pages": f.get("ocr_pages") or [],
            "illegible_pages": f.get("illegible_pages") or [],
            "proposed_bidder_name": a.get("proposed_bidder_name"),
            "document_type": a.get("confirmed_document_type") or a.get("proposed_document_type"),
            "envelope": a.get("confirmed_envelope") or a.get("proposed_envelope"),
            "confidence": a.get("confidence"),
            "evidence_text": a.get("evidence_text"),
            "anchor_page": a.get("anchor_page"),
            "confirmed": a.get("confirmed_at") is not None,
            "bidder_name": bids.get(settled) if settled else None,
            "in_triage": f["id"] in pile,
        })

    return {
        "files": rows,
        "triage_count": len(pile),
        "attribution_threshold": str(threshold),
        "bids": [{"id": k, "bidder_name": v} for k, v in sorted(bids.items(), key=lambda x: x[1])],
    }


def triage_blocked(tender_id: str, authority_id: str) -> int:
    """How many files still await a human. 0 means downstream screens may compute."""
    rows = _attribution_rows(tender_id, authority_id)
    return len(triage_pile(as_attributions(rows), get_settings().attribution_threshold))
