"""Export compliance-matrix mapping + gate wiring (Module E)."""

from app import export_service
from app.deterministic.types import CoverageStatus


def _crit(cid, level="mandatory"):
    return {"id": cid, "requirement_level": level}


def _resp(cid, status, flags=None):
    return {"criterion_id": cid, "draft_status": status, "flags": flags or []}


def test_status_mapping():
    criteria = [_crit("a"), _crit("b"), _crit("c"), _crit("d")]
    responses = [
        _resp("a", "drafted"),
        _resp("b", "placeholder"),
        _resp("c", "unverified"),
        # d has no response -> MISSING
    ]
    rows = export_service.build_matrix(criteria, responses)
    by = {r.criterion_id: r.status for r in rows}
    assert by["a"] is CoverageStatus.COVERED
    assert by["b"] is CoverageStatus.PLACEHOLDER
    assert by["c"] is CoverageStatus.UNVERIFIED
    assert by["d"] is CoverageStatus.MISSING


def test_uncited_financial_flag_detected():
    criteria = [_crit("a")]
    responses = [_resp("a", "drafted", flags=[{"reason": "uncited_financial", "text": "x"}])]
    rows = export_service.build_matrix(criteria, responses)
    assert rows[0].has_uncited_financial_claim is True


def test_clean_covered_proposal_exports_with_approvals():
    criteria = [_crit("a"), _crit("b")]
    responses = [_resp("a", "drafted"), _resp("b", "drafted")]
    decision, _ = export_service.evaluate(criteria, responses, approvals_required=2, approvals_done=2)
    assert decision.exportable is True


def test_placeholder_blocks_export():
    criteria = [_crit("a")]
    responses = [_resp("a", "placeholder")]
    decision, _ = export_service.evaluate(criteria, responses, approvals_required=0, approvals_done=0)
    assert decision.exportable is False


def test_incomplete_approvals_block_but_override_clears():
    criteria = [_crit("a")]
    responses = [_resp("a", "drafted")]
    blocked, _ = export_service.evaluate(criteria, responses, approvals_required=2, approvals_done=0)
    assert blocked.exportable is False
    overridden, _ = export_service.evaluate(
        criteria, responses, approvals_required=2, approvals_done=0, admin_override=True
    )
    assert overridden.exportable is True
    assert overridden.override_used is True


def test_uncited_financial_is_never_overridable():
    criteria = [_crit("a")]
    responses = [_resp("a", "drafted", flags=[{"reason": "uncited_financial", "text": "₹9 Cr"}])]
    decision, _ = export_service.evaluate(
        criteria, responses, approvals_required=0, approvals_done=0, admin_override=True
    )
    assert decision.exportable is False  # B-AC4 hard gate survives override


# --- an approval that signed different text is not an approval of this one -------------------


def _sect(key, body):
    return {"key": key, "body_md": body, "kind": "narrative", "status": "drafted",
            "approved_at": "2026-09-01T00:00:00Z", "sentences": [], "flags": []}


def test_an_approval_signed_against_changed_text_no_longer_counts():
    """A document could be signed through every stage, rewritten afterwards, and still export
    as approved: editing a section clears that SECTION's approval, but the proposal-level
    chain survived untouched."""
    from app.deterministic.export_gate import content_hash

    sections = [_sect("solution", "We will deliver in 12 weeks.")]
    signed = content_hash(sections)
    edited = [_sect("solution", "We will deliver in 20 weeks.")]

    decision, _ = export_service.evaluate(
        [_crit("a")], [_resp("a", "drafted")], approvals_required=2, approvals_done=2,
        sections=edited,
        approvals=[{"stage": "review", "approver": "u1", "content_hash": signed},
                   {"stage": "final", "approver": "u2", "content_hash": signed}],
    )

    assert decision.exportable is False
    assert any("approvals incomplete: 0/2" in b for b in decision.override_blockers)


def test_an_approval_signed_against_this_text_still_counts():
    from app.deterministic.export_gate import content_hash

    sections = [_sect("solution", "We will deliver in 12 weeks.")]
    signed = content_hash(sections)

    decision, _ = export_service.evaluate(
        [_crit("a")], [_resp("a", "drafted")], approvals_required=2, approvals_done=2,
        sections=sections,
        approvals=[{"stage": "review", "approver": "u1", "content_hash": signed},
                   {"stage": "final", "approver": "u2", "content_hash": signed}],
    )

    assert decision.exportable is True


def test_an_approval_from_before_content_binding_is_counted_not_invalidated():
    """NULL predates migration 0043. Inventing a hash would assert those signatures covered
    today's words; invalidating them would silently un-approve every proposal in every
    workspace. Both are worse than an honest NULL with a named ceiling."""
    decision, _ = export_service.evaluate(
        [_crit("a")], [_resp("a", "drafted")], approvals_required=2, approvals_done=2,
        sections=[_sect("solution", "anything at all")],
        approvals=[{"stage": "review", "approver": "u1", "content_hash": None},
                   {"stage": "final", "approver": "u2"}],
    )

    assert decision.exportable is True
