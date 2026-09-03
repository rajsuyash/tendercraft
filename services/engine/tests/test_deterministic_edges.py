"""The defensive arms of `app/deterministic/`, which nothing else reaches.

`app/deterministic/` is CI-gated at 100% branch coverage, and these arms sat uncovered while
the gate was red — which is the wrong pair of facts to hold at once on modules that decide what
a bidder sees. Every case here is a guard whose failure is silent: an inert rule that should
exclude nothing, a naive timestamp read as the wrong instant, a heading matched to the wrong
section. None of them raises when it goes wrong; they just answer differently.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from app.deterministic.answer_mining import match_section_key, mine_answers
from app.deterministic.discovery import (
    Rule,
    _days_to_close,
    _matches,
    evaluate_gate,
    keyword_relevance,
)
from app.deterministic.inbound import find_deadline
from app.deterministic.learning import edit_delta

NOW = datetime(2026, 9, 1, tzinfo=UTC)


# ── discovery: the closing-date reader ───────────────────────────────────────

def test_a_closing_date_already_parsed_is_used_as_is():
    """Records reach the gate from two directions — freshly parsed from a connector, and read
    back out of Postgres by a client that already builds datetimes."""
    assert _days_to_close({"closing_at": datetime(2026, 9, 11, tzinfo=UTC)}, NOW) == 10.0


def test_a_naive_closing_date_is_read_as_utc_rather_than_local():
    """A deadline is IST-sensitive and the corpus stores UTC. Reading a naive timestamp in the
    server's local zone would shift every window by the server's offset — and a tender that
    closes at 15:00 IST is lost, not late."""
    assert _days_to_close({"closing_at": "2026-09-11T00:00:00"}, NOW) == 10.0


# ── discovery: rules that must not act ───────────────────────────────────────

def test_an_unrecognised_rule_kind_excludes_nothing():
    """A rule kind this version does not implement must be inert, never excluding. A rule
    written by a newer deploy, or a typo in a kind, would otherwise silently remove tenders
    from a feed with a named reason that looks deliberate (G-9 / ET-7)."""
    unknown = Rule(name="from the future", kind="not_a_kind", spec={})

    # `evaluate_gate` skips it by allowlist...
    result = evaluate_gate({"title": "Wire rope"}, [unknown], now=NOW)
    assert result.in_scope is True
    assert result.excluded_by_rule is None

    # ...and `_matches` refuses it a second time, so a future caller that reaches the matcher
    # without the allowlist in front of it still excludes nothing.
    assert _matches(unknown, {"title": "Wire rope"}, NOW) is False


# ── discovery: the keyword bands ─────────────────────────────────────────────

def test_matching_only_the_authority_is_the_weakest_band():
    """Selling to an authority before is real evidence and weak evidence. It must not read as
    the same fit as the tender's own title naming the product."""
    match = keyword_relevance(
        {"title": "Supply of desktop computers", "authority": "Steel Authority of India"},
        ["steel authority"],
    )

    assert match.band == "low"
    assert match.matched_terms == ("steel authority",)


def test_a_multi_word_term_of_pure_stopwords_matches_nothing():
    """`content_words` strips stopwords, and a term that is nothing but stopwords would
    otherwise reduce to an empty requirement — which every tender satisfies."""
    match = keyword_relevance({"title": "Supply of wire rope"}, ["of the"])

    assert match.matched_terms == ()


def test_a_category_code_matched_exactly_counts_as_a_category_hit():
    """Category codes are the strongest signal the portal gives — GeM's own mapping beats our
    keyword stems. An exact hit on one must reach the top band, not be scored as a title match."""
    match = keyword_relevance(
        {"title": "Supply order", "category_codes": ["wirerope"]}, ["wirerope"],
    )

    assert match.matched_terms == ("wirerope",)
    assert match.band == "high"


# ── inbound: the deadline reader ─────────────────────────────────────────────

def test_an_uncued_date_is_skipped_and_a_later_cued_one_still_found():
    """A message naming a date in passing is not naming a deadline. Taking the first date it
    sees would make an email's own send-date the bid's due date."""
    text = (
        "Your bid was opened on 5 October 2026 by the buyer. "
        "Additional documents must be submitted by 20 October 2026."
    )

    assert find_deadline(text, today=date(2026, 9, 1)) == date(2026, 10, 20)


# ── learning: the edit delta ─────────────────────────────────────────────────

def test_an_edit_delta_serialises_for_the_meter():
    """The trend meter reads these across a workspace; a delta that cannot serialise is a
    silently empty chart rather than an error."""
    delta = edit_delta("The Bidder shall deploy the system.", "We will deploy the system.")

    assert delta is not None
    payload = delta.as_dict()
    assert set(payload) >= {"length_shift"}


# ── answer mining: headings that decide which section an answer lands in ─────

def test_a_heading_with_no_content_words_matches_no_section():
    """"1.2.3" is a heading by shape and says nothing. Matching it to a section would file a
    real answer under a requirement it does not answer."""
    assert match_section_key("2.4", [("approach", "Approach and Methodology")]) is None


def test_a_section_spec_with_no_content_words_is_skipped_rather_than_matched():
    """A spec whose heading and key both reduce to nothing would divide by zero on the overlap
    score, and any heading would match it first."""
    assert match_section_key(
        "Approach and Methodology", [("_", ""), ("approach", "Approach and Methodology")]
    ) == "approach"


def test_a_markdown_heading_opens_a_section():
    """Past bids arrive as PDFs, DOCX and markdown. A `##` heading is the shape the last of
    those uses, and missing it files the whole document under the previous section."""
    mined = mine_answers(
        [("bid.md", "## Approach and Methodology\nWe deploy in four phases, each led by a dedicated programme manager who remains with the engagement from mobilisation through to final handover and closure.\n")],
        [("approach", "Approach and Methodology")],
    )

    assert [m.section_key for m in mined] == ["approach"]
    assert "four phases" in mined[0].answer_text


def test_a_blank_line_inside_a_section_does_not_end_it():
    """Paragraph breaks are how prose is written. Treating one as a section boundary would cut
    every answer off at its first paragraph."""
    mined = mine_answers(
        [("bid.md", "## Approach and Methodology\nWe deploy in four phases, each led by a dedicated programme manager who remains with the engagement from mobilisation through to final handover and closure.\n\nEach phase is signed off by the buyer's nominated officer before the next begins, and the sign-off is recorded in the monthly progress report submitted to the department.\n")],
        [("approach", "Approach and Methodology")],
    )

    assert len(mined) == 1
    assert "signed off" in mined[0].answer_text
