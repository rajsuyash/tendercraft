"""Module G deterministic gates — coverage, completeness, import conflicts.

These are the gates the matrix's credibility rests on, so they get exhaustive branch
coverage (docs/test-strategy.md).
"""

from __future__ import annotations

import pytest

from app.deterministic.matrix import (
    Coverage,
    CriterionSpec,
    ImportConflict,
    MatrixRow,
    MatrixRowStatus,
    UnmappedResolution,
    coverage,
    coverage_of_rows,
    evaluate_matrix_complete,
    generate_rows,
    plan_import,
)
from app.deterministic.types import RequirementLevel, SourceAnchor

M = RequirementLevel.MANDATORY
D = RequirementLevel.DESIRABLE


def _spec(cid: str, level: RequirementLevel = M, anchor: SourceAnchor | None = None) -> CriterionSpec:
    return CriterionSpec(
        id=cid,
        verbatim_text=f"requirement {cid}",
        requirement_level=level,
        anchor=anchor if anchor is not None else SourceAnchor(page=12, clause="4.1(a)"),
        evidence_required="a certificate",
    )


def _row(cid: str, level: RequirementLevel = M, **kw) -> MatrixRow:
    base = dict(
        criterion_id=cid,
        requirement_text=f"requirement {cid}",
        requirement_level=level,
        anchor=SourceAnchor(page=12, clause="4.1(a)"),
    )
    return MatrixRow(**{**base, **kw})


# --- generation -------------------------------------------------------------------------


def test_generates_one_row_per_criterion_carrying_the_anchor():
    rows = generate_rows([_spec("c1"), _spec("c2", D)])

    assert [r.criterion_id for r in rows] == ["c1", "c2"]
    assert rows[0].requirement_text == "requirement c1"
    assert rows[0].anchor == SourceAnchor(page=12, clause="4.1(a)")
    assert rows[1].requirement_level is D
    # Every generated row starts unowned and unstarted — generation is not progress.
    assert all(r.status is MatrixRowStatus.NOT_STARTED and r.owner is None for r in rows)


def test_generates_nothing_from_no_criteria():
    assert generate_rows([]) == ()


def test_generation_preserves_a_missing_anchor_rather_than_inventing_one():
    rows = generate_rows([CriterionSpec(id="c1", verbatim_text="t", requirement_level=M)])
    assert rows[0].anchor is None


# --- coverage: the one function ---------------------------------------------------------


def test_coverage_counts_totals_and_mandatory_separately():
    c = coverage([(M, True), (M, False), (D, True), (D, False)])

    assert (c.total, c.resolved) == (4, 2)
    assert (c.mandatory_total, c.mandatory_resolved) == (2, 1)
    assert c.fraction == 0.5
    assert c.mandatory_fraction == 0.5


def test_empty_coverage_is_complete_not_zero():
    # A tender with nothing outstanding must not render as 0% — that would show as a blocker
    # on a screen where there is nothing to block.
    c = coverage([])
    assert c.fraction == 1.0 and c.mandatory_fraction == 1.0


def test_coverage_with_no_mandatory_rows_reports_full_mandatory_fraction():
    c = coverage([(D, False)])
    assert c.mandatory_fraction == 1.0
    assert c.fraction == 0.0


@pytest.mark.parametrize(
    ("status", "resolved"),
    [
        (MatrixRowStatus.NOT_STARTED, False),
        (MatrixRowStatus.DRAFTING, False),
        (MatrixRowStatus.DRAFTED, True),
        (MatrixRowStatus.REVIEWED, True),
        (MatrixRowStatus.APPROVED, True),
    ],
)
def test_every_workflow_status_maps_to_a_resolved_verdict(status, resolved):
    assert _row("c1", status=status).is_resolved is resolved


def test_coverage_of_rows_uses_workflow_status():
    rows = [_row("c1", status=MatrixRowStatus.APPROVED), _row("c2"), _row("c3", D)]
    assert coverage_of_rows(rows) == Coverage(
        total=3, resolved=1, mandatory_total=2, mandatory_resolved=1
    )


def test_export_gate_reads_its_fraction_from_this_module():
    # G-FR7 made structural: if someone reintroduces a second implementation, this import
    # check is what notices.
    from app.deterministic import export_gate

    assert export_gate.coverage is coverage


# --- the completeness gate --------------------------------------------------------------


def test_complete_when_every_mandatory_row_is_resolved_and_nothing_is_unmapped():
    rows = [_row("c1", status=MatrixRowStatus.DRAFTED), _row("c2", D)]
    result = evaluate_matrix_complete(rows, open_unmapped=0)

    assert result.ok is True
    assert result.blockers == ()


