"""A-AC5 / A-AC3 lock gate — the gate must never let an unsafe TOM lock."""

from app.deterministic.lock import evaluate_lock
from app.deterministic.types import Criterion, RequirementLevel, SourceAnchor

ANCHOR = SourceAnchor(page=12, clause="4.1(a)")
MAND = RequirementLevel.MANDATORY


def _crit(cid, conf, confirmed, anchor=ANCHOR):
    return Criterion(
        id=cid, confidence=conf, confirmed=confirmed, requirement_level=MAND, anchor=anchor
    )


def test_empty_tender_never_locks():
    result = evaluate_lock([])
    assert result.ok is False
    assert "empty tender" in result.blockers[0]


def test_all_high_confidence_anchored_locks():
    crits = [_crit("C1", 0.95, False), _crit("C2", 0.88, False)]
    assert evaluate_lock(crits).ok is True


def test_low_confidence_unconfirmed_blocks_lock():
    # A-AC5: the core safety property — a sub-0.80 unconfirmed item caps the lock
    crits = [_crit("C1", 0.95, False), _crit("C2", 0.64, False)]
    result = evaluate_lock(crits)
    assert result.ok is False
    assert any("C2" in b and "A-AC5" in b for b in result.blockers)


def test_low_confidence_confirmed_is_lockable():
    crits = [_crit("C1", 0.64, True)]
    assert evaluate_lock(crits).ok is True


def test_exactly_at_threshold_needs_no_confirmation():
    # 0.80 is not < 0.80 — boundary belongs to the safe side
    crits = [_crit("C1", 0.80, False)]
    assert evaluate_lock(crits).ok is True


def test_just_below_threshold_requires_confirmation():
    crits = [_crit("C1", 0.7999, False)]
    assert evaluate_lock(crits).ok is False


def test_missing_anchor_blocks_lock():
    crits = [_crit("C1", 0.99, True, anchor=None)]
    result = evaluate_lock(crits)
    assert result.ok is False
    assert any("A-AC3" in b for b in result.blockers)


def test_unresolvable_anchor_blocks_lock():
    crits = [_crit("C1", 0.99, True, anchor=SourceAnchor(page=0, clause=""))]
    assert evaluate_lock(crits).ok is False


def test_a_page_without_a_clause_number_is_still_resolvable():
    # Real tenders state obligations in unnumbered prose ("Note: Certificate should be on
    # official letterhead..."). Requiring a clause identifier made every such tender
    # permanently unlockable, with no way for a human to supply a number the document never
    # had. A page plus the stored verbatim text is enough to find the sentence again, which is
    # what A-AC3 exists to guarantee. Measured on a live NABARD RFP: 12 of 192 criteria.
    crits = [_crit("C1", 0.99, True, anchor=SourceAnchor(page=68, clause=""))]
    assert evaluate_lock(crits).ok is True


def test_one_criterion_can_trip_both_blockers():
    crits = [_crit("C1", 0.5, False, anchor=SourceAnchor(page=0, clause="  "))]
    result = evaluate_lock(crits)
    assert result.ok is False
    assert len(result.blockers) == 2  # unresolvable anchor AND low-confidence
