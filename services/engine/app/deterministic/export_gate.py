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

from collections.abc import Sequence
from dataclasses import dataclass, field

from .types import ComplianceRow, CoverageStatus, RequirementLevel

_BLOCKING_STATUSES = {CoverageStatus.PLACEHOLDER, CoverageStatus.UNVERIFIED, CoverageStatus.MISSING}


@dataclass(frozen=True)
class ApprovalChain:
    required: int
    completed: int

    def is_complete(self) -> bool:
        return self.completed >= self.required


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
) -> ExportDecision:
    """Decide whether a proposal may export, separating hard from override-able blockers."""
    hard: list[str] = []
    override: list[str] = []

    for row in rows:
        if row.has_uncited_financial_claim:
            hard.append(
                f"{row.criterion_id}: uncited financial/numeric claim (B-AC4, non-overridable)"
            )

    mandatory = [r for r in rows if r.requirement_level is RequirementLevel.MANDATORY]
    addressed = 0
    for row in mandatory:
        if row.status in _BLOCKING_STATUSES:
            override.append(
                f"{row.criterion_id}: {row.status.value} on mandatory criterion (B-FR1/B-FR2)"
            )
        else:
            addressed += 1  # COVERED or MANUAL (original-required, handled at physical submission)

    if not approvals.is_complete():
        override.append(
            f"approvals incomplete: {approvals.completed}/{approvals.required} (E-AC2)"
        )

    resolved = addressed / len(mandatory) if mandatory else 1.0

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
