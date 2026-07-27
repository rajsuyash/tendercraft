"""What one bidder may be told about an evaluation (F28). No model in this path — ever.

This is the only place in either product where evaluation data is packaged for someone OUTSIDE
the authority. Everything else is internal; this crosses a boundary and cannot be taken back.

The filter runs BEFORE the letter is generated, not after. Redacting model output is not a
gate — it assumes the model produced exactly the fields you expected to redact, and the one
time it does not is the time a competitor's technical evaluation reaches a bidder's lawyer.

Deny by default. An unrecognised field is refused and reported, never passed through, because
an allowlist that fails open is not an allowlist.

What a losing bidder may see, and why each is safe:
  their own marks, rationale, rank, total     — it is about them
  their own responsiveness verdicts + reasons — they are entitled to know why they were excluded
  the winner's name and the accepted price    — public at award
  the published criteria and weights          — published before bids were invited
What they may never see:
  another bidder's marks, prose, or technical content
  individual committee members' marks or names (only the committee's decision is disclosable)
  consensus notes, variance flags, deliberation
  any other bidder's price
  COI declarations
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Outcome(StrEnum):
    AWARD = "award"
    REGRET = "regret"


# The allowlist. Adding a key here is a decision to disclose it to a bidder — treat a change to
# this tuple as a change to what the authority tells the outside world, because it is one.
PERMITTED_FIELDS: tuple[str, ...] = (
    "tender_title",
    "tender_number",
    "authority_name",
    "bidder_name",
    "outcome",
    "own_rank",
    "own_technical_score",
    "own_combined_score",
    "own_criterion_marks",       # committee marks only — never per-member
    "own_responsiveness",
    "published_criteria",
    "technical_weight",
    "financial_weight",
    "qualifying_marks",
    "winner_name",
    "accepted_price_inr",
    "total_bids_received",       # a count reveals nothing about any individual bidder
)

# Fields that exist upstream and must never reach a recipient. Named explicitly so the refusal
# is a deliberate, reviewable list rather than an accident of what nobody thought to pass.
FORBIDDEN_FIELDS: tuple[str, ...] = (
    "per_member_marks",
    "evaluator_names",
    "consensus_notes",
    "variance_flags",
    "other_bids",
    "other_prices",
    "coi_declarations",
    "deliberation",
    "audit_trail",
)


@dataclass(frozen=True)
class DisclosureResult:
    fields: dict
    refused: tuple[str, ...]


class DisclosureError(Exception):
    """Raised when a disclosure cannot be produced at all."""


def filter_for_recipient(payload: dict) -> DisclosureResult:
    """Reduce a full evaluation payload to what this recipient may see.

    Returns the permitted subset plus the names of everything refused. The refusals are
    returned rather than swallowed so the caller can log them: a growing refusal list means
    someone upstream is trying to pass more than they should.
    """
    fields = {k: v for k, v in payload.items() if k in PERMITTED_FIELDS}
    refused = tuple(sorted(k for k in payload if k not in PERMITTED_FIELDS))
    return DisclosureResult(fields, refused)


def assert_disclosable(ranking_final: bool, tender_state: str) -> None:
    """Refuse to disclose anything at all when the evaluation is not in a state to be told.

    A letter sent before the ranking is final is a statement the authority may have to retract,
    and there is no un-sending it.
    """
    if not ranking_final:
        raise DisclosureError("the ranking is not final")
    if tender_state == "archived":
        raise DisclosureError("this tender is archived")


def outcome_for(rank: int | None, qualified: bool) -> Outcome:
    """Rank 1 among qualified bids is the award; everything else is a regret."""
    return Outcome.AWARD if (qualified and rank == 1) else Outcome.REGRET


def contains_forbidden(text: str, forbidden_values: list[str]) -> tuple[str, ...]:
    """Values that must not appear in generated prose, that do.

    The belt to `filter_for_recipient`'s braces: the filter controls what the model is GIVEN,
    and this checks what came back. A model that was never told a competitor's name cannot
    write it — but asserting that on the produced bytes is what makes F28-AC2 a test rather
    than an assumption.
    """
    lowered = text.lower()
    return tuple(sorted({v for v in forbidden_values if v and v.lower() in lowered}))