def test_an_empty_matrix_is_never_complete():
    result = evaluate_matrix_complete([], open_unmapped=0)
    assert result.ok is False
    assert "empty matrix" in result.blockers[0]


def test_open_unmapped_sentences_block_completion():
    rows = [_row("c1", status=MatrixRowStatus.APPROVED)]
    result = evaluate_matrix_complete(rows, open_unmapped=3)

    assert result.ok is False
    assert "3 requirement sentence(s)" in result.blockers[0]
    assert "G-AC1" in result.blockers[0]


def test_unresolved_mandatory_row_blocks_completion_and_names_its_status():
    result = evaluate_matrix_complete([_row("c1", status=MatrixRowStatus.DRAFTING)], 0)

    assert result.ok is False
    assert result.blockers == ("c1: mandatory requirement is drafting (G-FR5)",)


def test_an_unresolved_desirable_row_does_not_block():
    assert evaluate_matrix_complete([_row("c1", D)], 0).ok is True


def test_both_blocker_classes_are_reported_together():
    # A gate that stops at the first blocker makes the user fix things one round trip at a
    # time.
    result = evaluate_matrix_complete([_row("c1")], open_unmapped=2)
    assert len(result.blockers) == 2


# --- import conflicts -------------------------------------------------------------------


def test_editable_fields_round_trip_as_updates():
    existing = [_row("c1")]
    incoming = [
        _row("c1", status=MatrixRowStatus.DRAFTED, owner="u1", response_ref="§3.2",
             due_date="2026-08-01", notes="ask finance")
    ]

    plan = plan_import(existing, incoming)

    assert plan.ok is True
    assert plan.conflicts == ()
    assert len(plan.updates) == 1
    assert plan.updates[0].status is MatrixRowStatus.DRAFTED
    assert plan.updates[0].owner == "u1"
    assert plan.updates[0].requirement_text == "requirement c1"  # untouched


def test_an_unchanged_row_is_counted_not_rewritten():
    plan = plan_import([_row("c1")], [_row("c1")])
    assert plan.updates == () and plan.unchanged == 1 and plan.ok is True


@pytest.mark.parametrize(
    ("kw", "field"),
    [
        ({"requirement_text": "something the bidder prefers"}, "requirement_text"),
        ({"requirement_level": D}, "requirement_level"),
        ({"anchor": SourceAnchor(page=99, clause="4.1(a)")}, "anchor_page"),
        ({"anchor": SourceAnchor(page=12, clause="9.9(z)")}, "anchor_clause"),
    ],
)
def test_editing_a_protected_field_is_a_conflict_not_a_merge(kw, field):
    # A spreadsheet must never be able to rewrite the locked TOM: every downstream
    # deterministic check trusts that model, and the lock gate is what earned that trust.
    plan = plan_import([_row("c1")], [_row("c1", **kw)])

    assert plan.ok is False
    assert [c.field for c in plan.conflicts] == [field]
    assert plan.updates == ()


def test_a_protected_conflict_suppresses_the_editable_merge_on_that_row():
    plan = plan_import(
        [_row("c1")],
        [_row("c1", requirement_text="rewritten", status=MatrixRowStatus.APPROVED)],
    )
    assert plan.updates == ()  # the whole row is withheld, not partially applied


def test_a_row_that_is_not_in_the_matrix_is_a_conflict_not_an_insert():
    plan = plan_import([_row("c1")], [_row("c9")])

    assert plan.ok is False
    assert plan.conflicts == (
        ImportConflict(
            criterion_id="c9",
            field="criterion_id",
            existing="",
            incoming="c9",
            reason="row is not part of this tender's matrix",
        ),
    )


def test_a_row_omitted_from_the_sheet_is_left_alone():
    # Deleting a line in Excel must not delete a requirement.
    plan = plan_import([_row("c1"), _row("c2")], [_row("c1")])
    assert plan.ok is True and plan.updates == () and plan.unchanged == 1


def test_anchor_comparison_handles_a_row_with_no_anchor_on_either_side():
    plan = plan_import([_row("c1", anchor=None)], [_row("c1", anchor=None)])
    assert plan.ok is True and plan.unchanged == 1


def test_adding_an_anchor_via_import_is_a_conflict():
    plan = plan_import([_row("c1", anchor=None)], [_row("c1")])
    assert plan.ok is False
    assert {c.field for c in plan.conflicts} == {"anchor_page", "anchor_clause"}


def test_unmapped_resolution_values_are_stable():
    # The UI mirrors this set; if it changes, both ends change together (known-pitfalls).
    assert [r.value for r in UnmappedResolution] == ["open", "not_a_requirement", "mapped"]
