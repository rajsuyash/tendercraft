"""Harvest a finished proposal into the answer library (the export-time learning loop).

`POST /api/tenders/{id}/export` used to write an audit row and stop. The document the client
had just spent two weeks on — approved section by section, corrected by hand, gated by the
export blocker — taught the system nothing, while the identical file re-uploaded through
`POST /api/past-bids` would have been mined perfectly. This module closes that.

Three deliberate differences from the upload path (`past_bids_routes._process`), each of which
is a correctness point rather than a shortcut:

1. **No document parse, no model call.** Upload mining exists to recover structure from a blob.
   Our own proposal is not a blob: the section carries its own heading and its own semantic
   key. `deterministic/learning.py::harvestable` is the whole extraction.

2. **No `library_documents` row.** Two reasons, and the second is the important one.
   The retriever would then treat our own draft as citable evidence — a sentence "cited" to a
   document that is itself an unverified draft is circular grounding, and cite-or-flag would
   report it as satisfied. And `get_past_bid_texts` feeds the house-style measurement, which
   must be measured from how the CLIENT writes; generated prose in that corpus would converge
   the style brief onto the drafter's own voice. Style learns from human edits instead
   (deterministic/style.py + the edit deltas), which is the signal that actually means
   something.

3. **Harvest never fails an export.** The export gate is the product's safety story
   (B-AC4/E-AC2). A learning feature does not get to block a submission deadline because a
   mining query timed out. Errors are logged and swallowed; the caller is told what happened.
"""

from __future__ import annotations

import logging

from . import db
from .deterministic.learning import harvestable

log = logging.getLogger(__name__)


def harvest_proposal(workspace_id: str, proposal_id: str, actor: str | None) -> dict:
    """Mine the human-signed sections of an exported proposal into the answer library.

    Idempotent. A re-export updates the same past_bid and merges its answers in place
    (`upsert_answers` conflicts on workspace+bid+requirement, and our headings are stable
    because they come from SECTION_SPECS). Nothing is ever deleted: `answer_usages` cascades
    from `answers`, so a delete-and-rebuild would destroy the G-AC6 acceptance receipts —
    which are exactly the record that proves no suggestion entered a draft unaccepted.
    """
    sections = db.get_sections(proposal_id, workspace_id)
    pairs = harvestable(sections)
    if not pairs:
        # Not an error. A proposal exported with nothing individually approved has nothing to
        # teach, and saying so beats writing an empty bid row that later looks like a bug.
        return {"harvested": 0, "past_bid_id": None,
                "note": "no human-approved narrative sections to learn from"}

    bid = db.get_past_bid_by_proposal(workspace_id, proposal_id)
    if not bid:
        proposal = db.get_proposal(proposal_id, workspace_id) or {}
        tender = db.get_tender(proposal.get("tender_id") or "", workspace_id) or {}
        bid = db.create_past_bid(
            workspace_id,
            {
                "name": tender.get("title") or "Untitled proposal",
                "authority": tender.get("authority"),
                "tender_number": tender.get("tender_number"),
                # The day it left our building. Not an award date, and not a claim that a
                # buyer received it — `outcome` stays 'unknown' until a human says otherwise,
                # because a guessed win would steer every future suggestion (0027).
                "submitted_on": None,
                "outcome": "unknown",
                "origin": "generated",
                "proposal_id": proposal_id,
            },
            actor,
        )

    stored = db.upsert_answers(workspace_id, bid["id"], [
        {
            "requirement_text": p.requirement_text,
            "answer_text": p.answer_text,
            "section_key": p.section_key,
            "mined_by": p.provenance,
        }
        for p in pairs
    ])
    db.write_audit(
        workspace_id, actor, "proposal_harvested", "past_bid", bid["id"],
        after={"proposal_id": proposal_id, "answers": len(stored),
               "edited": sum(1 for p in pairs if p.provenance == "edited")},
    )
    return {
        "harvested": len(stored),
        "past_bid_id": bid["id"],
        # Named so the user can judge the harvest rather than trust it — same reason the
        # upload path returns `sections_recognised`.
        "sections": sorted(p.section_key for p in pairs),
        "note": "",
    }


def harvest_quietly(workspace_id: str, proposal_id: str, actor: str | None) -> dict:
    """`harvest_proposal`, but a failure can never take an export down with it."""
    try:
        return harvest_proposal(workspace_id, proposal_id, actor)
    except Exception:  # noqa: BLE001 — deliberate: learning is never worth a failed export
        log.exception("harvest failed for proposal %s", proposal_id)
        return {"harvested": 0, "past_bid_id": None, "note": "harvest deferred"}
