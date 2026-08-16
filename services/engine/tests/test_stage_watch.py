"""Bid-stage watching (UML ask 4): what alerts, what stays quiet, and what we never claim."""

from __future__ import annotations

import pytest

from app.deterministic.stage_watch import STAGES, classify, render_stage_alert

REF = "GEM/2026/B/7876746"


def test_a_forward_move_alerts():
    t = classify(REF, "not_evaluated", "tech_evaluated")
    assert t.alertable is True
    assert t.kind == "stage:tech_evaluated"


def test_a_first_sighting_records_a_baseline_and_stays_quiet():
    """NULL means 'never looked', not 'not evaluated'. Alerting here would announce every
    watched bid once on the day watching was switched on, for bids that had not moved."""
    t = classify(REF, None, "fin_evaluated")
    assert t.alertable is False
    assert "baseline" in t.reason


def test_no_change_is_not_an_event():
    assert classify(REF, "tech_evaluated", "tech_evaluated").alertable is False


def test_a_backwards_move_is_never_announced():
    """The portal can report an earlier stage — a re-evaluation, or our most-advanced-first
    probe resolving differently on a flaky page. 'Your bid went backwards' on portal noise
    costs the user's trust in every later alert."""
    t = classify(REF, "bid_awarded", "tech_evaluated")
    assert t.alertable is False
    assert "earlier stage" in t.reason


def test_an_unrecognised_stage_never_alerts():
    """A portal vocabulary change must go quiet, not loud with a stage nobody can interpret."""
    assert classify(REF, "tech_evaluated", "under_review").alertable is False


@pytest.mark.parametrize("previous,current", [
    ("not_evaluated", "fin_evaluated"),   # skipped a stage — polling is periodic
    ("tech_evaluated", "bid_awarded"),
])
def test_a_skipped_stage_still_alerts(previous, current):
    """Polling is periodic, so two moves can land between checks. The later stage is the news."""
    assert classify(REF, previous, current).alertable is True


def test_each_stage_alerts_at_most_once():
    """`kind` is the notifications_sent key, so the ledger makes repetition impossible."""
    kinds = {classify(REF, "not_evaluated", s).kind for s in STAGES if s != "not_evaluated"}
    assert len(kinds) == 3


# --- the message ---------------------------------------------------------------------------

def test_the_technical_evaluation_alert_says_what_it_means_for_the_bidder():
    t = classify(REF, "not_evaluated", "tech_evaluated")
    subject, body = render_stage_alert(t, "Supply of wire rope", "https://app.test",
                                       "https://bidplus.gem.gov.in/x")
    assert "tech evaluated" in subject
    assert "clarifications" in body
    assert "response window" in body
    assert "https://bidplus.gem.gov.in/x" in body


def test_every_alert_states_what_we_cannot_see():
    """The limitation belongs in the message, not in documentation nobody opens. A bidder who
    believed we could see the request would stop checking the inbox where it arrives."""
    for stage in ("tech_evaluated", "fin_evaluated", "bid_awarded"):
        t = classify(REF, "not_evaluated", stage)
        _, body = render_stage_alert(t, "Wire rope", "https://app.test")
        assert "cannot see the request itself" in body
        assert "we do not hold portal logins" in body


def test_a_hostile_title_cannot_inject_an_email_header():
    t = classify(REF, "not_evaluated", "bid_awarded")
    subject, _ = render_stage_alert(t, "Rope\r\nBcc: attacker@example.test", "https://app.test")
    assert "\r" not in subject and "\n" not in subject


def test_the_subject_is_bounded():
    t = classify(REF, "not_evaluated", "bid_awarded")
    subject, _ = render_stage_alert(t, "Rope " * 200, "https://app.test")
    assert len(subject) <= 160
