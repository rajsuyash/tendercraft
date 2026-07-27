"""The required-document register (F17) and the presence matrix read model (F18).

The register is the officer's printed checklist as data. It can be proposed from the tender's
own criteria, but the proposal is deterministic keyword matching, not a model call: this list
decides which bidders get chased for paperwork, and it is short enough to read and correct in
a minute. A model here would add a confidence score to a job that does not need one.

Once F26 (authoring) lands, a tender published from a draft carries its register over verbatim
and none of this derivation runs at all — the officer already wrote the list when they wrote
the tender.
"""

from __future__ import annotations

from . import db
from .config import get_settings
from .deterministic.attribution import files_for_bid, triage_pile
from .deterministic.presence import (
    AttributedFile,
    Presence,
    Requirement,
    apply_override,
    missing_mandatory,
    screen_bid_documents,
)
from .intake import as_attributions

# Keyword → (label, accepted document types, original usually required at submission).
# Ordered: the first match wins, so put the specific before the general.
_DERIVATIONS: list[tuple[tuple[str, ...], str, tuple[str, ...], bool]] = [
    (("earnest money", "emd", "bid security"), "Earnest Money Deposit", ("emd",), True),
    (("iso 9001",), "ISO 9001 certificate", ("certificate",), False),
    (("iso ",), "ISO certificate", ("certificate",), False),
    (("affidavit", "undertaking", "self declaration", "self-declaration"),
     "Affidavit / undertaking", ("affidavit",), True),
    (("power of attorney",), "Power of attorney", ("authorisation",), True),
    (("authorisation", "authorization", "maf", "oem"),
     "Manufacturer's authorisation", ("authorisation",), False),
    (("audited", "balance sheet", "profit and loss", "turnover", "financial statement"),
     "Audited financial statements", ("financial_statement",), False),
    (("completion certificate", "similar work", "past experience", "experience"),
     "Experience / completion certificates", ("experience_certificate",), False),
    (("pan",), "PAN card", ("certificate", "form"), False),
    (("gst",), "GST registration", ("certificate", "form"), False),
    (("udyam", "msme", "mse"), "Udyam / MSME registration", ("certificate",), False),
    (("registration", "incorporation", "cin"), "Registration / incorporation proof",
     ("certificate", "form"), False),
]


def derive_register(criteria: list[dict]) -> list[dict]:
    """Propose a checklist from the published criteria. The officer edits it before it counts.

    Deliberately conservative: a criterion that names no recognisable document produces no
    entry. Inventing "supporting documents as applicable" would put a row on the matrix that
    every bidder fails and nobody can satisfy.
    """
    seen: set[str] = set()
    out: list[dict] = []
    for c in criteria:
        text = (c.get("text") or "").lower()
        evidence = (c.get("evidence_required") or "").lower()
        haystack = f"{text} {evidence}"
        for needles, label, types, original in _DERIVATIONS:
            if any(n in haystack for n in needles):
                if label in seen:
                    break
                seen.add(label)
                out.append({
                    "label": label,
                    "mandatory": c.get("kind") == "pq",
                    "criterion_id": c.get("id"),
                    "accepted_types": list(types),
                    "original_required": original,
                    "order_index": len(out) + 1,
                })
                break
    return out


def _requirements(rows: list[dict]) -> list[Requirement]:
    return [
        Requirement(id=r["id"], label=r["label"], mandatory=r["mandatory"],
                    accepted_types=tuple(r.get("accepted_types") or ()))
        for r in rows
    ]


def presence_matrix(tender_id: str, authority_id: str) -> dict:
    """Bidders × required documents. Computed fresh every time, never stored.

    Storing the computed verdict would let it disagree with the files the moment one is
    re-attributed — and a stale "missing" is exactly the cell that removes a bidder.
    """
    threshold = get_settings().attribution_threshold
    reqs_rows = db.required_documents(tender_id, authority_id)
    reqs = _requirements(reqs_rows)
    bids = db.bids(tender_id, authority_id)

    attr_rows = db.attributions(tender_id, authority_id)
    # One mapping from row to Attribution, owned by intake.py. Two copies of it would drift,
    # and the thing that drifts is which files count as a bidder's — i.e. who looks compliant.
    attributions = as_attributions(attr_rows)
    by_file = {r["file_id"]: r for r in attr_rows}
    files_meta = {f["id"]: f for f in db.bid_files(tender_id, authority_id)}
    unresolved = set(triage_pile(attributions, threshold))
    overrides = {(o["requirement_id"], o["bid_id"]): o
                 for o in db.document_presence(tender_id, authority_id)}

    rows = []
    for b in bids:
        owned = files_for_bid(attributions, b["id"], threshold)
        files = []
        for fid in owned:
            a = by_file.get(fid, {})
            files.append(AttributedFile(
                file_id=fid,
                document_type=a.get("confirmed_document_type") or a.get("proposed_document_type"),
                confirmed=a.get("confirmed_at") is not None,
            ))
        # A bidder is "unresolved" only if a file that MIGHT be theirs is still in the pile.
        # Being strict here would mark every bidder needs-review whenever any file is pending,
        # which makes the matrix useless; being loose would mark a bidder missing on our own
        # unfinished work. The honest middle: any unattributed file could belong to anyone,
        # so it blocks a MISSING verdict for every bidder until it is settled.
        cells = screen_bid_documents(reqs, files, bid_id=b["id"],
                                     has_unresolved_files=bool(unresolved))
        cells = tuple(
            apply_override(c, (overrides.get((c.requirement_id, b["id"])) or {}).get(
                "override_verdict"),
                (overrides.get((c.requirement_id, b["id"])) or {}).get("override_reason"))
            for c in cells
        )
        rows.append({
            "bid_id": b["id"], "bidder_name": b["bidder_name"],
            "responsive": b.get("responsive"),
            "cells": [{
                "requirement_id": c.requirement_id,
                "verdict": str(c.verdict),
                "matched_file_id": c.matched_file_id,
                "matched_filename": (files_meta.get(c.matched_file_id) or {}).get("filename"),
                "reason": c.reason,
                "overridden": c.overridden,
            } for c in cells],
            "missing_mandatory": list(missing_mandatory(cells, reqs)),
        })

    return {
        "requirements": [{
            "id": r["id"], "label": r["label"], "mandatory": r["mandatory"],
            "accepted_types": r.get("accepted_types") or [],
            "original_required": r["original_required"],
            "criterion_id": r.get("criterion_id"),
        } for r in reqs_rows],
        "bids": rows,
        "frozen": bool(db.bid_files(tender_id, authority_id)),
        "unresolved_files": len(unresolved),
        "complete": sum(
            1 for row in rows
            for c in row["cells"] if c["verdict"] == str(Presence.PRESENT)
        ),
        "total_cells": len(reqs_rows) * len(bids),
    }
