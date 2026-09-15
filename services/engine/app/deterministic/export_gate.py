"""Export compliance gate — B-AC4 + E-AC2 (tendercraft-PRD.md Modules B, E).

Two distinct classes of blocker, because they have different override semantics:

  HARD (never overridable) — an uncited financial/numeric claim (B-AC4, ET-3).
      A hallucinated money figure can never reach a submitted document, full stop.

  OVERRIDE-ABLE (logged admin path only, E-AC2) — open placeholders (B-FR2),
      unverified claims (B-FR1), missing mandatory coverage, incomplete approvals.
      An admin may override these, and the override is surfaced so the caller logs it
      (E-FR5) — the gate reports it, never hides it.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from .matrix import coverage
from .types import ComplianceRow, CoverageStatus, RequirementLevel, SectionKind

_BLOCKING_STATUSES = {CoverageStatus.PLACEHOLDER, CoverageStatus.UNVERIFIED, CoverageStatus.MISSING}


def content_hash(sections: Iterable[Mapping]) -> str:
    """What a stage approval is signing, as one stable string.

    An approval row recorded who signed and when, and nothing about WHAT. Editing a section
    clears that section's own approval, but the proposal-level chain survived — so a document
    could be signed through every stage, rewritten afterwards, and still export as approved.

    Ordered by `key` rather than by `order_index`, because reordering sections does not
    change what anybody agreed to; changing their words does. Same idiom as
    `discovery/relevance.py::input_hash` and `inbound_routes._digest`: sha256 over
    "\x1f"-joined fields, so a body ending where the next key begins cannot collide with a
    different split.
    """
    parts: list[str] = []
    for s in sorted(sections, key=lambda x: str(x.get("key") or "")):
        parts.append(str(s.get("key") or ""))
        parts.append(str(s.get("body_md") or ""))
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SectionRow:
    """One long-form document section, as the gate sees it."""

    key: str
    kind: SectionKind
    status: str  # 'drafted' | 'placeholder' | 'unverified'
    approved: bool = False
    narrative_sentences: int = 0
    has_uncited_financial_claim: bool = False


@dataclass(frozen=True)
class ApprovalChain:
    required: int
    completed: int
    # Distinct human approvers. Defaulted so every existing caller and test compiles; when
    # it is left at 0 the SoD check is inert rather than wrongly blocking.
    distinct_approvers: int = 0

    def is_complete(self) -> bool:
        return self.completed >= self.required

    def has_segregation_of_duties(self) -> bool:
        """E-FR1: N stages must be signed by N different people.

        Counting rows alone made the chain a counter, not a control — one person could
        satisfy every stage. Inert until a caller supplies distinct_approvers.
        """
        return self.distinct_approvers == 0 or self.distinct_approvers >= self.required


@dataclass(frozen=True)
class ExportDecision:
    exportable: bool
    hard_blockers: tuple[str, ...] = field(default_factory=tuple)
    override_blockers: tuple[str, ...] = field(default_factory=tuple)
    override_used: bool = False
    # Fraction of mandatory rows GENUINELY resolved at export time (COVERED or MANUAL).
    # NOT the PRD B-AC2 draft-time coverage figure — B-AC2 counts open placeholders as
    # "addressed", this deliberately does not (an open placeholder blocks export).
    resolved_mandatory_fraction: float = 0.0


def evaluate_export(
    rows: Sequence[ComplianceRow],
    approvals: ApprovalChain,
    admin_override: bool = False,
    sections: Sequence[SectionRow] = (),
) -> ExportDecision:
    """Decide whether a proposal may export, separating hard from override-able blockers.

    `sections` defaults to empty so callers that predate the document layer are unaffected.
    """
    hard: list[str] = []
    override: list[str] = []

    for row in rows:
        if row.has_uncited_financial_claim:
            hard.append(
                f"{row.criterion_id}: uncited financial/numeric claim (B-AC4, non-overridable)"
            )

    for s in sections:
        # Without this the document layer would be a hole straight around B-AC4 — a figure
        # smuggled into the methodology section would never reach the compliance matrix.
        if s.has_uncited_financial_claim:
            hard.append(
                f"section {s.key}: uncited financial/numeric claim (B-AC4, non-overridable)"
            )
        if s.status == "placeholder":
            override.append(f"section {s.key}: placeholder not resolved (B-FR2)")
        # The same status set the per-criterion rows are judged by. It was applied to
        # ComplianceRow only, so a long-form section carrying an unverified claim — a
        # sentence cite-or-flag could not resolve to any retrieved chunk — passed the gate
        # silently while the identical status on a criterion blocked it.
        if s.status == "unverified":
            override.append(f"section {s.key}: unverified claim with no resolving source (B-FR1)")
        # AI-authored narrative can't be policed by cite-or-flag — nothing exists to cite —
        # so human sign-off is the control that replaces it (B-FR4).
        if s.kind is SectionKind.NARRATIVE and s.narrative_sentences > 0 and not s.approved:
            override.append(
                f"section {s.key}: {s.narrative_sentences} AI-authored sentences "
                "not human-approved (B-FR4)"
            )

    for row in rows:
        if (
            row.requirement_level is RequirementLevel.MANDATORY
            and row.status in _BLOCKING_STATUSES
        ):
            override.append(
                f"{row.criterion_id}: {row.status.value} on mandatory criterion (B-FR1/B-FR2)"
            )

    if not approvals.is_complete():
        override.append(
            f"approvals incomplete: {approvals.completed}/{approvals.required} (E-AC2)"
        )
    elif not approvals.has_segregation_of_duties():
        override.append(
            f"segregation of duties: {approvals.completed} stages signed by "
            f"{approvals.distinct_approvers} person(s) (E-FR1)"
        )

    # G-FR7: the arithmetic lives in matrix.coverage() and nowhere else. The export gate and
    # the matrix screen count different things (draft status vs workflow status) but must
    # never compute "what fraction is done" two different ways — that is how a compliance
    # product ends up reporting 95% on one screen and 93% on the next.
    resolved = coverage(
        [(r.requirement_level, r.status not in _BLOCKING_STATUSES) for r in rows]
    ).mandatory_fraction

    # Hard blockers never clear; override-able blockers clear only under a logged admin override.
    override_used = bool(override) and admin_override
    exportable = not hard and (not override or admin_override)

    return ExportDecision(
        exportable=exportable,
        hard_blockers=tuple(hard),
        override_blockers=tuple(override),
        override_used=override_used,
        resolved_mandatory_fraction=resolved,
    )
