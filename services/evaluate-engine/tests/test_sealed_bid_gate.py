"""F9 — the sealed-bid gate. CI requires this file to exist.

F9 is the one gate whose failure invalidates a tender, so a green suite that never tested it
is worse than a red one. These tests are about data that must NOT be reachable.
"""

from decimal import Decimal

from evaluate.deterministic.gates import financial_readable, qualified


def test_financial_is_sealed_until_technical_lock():
    assert financial_readable(None) is False


def test_financial_readable_once_locked():
    assert financial_readable("2026-08-02T10:00:00Z") is True


def test_the_gate_mirrors_the_rls_policy_exactly():
    """The SQL policy is `technical_locked_at is not null`. This function must mean the same
    thing, because the two are a single rule with two implementations — and the bidder side
    already learned that drift between such a pair IS the cross-tenant read."""
    assert financial_readable(None) is False
    assert financial_readable("2026-08-02T10:00:00Z") is True


def test_only_qualified_bids_may_have_prices_opened():
    assert qualified(Decimal(70), 65) is True
    assert qualified(Decimal(64), 65) is False
    assert qualified(None, 65) is False, "an unsettled technical score never qualifies"
