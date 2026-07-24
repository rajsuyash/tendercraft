"""TOM lock gate — A-AC5 + A-AC3 (tendercraft-PRD.md Module A).

A Tender Object Model may lock ONLY when:
  - every criterion carries a resolvable source anchor (page + clause)   [A-AC3]
  - every sub-0.80-confidence criterion has been human-confirmed          [A-AC5]

This is the boundary that lets all downstream compliance checks be deterministic
(A-FR5). The gate never guesses — it lists exactly what blocks the lock.
"""

from __future__ import annotations

from collections.abc import Sequence

from .types import EXTRACTION_CONFIRM_THRESHOLD, Criterion, GateResult


def evaluate_lock(criteria: Sequence[Criterion]) -> GateResult:
    """Return whether the TOM is lockable, with a blocker per offending criterion."""
    if not criteria:
        return GateResult(ok=False, blockers=("empty tender: no criteria to lock",))

    blockers: list[str] = []
    for c in criteria:
        if c.anchor is None or not c.anchor.is_resolvable():
            blockers.append(f"{c.id}: missing resolvable source anchor (A-AC3)")
        if c.confidence < EXTRACTION_CONFIRM_THRESHOLD and not c.confirmed:
            blockers.append(
                f"{c.id}: confidence {c.confidence:.2f} < "
                f"{EXTRACTION_CONFIRM_THRESHOLD:.2f} and unconfirmed (A-AC5)"
            )

    return GateResult(ok=not blockers, blockers=tuple(blockers))
