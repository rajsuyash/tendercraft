"""Reuse ranking + stale-claim detection (G-FR3). The gate layer — no model, no I/O."""

from __future__ import annotations

from app.deterministic.answer_reuse import rank_answers, similarity, stale_claims


def _answer(aid, requirement, *, outcome="unknown", submitted="2025-01-01", section=None,
            answer="Our quality management system is certified and independently audited."):
    return {
        "id": aid, "requirement_text": requirement, "answer_text": answer,
        "section_key": section, "outcome": outcome, "submitted_on": submitted,
        "bid_name": f"bid-{aid}", "authority": "NIC",
    }


def test_similarity_is_asymmetric_toward_the_new_requirement():
    short = "quality management certification"
    long_prior = (
        "The bidder shall hold a valid quality management certification issued by an "
        "accredited body and shall submit the certificate with the technical bid."
    )
    # Every distinctive word of the new requirement appears in the prior one.
    assert similarity(short, long_prior) == 1.0
    # The reverse is not true, and must not be — Jaccard would flatten both.
    assert similarity(long_prior, short) < 0.5


def test_nothing_is_suggested_below_the_floor():
    assert rank_answers("bank guarantee validity period", [_answer("a", "training plan")]) == ()


def test_a_won_bid_outranks_a_lost_one_at_equal_match():
    # Distinct prose on each side: identical answers are the SAME answer under two bid names
    # and are folded into one row (see the collapse test below), which would hide the ordering.
    rows = [_answer("lost", "quality management certification", outcome="lost",
                    answer="We maintain a documented quality manual reviewed by management."),
            _answer("won", "quality management certification", outcome="won",
                    answer="Our ISO 9001 registration is subject to annual surveillance.")]
    assert [s.answer_id for s in rank_answers("quality management certification", rows)] == [
        "won", "lost",
    ]


def test_the_same_answer_in_a_won_and_a_lost_bid_folds_behind_the_won_one():
    rows = [_answer("lost", "quality management certification", outcome="lost"),
            _answer("won", "quality management certification", outcome="won")]
    (only,) = rank_answers("quality management certification", rows)
    assert only.answer_id == "won"
    assert only.also_in_bids == 1


def test_a_better_textual_match_beats_a_won_bid():
    # Outcome nudges ties; it never overrides a materially better match.
    rows = [
        _answer("won", "training plan for departmental users", outcome="won"),
        _answer("close", "quality management certification issued", outcome="lost"),
    ]
    assert rank_answers("quality management certification", rows)[0].answer_id == "close"


def test_recency_breaks_a_tie():
    rows = [_answer("old", "quality management certification", submitted="2021-06-01"),
            _answer("new", "quality management certification", submitted="2025-06-01")]
    assert rank_answers("quality management certification", rows)[0].answer_id == "new"


def test_a_methodology_answer_is_not_offered_for_a_prequalification_requirement():
    rows = [_answer("m", "quality management certification", section="approach_methodology")]
    assert rank_answers("quality management certification", rows, section_key="compliance_pq") == ()


_DISTINCT = (
    "Our quality management system is certified and independently audited.",
    "We operate a documented quality manual reviewed quarterly by senior management.",
    "Every delivery passes an internal inspection regime before dispatch to the buyer.",
    "Our processes were assessed against the applicable standard by an accredited registrar.",
    "Continuous improvement is governed by a corrective and preventive action register.",
    "Supplier qualification and incoming material checks are part of the same regime.",
)


def test_only_the_top_three_are_returned():
    rows = [_answer(str(i), "quality management certification", answer=_DISTINCT[i])
            for i in range(6)]
    assert len(rank_answers("quality management certification", rows)) == 3


# ---------- stale claims ----------
_EXPIRED = [{"name": "ISO 9001:2015 Certificate", "valid_to": "2026-03-14"}]


def test_an_expired_certificate_named_in_a_prior_answer_is_reported_with_its_date():
    text = "We hold ISO 9001:2015 certification, valid and independently audited."
    claims = stale_claims(text, _EXPIRED)
    assert len(claims) == 1
    assert claims[0].document == "ISO 9001:2015 Certificate"
    assert claims[0].expired_on == "2026-03-14"


def test_a_sentence_naming_no_credential_is_never_stale():
    assert stale_claims("The programme manager reports weekly to the department.", _EXPIRED) == ()


