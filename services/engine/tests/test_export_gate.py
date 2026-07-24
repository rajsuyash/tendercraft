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
