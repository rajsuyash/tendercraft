"""B-AC4 / E-AC2 export gate — hard vs override-able blockers."""

from app.deterministic.export_gate import ApprovalChain, evaluate_export
from app.deterministic.types import ComplianceRow, CoverageStatus, RequirementLevel

MAND = RequirementLevel.MANDATORY
DES = RequirementLevel.DESIRABLE
DONE = ApprovalChain(required=3, completed=3)


def _row(cid, status=CoverageStatus.COVERED, level=MAND, uncited=False):
    return ComplianceRow(
        criterion_id=cid,
        requirement_level=level,
        status=status,
        has_uncited_financial_claim=uncited,
    )


def test_clean_proposal_exports():
    rows = [_row("a"), _row("b")]
    d = evaluate_export(rows, DONE)
    assert d.exportable is True
    assert d.resolved_mandatory_fraction == 1.0
    assert d.override_used is False


def test_uncited_financial_claim_is_a_hard_block():
    rows = [_row("a"), _row("b", uncited=True)]
    d = evaluate_export(rows, DONE)
    assert d.exportable is False
    assert any("B-AC4" in b for b in d.hard_blockers)


def test_admin_override_cannot_bypass_uncited_financial_claim():
    # ET-3 zero tolerance — the one thing an override may never clear
    rows = [_row("a", uncited=True)]
    d = evaluate_export(rows, DONE, admin_override=True)
    assert d.exportable is False
    assert d.hard_blockers


def test_placeholder_blocks_export():
    rows = [_row("a", status=CoverageStatus.PLACEHOLDER)]
    d = evaluate_export(rows, DONE)
    assert d.exportable is False
    assert any("B-FR1/B-FR2" in b for b in d.override_blockers)


def test_unverified_claim_blocks_export():
    rows = [_row("a", status=CoverageStatus.UNVERIFIED)]
    assert evaluate_export(rows, DONE).exportable is False


def test_missing_mandatory_blocks_export():
    rows = [_row("a", status=CoverageStatus.MISSING)]
    assert evaluate_export(rows, DONE).exportable is False


def test_admin_override_clears_placeholder_and_flags_it():
    rows = [_row("a", status=CoverageStatus.PLACEHOLDER)]
    d = evaluate_export(rows, DONE, admin_override=True)
    assert d.exportable is True
    assert d.override_used is True  # surfaced so the caller logs it (E-FR5)
    # E-FR5: the reason MUST survive the override so the audit log can record what was bypassed
    assert d.override_blockers
    assert any("a" in b for b in d.override_blockers)


def test_incomplete_approvals_block_export():
    rows = [_row("a")]
    d = evaluate_export(rows, ApprovalChain(required=3, completed=2))
    assert d.exportable is False
    assert any("E-AC2" in b for b in d.override_blockers)


def test_override_on_clean_proposal_is_not_marked_used():
    rows = [_row("a")]
    d = evaluate_export(rows, DONE, admin_override=True)
    assert d.exportable is True
    assert d.override_used is False  # nothing to override -> not flagged


def test_manual_original_required_counts_as_addressed():
    # B-FR5: original-required item is the human's job at physical submission, not a blocker
    rows = [_row("a", status=CoverageStatus.MANUAL), _row("b")]
    d = evaluate_export(rows, DONE)
    assert d.exportable is True
    assert d.resolved_mandatory_fraction == 1.0


def test_desirable_gaps_do_not_block_or_count_against_mandatory_coverage():
    rows = [_row("a"), _row("d", status=CoverageStatus.MISSING, level=DES)]
    d = evaluate_export(rows, DONE)
    assert d.exportable is True
    assert d.resolved_mandatory_fraction == 1.0


def test_partial_mandatory_coverage_reported():
    rows = [_row("a"), _row("b", status=CoverageStatus.PLACEHOLDER)]
    d = evaluate_export(rows, DONE)
    assert d.resolved_mandatory_fraction == 0.5


