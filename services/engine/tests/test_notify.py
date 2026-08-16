"""Alerting: the band is a threshold on the INBOX, never a filter on the feed (UML ask 1)."""

from __future__ import annotations

import pytest

from app.deterministic.notify import (
    Alertable,
    meets_band,
    render_assignment,
    render_digest,
    select_for_digest,
)


def _match(**over) -> dict:
    return {
        "opportunity_id": "o1",
        "state": "in_scope",
        "relevance_band": "high",
        "portal_ref_no": "GEM/2026/B/1",
        "title": "Supply of steel wire rope, IS 2266",
        "authority": "ONGC",
        "deadline": "2026-09-01T09:00:00Z",
        "value_display": "₹1.2 Cr",
        "eligibility": "likely_eligible",
    } | over


# --- the threshold -------------------------------------------------------------------------

@pytest.mark.parametrize("band,minimum,ok", [
    ("high", "medium", True), ("medium", "medium", True), ("low", "medium", False),
    ("high", "high", True), ("medium", "high", False), ("low", "low", True),
])
def test_the_band_threshold_is_at_least_as_relevant_as(band, minimum, ok):
    assert meets_band(band, minimum) is ok


def test_an_unknown_band_does_not_clear_the_bar():
    """Fails toward a quieter inbox. The item is in the feed either way, and alerts nobody
    trusts are worse than no alerts."""
    assert meets_band(None, "low") is False
    assert meets_band("", "low") is False
    assert meets_band("urgent", "low") is False


# --- selection -----------------------------------------------------------------------------

def test_only_in_scope_matches_are_alertable():
    """The email must agree with the screen. An excluded item is not in the user's world."""
    got = select_for_digest(
        [_match(state="excluded", excluded_by_rule="Goods only")], "low", set())
    assert got == ()


def test_an_already_notified_opportunity_is_never_re_sent():
    """The ledger is the idempotency guarantee: a dispatcher that runs twice must be silent."""
    assert select_for_digest([_match()], "low", {"o1"}) == ()


def test_items_below_the_threshold_are_not_emailed():
    assert select_for_digest([_match(relevance_band="low")], "high", set()) == ()


def test_most_relevant_first_then_soonest_deadline():
    got = select_for_digest([
        _match(opportunity_id="a", relevance_band="medium", deadline="2026-08-20T00:00:00Z"),
        _match(opportunity_id="b", relevance_band="high", deadline="2026-12-01T00:00:00Z"),
        _match(opportunity_id="c", relevance_band="high", deadline="2026-09-01T00:00:00Z"),
    ], "low", set())
    assert [a.opportunity_id for a in got] == ["c", "b", "a"]


# --- rendering -----------------------------------------------------------------------------

def test_a_tender_title_cannot_inject_an_email_header():
    """Portal text is untrusted everywhere else in this product; an outbound header is no
    exception. A newline in a subject line is header injection (Bcc:, Content-Type:)."""
    hostile = "Rope supply\r\nBcc: attacker@example.com\r\nSubject: Free money"
    (item,) = select_for_digest([_match(title=hostile)], "low", set())
    subject, body = render_digest([item], "Usha Martin", "https://app.test")
    # The CR/LF is the whole attack. Stripped of it, "Bcc: …" is inert text in a subject
    # string — asserting its absence would be testing prudishness, not security.
    assert "\r" not in subject and "\n" not in subject
    assert "\r" not in body.split("\n")[0]
    # The title still reaches the reader intact, which is what makes this safe rather than
    # merely quiet: nothing was silently deleted from a tender's name.
    assert "Rope supply" in subject or "Rope supply" in body


def test_a_very_long_title_cannot_produce_an_unbounded_subject():
    (item,) = select_for_digest([_match(title="Rope " * 200)], "low", set())
    subject, _ = render_digest([item], "UML", "https://app.test")
    assert len(subject) <= 160


