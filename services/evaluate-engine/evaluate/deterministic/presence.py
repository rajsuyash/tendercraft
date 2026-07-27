"""Was the required document received? (F18). No model in this path — ever.

This answers exactly one question per (bid × requirement): is there a file attributed to this
bidder whose document type satisfies this requirement? That is arithmetic over a set, so it
lives here and it is 100% branch covered.

It does NOT answer whether the document is adequate — whether the EMD is the right amount,
whether the affidavit is correctly executed, whether the certificate is genuine. That is a
human judgement (D12), and a UI that blurs the two rebuilds the uneven-rejection problem this
feature exists to remove.

The three verdicts are not symmetric, and the asymmetry is the whole design:

  PRESENT       a matching file is attributed to this bidder
  MISSING       no matching file, AND nothing about this bidder is still unresolved
  NEEDS_REVIEW  we cannot say — a file is still in triage, or a match is uncertain

`MISSING` is the only verdict that can cost a bidder their bid, so it is the only one that
requires us to be certain. Anything unresolved degrades to NEEDS_REVIEW, never to MISSING.
This mirrors `screening.Verdict.NOT_STATED` deliberately: same trap, same answer.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Presence(StrEnum):
    PRESENT = "present"
    MISSING = "missing"
    NEEDS_REVIEW = "needs_review"   # never silently a MISSING — an intake miss is not a defect


@dataclass(frozen=True)
class Requirement:
    id: str
    label: str
    mandatory: bool = True
    # Empty means "any document satisfies this" — used for requirements an officer typed but
    # has not classified. It must not mean "nothing satisfies this".
    accepted_types: tuple[str, ...] = ()


@dataclass(frozen=True)
class AttributedFile:
    file_id: str
    document_type: str | None
    # True when a human settled this file's type, false when the model proposed it.
    confirmed: bool = False


@dataclass(frozen=True)
class PresenceCell:
    requirement_id: str
    bid_id: str
    verdict: Presence
    matched_file_id: str | None = None
    reason: str | None = None
    overridden: bool = False


def _matches(req: Requirement, f: AttributedFile) -> bool:
    if not req.accepted_types:
        return True
    return f.document_type in req.accepted_types


def evaluate_requirement(req: Requirement, files: list[AttributedFile], *,
                         bid_id: str, has_unresolved_files: bool) -> PresenceCell:
    """One cell of the presence matrix."""
    matches = [f for f in files if _matches(req, f)]

    if matches:
        # Prefer a human-confirmed match, so the cell cites the strongest evidence available.
        best = next((f for f in matches if f.confirmed), matches[0])
        return PresenceCell(req.id, bid_id, Presence.PRESENT, best.file_id)

    if has_unresolved_files:
        # The decisive guard (F18-AC4). Files for this bidder are still in triage, so "we did
        # not find it" cannot be distinguished from "we have not looked at everything yet".
        return PresenceCell(
            req.id, bid_id, Presence.NEEDS_REVIEW, None,
            "this bidder has files still awaiting attribution")

    return PresenceCell(req.id, bid_id, Presence.MISSING, None)


def screen_bid_documents(requirements: list[Requirement], files: list[AttributedFile], *,
                         bid_id: str, has_unresolved_files: bool) -> tuple[PresenceCell, ...]:
    return tuple(
        evaluate_requirement(r, files, bid_id=bid_id, has_unresolved_files=has_unresolved_files)
        for r in requirements
    )


def apply_override(cell: PresenceCell, verdict: str | None, reason: str | None) -> PresenceCell:
    """A human's decision replaces the computed one, and is marked as such.

    The computed verdict is never stored — it is recomputed from the register and the files
    every time — so an override has to be layered on top rather than written over it. That is
    what keeps the matrix honest when a file is later re-attributed.
    """
    if not verdict:
        return cell
    return PresenceCell(cell.requirement_id, cell.bid_id, Presence(verdict),
                        cell.matched_file_id, reason, overridden=True)


def missing_mandatory(cells: tuple[PresenceCell, ...],
                      requirements: list[Requirement]) -> tuple[str, ...]:
    """Mandatory requirements this bid is definitively missing.

    PROPOSES a finding; it never decides. Removing a bidder still runs through the officer's
    written reason and the audit trail (F18-AC3, base F6-AC3).
    """
    mandatory = {r.id for r in requirements if r.mandatory}
    return tuple(c.requirement_id for c in cells
                 if c.verdict is Presence.MISSING and c.requirement_id in mandatory)
