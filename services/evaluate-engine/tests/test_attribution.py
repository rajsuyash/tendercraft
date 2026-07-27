"""The triage gate (F15). What these tests protect is a silence.

A file attributed to the wrong bidder raises no error, fails no test, and leaves the screening
matrix looking complete. There is no natural feedback signal anywhere in the product. So the
only defence is refusing to be confident, and these tests are what stop someone from relaxing
that later because triage felt like friction.
"""

from decimal import Decimal

import pytest

from evaluate.deterministic.attribution import (
    Attribution,
    effective_bid_id,
    files_for_bid,
    intake_blocked,
    is_resolved,
    triage_pile,
)

T = Decimal("0.85")


def _a(fid, *, proposed=None, conf=None, confirmed=None, at=None):
    return Attribution(file_id=fid, proposed_bid_id=proposed,
                       confidence=Decimal(str(conf)) if conf is not None else None,
                       confirmed_bid_id=confirmed, confirmed_at=at)


# ── the threshold ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("conf,expected", [
    (0.99, "bid-1"),
    (0.85, "bid-1"),   # at the threshold resolves — the boundary is inclusive
    (0.84, None),
    (0.40, None),      # the filename-only ceiling never resolves
    (0.00, None),
])
def test_confidence_decides_whether_a_proposal_stands(conf, expected):
    assert effective_bid_id(_a("f", proposed="bid-1", conf=conf), T) == expected


def test_a_proposal_with_no_confidence_never_resolves():
    assert effective_bid_id(_a("f", proposed="bid-1"), T) is None


def test_a_confidence_with_no_proposed_bid_never_resolves():
    assert effective_bid_id(_a("f", conf=0.99), T) is None


# ── human confirmation ─────────────────────────────────────────────────────────
def test_confirmation_wins_over_a_high_confidence_proposal():
    """The officer correcting a confident model is the product working, not an anomaly."""
    a = _a("f", proposed="bid-1", conf=0.99, confirmed="bid-2", at="2026-07-27T10:00:00Z")
    assert effective_bid_id(a, T) == "bid-2"


def test_confirming_a_file_to_no_bidder_settles_it():
    """A covering note or a portal receipt belongs to nobody. That is an answer, not a gap —
    and it must NOT fall through to the model's proposal."""
    a = _a("f", proposed="bid-1", conf=0.99, confirmed=None, at="2026-07-27T10:00:00Z")
    assert effective_bid_id(a, T) is None
    assert is_resolved(a, T) is True


def test_an_unconfirmed_low_confidence_file_is_unresolved():
    assert is_resolved(_a("f", proposed="bid-1", conf=0.5), T) is False


# ── the pile ───────────────────────────────────────────────────────────────────
def test_triage_pile_holds_only_the_unresolved_in_input_order():
    attrs = [
        _a("keep-1", proposed="b1", conf=0.9),
        _a("triage-1", proposed="b1", conf=0.5),
        _a("keep-2", confirmed="b2", at="2026-07-27T10:00:00Z"),
        _a("triage-2"),
    ]
    assert triage_pile(attrs, T) == ("triage-1", "triage-2")


def test_an_empty_intake_is_not_blocked():
    assert triage_pile([], T) == ()
    assert intake_blocked([], T) is False


def test_intake_is_blocked_while_any_file_is_unresolved():
    assert intake_blocked([_a("f", proposed="b", conf=0.5)], T) is True
    assert intake_blocked([_a("f", proposed="b", conf=0.9)], T) is False


# ── per-bid grouping (feeds the presence gate) ─────────────────────────────────
def test_files_for_bid_counts_confirmed_and_confident_files_only():
    attrs = [
        _a("f1", proposed="b1", conf=0.9),
        _a("f2", proposed="b1", conf=0.5),                      # too unsure — not b1's
        _a("f3", confirmed="b1", at="2026-07-27T10:00:00Z"),
        _a("f4", proposed="b2", conf=0.95),
    ]
    assert files_for_bid(attrs, "b1", T) == ("f1", "f3")
    assert files_for_bid(attrs, "b2", T) == ("f4",)


def test_a_confirmation_moves_a_file_between_bids():
    """The officer reassigning a file must actually move it, or the presence matrix keeps
    checking the wrong bidder's documents."""
    attrs = [_a("f1", proposed="b1", conf=0.95, confirmed="b2", at="2026-07-27T10:00:00Z")]
    assert files_for_bid(attrs, "b1", T) == ()
    assert files_for_bid(attrs, "b2", T) == ("f1",)
