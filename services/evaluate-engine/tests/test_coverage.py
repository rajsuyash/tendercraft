"""Requirement coverage (F20).

The load-bearing test here is `test_not_found_is_not_a_compliance_verdict` — not because the
assertion is clever, but because the whole feature is one careless rename away from telling a
procurement officer that a bidder is non-compliant when what actually happened is that our
extractor missed page 180 of a scanned submission.
"""

from evaluate.deterministic.coverage import (
    Coverage,
    CoverageCell,
    OfferRef,
    RequirementRef,
    addressed_count,
    classify,
    cover_bid,
    denominator,
    needs_attention,
)

R1 = RequirementRef("c1", "Uptime SLA", 10)
R2 = RequirementRef("c2", "Support hours", 10)
R3 = RequirementRef("c3", "Data residency", 5)


def _o(cid, value=None, excerpt=None, page=None):
    return OfferRef(cid, value, excerpt, page)


# ── classification ─────────────────────────────────────────────────────────────
def test_a_value_with_a_locatable_excerpt_is_addressed():
    assert classify([_o("c1", "99.5%", "uptime of 99.5% guaranteed", 61)]) is Coverage.ADDRESSED


def test_a_value_the_officer_cannot_jump_to_is_only_partial():
    """The promise of this screen is that every claim is checkable in one click. A value with
    no page is a claim we are asking them to take on trust."""
    assert classify([_o("c1", "99.5%")]) is Coverage.PARTIAL
    assert classify([_o("c1", "99.5%", "some text", None)]) is Coverage.PARTIAL
    assert classify([_o("c1", "99.5%", None, 61)]) is Coverage.PARTIAL


def test_no_answer_is_not_found():
    assert classify([]) is Coverage.NOT_FOUND
    assert classify([_o("c1", "   ")]) is Coverage.NOT_FOUND
    assert classify([_o("c1", None)]) is Coverage.NOT_FOUND


def test_two_different_answers_are_contradictory_not_resolved_by_us():
    """Picking one would be inventing a bid. Both go to a human."""
    assert classify([
        _o("c1", "99.5%", "x", 12), _o("c1", "99.0%", "y", 88),
    ]) is Coverage.CONTRADICTORY


def test_the_same_answer_twice_is_not_a_contradiction():
    """A bid restating its SLA in the summary is normal."""
    assert classify([
        _o("c1", "99.5%", "x", 12), _o("c1", " 99.5% ", "y", 88),
    ]) is Coverage.ADDRESSED


def test_not_found_is_not_a_compliance_verdict():
    """The enum must never gain a member that reads as a judgement about the bidder. If this
    test is failing because someone renamed NOT_FOUND to NON_COMPLIANT, that rename is the bug:
    an extraction miss is our failure, not the bidder's, and F6 owns responsiveness."""
    assert {c.value for c in Coverage} == {
        "addressed", "partial", "not_found", "contradictory"}


# ── whole-bid coverage ─────────────────────────────────────────────────────────
def test_cover_bid_returns_one_cell_per_requirement_in_order():
    cells = cover_bid([R1, R2, R3], [_o("c1", "99.5%", "x", 61)])
    assert [c.requirement_id for c in cells] == ["c1", "c2", "c3"]
    assert [c.coverage for c in cells] == [
        Coverage.ADDRESSED, Coverage.NOT_FOUND, Coverage.NOT_FOUND]


def test_a_cell_cites_the_anchored_offer_when_one_exists():
    """The officer clicks the page number, so it must be the offer that HAS one."""
    cells = cover_bid([R1], [_o("c1", "99.5%"), _o("c1", "99.5%", "quoted", 61)])
    assert cells[0].anchor_page == 61
    assert cells[0].excerpt == "quoted"


def test_offers_for_an_unknown_requirement_are_ignored_not_crashed_on():
    """A stale response row for a deleted criterion must not break the matrix."""
    cells = cover_bid([R1], [_o("gone", "x", "y", 1)])
    assert cells[0].coverage is Coverage.NOT_FOUND


# ── the denominator ────────────────────────────────────────────────────────────
def test_the_denominator_is_the_requirement_count():
    assert denominator([R1, R2, R3]) == 3
    assert denominator([]) == 0


def test_addressed_count_excludes_partial():
    cells = (
        CoverageCell("c1", Coverage.ADDRESSED, "a", "x", 1),
        CoverageCell("c2", Coverage.PARTIAL, "b", None, None),
        CoverageCell("c3", Coverage.NOT_FOUND, None, None, None),
    )
    assert addressed_count(cells) == 1


# ── the ranking that saves the reading time ────────────────────────────────────
def test_needs_attention_puts_contradictions_first_then_gaps_then_partials():
    cells = (
        CoverageCell("c1", Coverage.PARTIAL, "a", None, None),
        CoverageCell("c2", Coverage.NOT_FOUND, None, None, None),
        CoverageCell("c3", Coverage.CONTRADICTORY, "b", "x", 3),
        CoverageCell("c4", Coverage.ADDRESSED, "c", "y", 4),
    )
    assert needs_attention(cells) == ("c3", "c2", "c1")


def test_a_fully_addressed_bid_needs_no_attention():
    cells = (CoverageCell("c1", Coverage.ADDRESSED, "a", "x", 1),)
    assert needs_attention(cells) == ()
