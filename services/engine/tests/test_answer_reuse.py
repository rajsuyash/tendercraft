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
    rows = [_answer("lost", "quality management certification", outcome="lost"),
            _answer("won", "quality management certification", outcome="won")]
    assert [s.answer_id for s in rank_answers("quality management certification", rows)] == [
        "won", "lost",
    ]


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


def test_only_the_top_three_are_returned():
    rows = [_answer(str(i), "quality management certification") for i in range(6)]
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