def test_no_mandatory_rows_is_full_coverage():
    rows = [_row("d", level=DES)]
    d = evaluate_export(rows, DONE)
    assert d.resolved_mandatory_fraction == 1.0


# --- long-form document sections (the B-FR4 human-approval control) ---


def _crow():
    from app.deterministic.types import ComplianceRow, CoverageStatus, RequirementLevel
    return ComplianceRow("c1", RequirementLevel.MANDATORY, CoverageStatus.COVERED)


def _sect(**kw):
    from app.deterministic.export_gate import SectionRow
    from app.deterministic.types import SectionKind
    base = dict(key="methodology", kind=SectionKind.NARRATIVE, status="drafted",
                approved=True, narrative_sentences=0, has_uncited_financial_claim=False)
    base.update(kw)
    return SectionRow(**base)


def _decide(sections, done=2):
    from app.deterministic.export_gate import ApprovalChain, evaluate_export
    return evaluate_export([_crow()], ApprovalChain(2, done), False, sections)


def test_sections_absent_leaves_behaviour_unchanged():
    assert _decide(()).exportable


def test_unapproved_ai_narrative_blocks_export():
    d = _decide([_sect(approved=False, narrative_sentences=40)])
    assert not d.exportable
    assert any("not human-approved" in b for b in d.override_blockers)


def test_approved_narrative_does_not_block():
    assert _decide([_sect(approved=True, narrative_sentences=40)]).exportable


def test_narrative_with_no_ai_sentences_needs_no_approval():
    assert _decide([_sect(approved=False, narrative_sentences=0)]).exportable


def test_assembled_section_never_needs_narrative_approval():
    from app.deterministic.types import SectionKind
    d = _decide([_sect(kind=SectionKind.COMPLIANCE, approved=False, narrative_sentences=5)])
    assert d.exportable


def test_placeholder_section_blocks_export():
    d = _decide([_sect(status="placeholder")])
    assert not d.exportable
    assert any("placeholder" in b for b in d.override_blockers)


def test_financial_claim_in_a_section_is_a_HARD_blocker():
    """Without this the document layer is a hole straight around B-AC4."""
    from app.deterministic.export_gate import ApprovalChain, evaluate_export
    d = evaluate_export([_crow()], ApprovalChain(2, 2), True,
                        [_sect(has_uncited_financial_claim=True)])
    assert not d.exportable, "an admin override must NOT clear a fabricated figure"
    assert any("non-overridable" in b for b in d.hard_blockers)


def test_section_blockers_clear_under_admin_override():
    from app.deterministic.export_gate import ApprovalChain, evaluate_export
    d = evaluate_export([_crow()], ApprovalChain(2, 2), True,
                        [_sect(approved=False, narrative_sentences=10, status="placeholder")])
    assert d.exportable and d.override_used


# --- segregation of duties (E-FR1) ---


def _chain(required=2, completed=2, distinct=0):
    from app.deterministic.export_gate import ApprovalChain, evaluate_export
    return evaluate_export([_crow()], ApprovalChain(required, completed, distinct))


def test_two_stages_signed_by_one_person_is_blocked():
    """The chain was a counter, not a control: one user could sign every stage."""
    d = _chain(required=2, completed=2, distinct=1)
    assert not d.exportable
    assert any("segregation of duties" in b for b in d.override_blockers)


def test_two_stages_signed_by_two_people_clears():
    assert _chain(required=2, completed=2, distinct=2).exportable


def test_more_approvers_than_required_clears():
    assert _chain(required=2, completed=3, distinct=3).exportable


def test_sod_is_inert_when_the_caller_supplies_no_approver_data():
    # distinct=0 means "not measured" — must not wrongly block a pre-existing caller.
    assert _chain(required=2, completed=2, distinct=0).exportable


def test_incomplete_approvals_reported_before_sod():
    # An incomplete chain is the more actionable message; don't emit both.
    d = _chain(required=2, completed=1, distinct=1)
    assert any("approvals incomplete" in b for b in d.override_blockers)
    assert not any("segregation" in b for b in d.override_blockers)