def test_one_shared_word_is_not_enough_to_accuse_a_document_of_expiring():
    # "certificate" alone links nothing; without the second match this fires on everything.
    assert stale_claims("We hold ISO 27001 certification.", _EXPIRED) == ()


def test_a_claim_is_reported_once_per_document_not_once_per_mention():
    text = "We hold ISO 9001:2015 certification. We hold ISO 9001:2015 certification."
    assert len(stale_claims(text, _EXPIRED)) == 1


# --- acceptance and convergence (Phase 3) -------------------------------------------------

def _row(**over) -> dict:
    return {
        "id": "a1",
        "requirement_text": "Average annual turnover of the last three financial years",
        "answer_text": "Our audited average annual turnover across FY23-FY25 is stated in the "
                       "attached certificate issued by our statutory auditor.",
        "section_key": None,
        "bid_name": "Bid A",
        "authority": "ONGC",
        "submitted_on": "2026-01-01",
        "outcome": "unknown",
        "times_used": 0,
    } | over


_REQ = "Average annual turnover of the last three financial years"


def test_an_accepted_answer_outranks_an_identical_never_accepted_one():
    """answer_usages was written since 0027 and read by nothing. This is it doing work."""
    ranked = rank_answers(_REQ, [
        _row(id="never", answer_text="Turnover evidence alpha unique wording here entirely."),
        _row(id="taken", times_used=4,
             answer_text="Turnover evidence beta separate distinct phrasing altogether."),
    ])
    assert [s.answer_id for s in ranked][0] == "taken"
    assert ranked[0].times_used == 4


def test_acceptance_never_overrides_a_materially_better_textual_match():
    """Evidence, not proof — the fourth tender may simply have resembled the first three."""
    ranked = rank_answers(_REQ, [
        _row(id="weak", times_used=5,
             requirement_text="Average annual turnover unrelated wording",
             answer_text="Weak match text with entirely separate vocabulary chosen."),
        _row(id="strong", times_used=0),
    ])
    assert ranked[0].answer_id == "strong"


def test_usage_boost_saturates_so_one_popular_answer_cannot_dominate_forever():
    a = rank_answers(_REQ, [_row(times_used=5)])[0]
    b = rank_answers(_REQ, [_row(times_used=500)])[0]
    assert a.score == b.score


def test_near_identical_answers_from_six_bids_collapse_to_one_row_with_a_count():
    rows = [
        _row(id=f"a{i}", bid_name=f"Bid {i}", submitted_on=f"2026-0{i}-01")
        for i in range(1, 7)
    ]
    ranked = rank_answers(_REQ, rows)
    assert len(ranked) == 1
    assert ranked[0].also_in_bids == 5


def test_collapse_runs_before_the_limit_so_the_panel_is_not_filled_by_one_answer():
    """Collapsing after truncation would fill a three-slot panel with a single answer."""
    dups = [_row(id=f"d{i}", bid_name=f"Bid {i}") for i in range(4)]
    distinct = _row(
        id="other",
        answer_text="A different response entirely, describing our quality management "
                    "framework and its independent surveillance audits each year.",
    )
    ranked = rank_answers(_REQ, [*dups, distinct])
    assert {s.answer_id for s in ranked} == {"d0", "other"}


def test_a_short_answer_is_not_swallowed_by_a_long_one_that_merely_contains_it():
    """similarity() is asymmetric; the weaker direction has to decide, or the short one dies."""
    short = _row(id="short", answer_text="Our average annual turnover exceeds the threshold.")
    long = _row(
        id="long",
        answer_text="Our average annual turnover exceeds the threshold. We further confirm "
                    "an unbroken record of statutory compliance, an ISO 9001 quality "
                    "management system under annual surveillance, and delivery of eleven "
                    "comparable state-government platforms within the period concerned.",
    )
    ranked = rank_answers(_REQ, [short, long])
    assert len(ranked) == 2


def test_genuinely_different_answers_are_never_merged():
    a = _row(id="a", answer_text="We enclose the statutory auditor's turnover certificate "
                                 "covering the three financial years concerned.")
    b = _row(id="b", answer_text="Our quality management system is certified to ISO 9001 and "
                                 "subject to annual surveillance audits by the registrar.")
    assert len(rank_answers(_REQ, [a, b])) == 2