def test_the_digest_names_each_tender_with_its_reference_and_deadline():
    items = select_for_digest([_match()], "low", set())
    subject, body = render_digest(items, "Usha Martin", "https://app.test")
    assert "New tender matched" in subject
    assert "GEM/2026/B/1" in body
    assert "closes 2026-09-01" in body
    assert "₹1.2 Cr" in body
    assert "https://app.test/opportunities" in body


def test_the_digest_says_out_loud_that_it_hides_nothing():
    """The one sentence that keeps an alert threshold from being mistaken for a filter."""
    items = select_for_digest([_match()], "low", set())
    _, body = render_digest(items, "UML", "https://app.test")
    assert "never hides anything" in body


def test_a_long_digest_is_truncated_but_says_how_many_it_left_out():
    items = select_for_digest(
        [_match(opportunity_id=f"o{i}", deadline=f"2026-09-{i + 1:02d}T00:00:00Z")
         for i in range(20)], "low", set())
    _, body = render_digest(items, "UML", "https://app.test")
    assert "and 5 more in the feed" in body


def test_an_eligibility_signal_is_labelled_a_signal_not_a_verdict():
    items = select_for_digest([_match()], "low", set())
    _, body = render_digest(items, "UML", "https://app.test")
    assert "eligibility signal: likely_eligible" in body


def test_an_unknown_eligibility_is_simply_not_mentioned():
    items = select_for_digest([_match(eligibility="unknown")], "low", set())
    _, body = render_digest(items, "UML", "https://app.test")
    assert "eligibility signal" not in body


def test_the_assignment_email_names_who_routed_it():
    """UML's ask, literally: 'circulated to the respective Zonal Heads'."""
    item = Alertable("o1", "GEM/2026/B/1", "Wire rope", "high", "ONGC",
                     "2026-09-01T00:00:00Z", "₹1.2 Cr", None)
    subject, body = render_assignment(item, "priya@meridian.test", "https://app.test")
    assert subject == "Tender assigned to you: Wire rope"
    assert "priya@meridian.test has assigned" in body
    assert "GEM/2026/B/1" in body


# --- transport selection (Resend or SMTP, both free at this volume) -------------------------

def test_resend_is_preferred_when_a_key_is_present(monkeypatch):
    """Chosen for reliability on Cloud Run, not cost: an HTTPS POST needs no long-lived
    connection and cannot be tripped by a blocked SMTP egress port."""
    from app import mailer

    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_USER", "u")
    monkeypatch.setenv("SMTP_PASSWORD", "p")
    assert mailer.transport() == "resend"
    assert mailer.is_configured() is True


def test_smtp_is_the_fallback_when_there_is_no_resend_key(monkeypatch):
    from app import mailer

    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_USER", "u")
    monkeypatch.setenv("SMTP_PASSWORD", "p")
    assert mailer.transport() == "smtp"


def test_no_credentials_at_all_reports_none_rather_than_pretending(monkeypatch):
    from app import mailer

    for var in ("RESEND_API_KEY", "SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"):
        monkeypatch.delenv(var, raising=False)
    assert mailer.transport() == "none"
    assert mailer.is_configured() is False


def test_a_resend_rejection_keeps_the_reason(monkeypatch):
    """Resend's body says WHY — unverified domain, bad recipient, rate limit. A bare status
    code turns a five-second fix into an afternoon."""
    import httpx

    from app import http, mailer

    monkeypatch.setenv("RESEND_API_KEY", "re_test")

    def _post(*_a, **_k):
        request = httpx.Request("POST", "https://api.resend.com/emails")
        response = httpx.Response(403, json={"message": "domain is not verified"},
                                  request=request)
        raise httpx.HTTPStatusError("403", request=request, response=response)

    monkeypatch.setattr(http.client, "post", _post)
    with pytest.raises(RuntimeError, match="domain is not verified"):
        mailer.send("ops@uml.test", "subject", "body")
