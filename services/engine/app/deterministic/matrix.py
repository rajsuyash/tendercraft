"""Compliance matrix — generation, coverage, the completeness gate, and import conflicts.

Module G (tendercraft-discovery-PRD.md §6). Everything here is a pure function over typed
inputs; the routes adapt database dicts at the boundary.

Three things live here for reasons worth stating:

1. `coverage()` is THE coverage function. Every surface that shows a coverage number — the
   matrix screen, the export gate, the dashboard — reads it from here (G-FR7). This codebase
   has already been bitten by four counters describing the same object and disagreeing; a
   compliance product that reports two different figures for "how much of this tender have we
   answered" has no business being trusted with either.

2. The unmapped-sentence denominator (G-FR2) turns "we covered everything" from an assertion
   into a measurement. A hand-shredded matrix has no denominator: nobody can say how many
   requirement sentences the RFP contained, so nothing can be proven missing.

3. Import conflicts (G-FR4). Requirement text, level and anchor are copies of the locked TOM.
   A re-imported spreadsheet may never rewrite them — that would let a user change the tender
   model without passing the lock gate, and every downstream deterministic check trusts that
   model.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum

from .types import GateResult, RequirementLevel, SourceAnchor


class MatrixRowStatus(StrEnum):
    """Human workflow state of one requirement's response.

    Distinct from CoverageStatus, which describes what the DRAFT contains. A row can be
    'approved' here while its drafted text is still an open placeholder there — they answer
    different questions and must never be collapsed into one field.
    """

    NOT_STARTED = "not_started"
    DRAFTING = "drafting"
    DRAFTED = "drafted"
    REVIEWED = "reviewed"
    APPROVED = "approved"


class UnmappedResolution(StrEnum):
    OPEN = "open"
    NOT_A_REQUIREMENT = "not_a_requirement"
    MAPPED = "mapped"


#: Statuses that count as a resolved response for coverage purposes.
_RESOLVED_STATUSES = {MatrixRowStatus.DRAFTED, MatrixRowStatus.REVIEWED, MatrixRowStatus.APPROVED}

#: Fields copied from the locked TOM. Editable in-app never, by XLSX import never.
PROTECTED_FIELDS = ("requirement_text", "requirement_level", "anchor_page", "anchor_clause")

#: Fields a user may change, in-app or via the spreadsheet.
EDITABLE_FIELDS = ("response_ref", "owner", "status", "due_date", "notes")


@dataclass(frozen=True)
class CriterionSpec:
    """A locked-TOM criterion, as the matrix generator sees it."""

    id: str
    verbatim_text: str
    requirement_level: RequirementLevel
    anchor: SourceAnchor | None = None
    evidence_required: str | None = None


@dataclass(frozen=True)
class MatrixRow:
    criterion_id: str
    requirement_text: str
    requirement_level: RequirementLevel
    anchor: SourceAnchor | None = None
    evidence_required: str | None = None
    response_ref: str | None = None
    owner: str | None = None
    status: MatrixRowStatus = MatrixRowStatus.NOT_STARTED
    due_date: str | None = None
    notes: str | None = None

    @property
    def is_resolved(self) -> bool:
        return self.status in _RESOLVED_STATUSES


@dataclass(frozen=True)
class Coverage:
    """The one coverage figure (G-FR7). Fractions are 1.0 over an empty set, never 0.0.

    An empty tender has nothing outstanding, and reporting 0% for it would render as a
    blocker on a screen where there is nothing to block.
    """

    total: int
    resolved: int
    mandatory_total: int
    mandatory_resolved: int

    @property
    def fraction(self) -> float:
        return self.resolved / self.total if self.total else 1.0

    @property
    def mandatory_fraction(self) -> float:
        return self.mandatory_resolved / self.mandatory_total if self.mandatory_total else 1.0


def coverage(items: Sequence[tuple[RequirementLevel, bool]]) -> Coverage:
    """Compute coverage from (requirement_level, is_resolved) pairs.

    Deliberately takes tuples rather than a row type: the export gate counts draft statuses
    and the matrix screen counts workflow statuses, and they must share the ARITHMETIC without
    sharing a schema. One implementation, two callers, no drift.
    """
    total = len(items)
    resolved = sum(1 for _level, ok in items if ok)
    mandatory = [ok for level, ok in items if level is RequirementLevel.MANDATORY]
    return Coverage(
        total=total,
        resolved=resolved,
        mandatory_total=len(mandatory),
        mandatory_resolved=sum(1 for ok in mandatory if ok),
    )


def coverage_of_rows(rows: Sequence[MatrixRow]) -> Coverage:
    """Coverage over matrix rows — the workflow-status view."""
    return coverage([(r.requirement_level, r.is_resolved) for r in rows])


def generate_rows(criteria: Sequence[CriterionSpec]) -> tuple[MatrixRow, ...]:
    """Build one matrix row per locked criterion. Pure; the caller persists."""
    return tuple(
        MatrixRow(
            criterion_id=c.id,
            requirement_text=c.verbatim_text,
            requirement_level=c.requirement_level,
            anchor=c.anchor,
            evidence_required=c.evidence_required,
        )
        for c in criteria
    )


def evaluate_matrix_complete(
    rows: Sequence[MatrixRow],
    open_unmapped: int,
) -> GateResult:
    """May this matrix be marked complete?

    Blocks on unresolved requirement sentences (G-AC1) and on unresolved mandatory rows. This
    gate governs the matrix's own completeness ONLY — it is deliberately NOT wired into the
    export gate. The shredder that produces `open_unmapped` is a new model output with no
    measured false-positive rate on a real 200-page NIT; wiring an unmeasured signal into the
    product's hardest gate would teach users to reach for the admin override, which is the one
    habit a compliance product cannot afford.
    """
    blockers: list[str] = []

    if not rows:
        return GateResult(ok=False, blockers=("empty matrix: no rows generated",))

    if open_unmapped > 0:
        blockers.append(
            f"{open_unmapped} requirement sentence(s) not mapped to a row and not "
            "dismissed (G-AC1)"
        )

    for row in rows:
        if row.requirement_level is RequirementLevel.MANDATORY and not row.is_resolved:
            blockers.append(
                f"{row.criterion_id}: mandatory requirement is {row.status.value} (G-FR5)"
            )

    return GateResult(ok=not blockers, blockers=tuple(blockers))


@dataclass(frozen=True)
class ImportConflict:
    criterion_id: str
    field: str
    existing: str
    incoming: str
    reason: str


@dataclass(frozen=True)
class ImportPlan:
    """The result of diffing an uploaded sheet against the live matrix."""

    updates: tuple[MatrixRow, ...] = field(default_factory=tuple)
    conflicts: tuple[ImportConflict, ...] = field(default_factory=tuple)
    unchanged: int = 0

    @property
    def ok(self) -> bool:
        return not self.conflicts


def _protected_value(row: MatrixRow, name: str) -> str:
    if name == "requirement_text":
        return row.requirement_text
    if name == "requirement_level":
        return row.requirement_level.value
    if name == "anchor_page":
        return str(row.anchor.page) if row.anchor else ""
    return row.anchor.clause if row.anchor else ""


def plan_import(
    existing: Sequence[MatrixRow],
    incoming: Sequence[MatrixRow],
    ignore_fields: Sequence[str] = (),
) -> ImportPlan:
    """Diff an imported sheet against the live matrix, row by row.

    Never a last-write-wins merge: an edit to a protected field is a conflict the human must
    resolve, and a row key that does not exist in the live matrix is a conflict rather than an
    insert — a spreadsheet may not invent requirements any more than it may rewrite them.

    `ignore_fields` names editable fields the sheet may display but not write back — `owner`
    is one, because the sheet shows a person's name while the column stores a user id, and
    resolving a typed name back to a member is a guess. The caller reports them as ignored
    rather than dropping them silently.
    """
    editable = [f for f in EDITABLE_FIELDS if f not in ignore_fields]
    by_id = {r.criterion_id: r for r in existing}
    updates: list[MatrixRow] = []
    conflicts: list[ImportConflict] = []
    unchanged = 0

    for row in incoming:
        current = by_id.get(row.criterion_id)
        if current is None:
            conflicts.append(
                ImportConflict(
                    criterion_id=row.criterion_id,
                    field="criterion_id",
                    existing="",
                    incoming=row.criterion_id,
                    reason="row is not part of this tender's matrix",
                )
            )
            continue

        row_conflicts = [
            ImportConflict(
                criterion_id=row.criterion_id,
                field=name,
                existing=_protected_value(current, name),
                incoming=_protected_value(row, name),
                reason="requirement text, level and anchor come from the locked TOM",
            )
            for name in PROTECTED_FIELDS
            if _protected_value(current, name) != _protected_value(row, name)
        ]
        if row_conflicts:
            conflicts.extend(row_conflicts)
            continue

        merged = replace(current, **{f: getattr(row, f) for f in editable})
        if merged == current:
            unchanged += 1
        else:
            updates.append(merged)

    return ImportPlan(
        updates=tuple(updates), conflicts=tuple(conflicts), unchanged=unchanged
    )
