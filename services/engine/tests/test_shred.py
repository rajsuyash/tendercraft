"""Requirement shredding (G-FR2) — the denominator's own tests.

The failure that matters here is a FALSE NEGATIVE: a requirement sentence this module fails
to collect is a requirement nobody is ever asked about, which is precisely the silent omission
the denominator exists to prevent. Over-collection costs one dismissal click and is tested for
sanity, not minimised.
"""

from __future__ import annotations

import pytest

from app.deterministic.shred import (
    MIN_SENTENCE_CHARS,
    RequirementSentence,
    find_requirement_sentences,
    is_represented,
    split_sentences,
    unmapped_sentences,
)

SHALL = "The bidder shall submit a CA-certified turnover certificate for FY23 to FY25."
MUST = "Bidders must possess a valid ISO 9001:2015 certification on the bid due date."
MAY = "The Authority may seek clarification from any bidder during evaluation of the bids."


# --- sentence splitting -----------------------------------------------------------------


def test_splits_on_terminators_and_blank_lines():
    assert split_sentences(f"{SHALL} {MUST}") == [SHALL, MUST]
    assert split_sentences(f"{SHALL}\n\n{MUST}") == [SHALL, MUST]


def test_collapses_the_line_wrapping_pdfs_introduce():
    wrapped = "The bidder shall submit a\n   CA-certified turnover\ncertificate for FY23."
    assert split_sentences(wrapped) == [
        "The bidder shall submit a CA-certified turnover certificate for FY23."
    ]


@pytest.mark.parametrize(
    "furniture",
    ["Page 14", "27", "-------------------", "Table of Contents", "Annexure VII", "| | |"],
)
def test_page_furniture_is_not_a_sentence(furniture):
    assert split_sentences(furniture) == []


def test_empty_input_yields_nothing():
    assert split_sentences("") == [] and split_sentences(None) == []


# --- requirement detection --------------------------------------------------------------


@pytest.mark.parametrize(
    "sentence",
    [
        SHALL,
        MUST,
        "The successful bidder is required to furnish a PBG within 21 days of award.",
        "Bidders are required to submit Annexure-VII duly signed by an authorised person.",
        "The tenderer has to deposit EMD of Rs. 2,40,000 before the due date and time.",
        "Documents to be submitted along with the technical bid are listed in Clause 9.",
        "Registration under the MSME Act is mandatory for claiming the fee exemption.",
        "The bidder should possess prior experience of three similar works of like nature.",
    ],
)
def test_obligation_phrasings_are_all_collected(sentence):
    assert find_requirement_sentences([(1, sentence)]) == [
        RequirementSentence(page=1, text=sentence)
    ]


def test_permission_is_not_obligation():
    # "may" grants permission. Including it turned an NIT's boilerplate into dozens of
    # phantom requirements — noise teaches users to dismiss the list unread.
    assert find_requirement_sentences([(1, MAY)]) == []


def test_prose_without_an_obligation_marker_is_ignored():
    text = "This tender is issued by the Public Works Department, Government of Maharashtra."
    assert find_requirement_sentences([(1, text)]) == []


def test_a_fragment_is_too_short_to_carry_an_obligation():
    fragment = "Shall submit."
    assert len(fragment) < MIN_SENTENCE_CHARS
    assert find_requirement_sentences([(1, fragment)]) == []


def test_pages_are_reported_in_order_with_their_page_number():
    found = find_requirement_sentences([(3, MUST), (1, SHALL)])
    assert [(f.page, f.text) for f in found] == [(3, MUST), (1, SHALL)]


def test_a_clause_repeated_on_one_page_is_one_requirement():
    # A clause quoted in a header and again in a body table is one obligation.
    found = find_requirement_sentences([(1, f"{SHALL} {SHALL}")])
    assert len(found) == 1


def test_the_same_clause_on_two_pages_is_reported_for_each():
    # Deliberate: it may be answered in one place and missed in the other.
    assert len(find_requirement_sentences([(1, SHALL), (2, SHALL)])) == 2


def test_a_page_of_only_whitespace_contributes_nothing():
    assert find_requirement_sentences([(1, "   \n  \n ")]) == []


# --- mapping a sentence to an extracted criterion ----------------------------------------


def test_verbatim_extraction_is_represented():
    assert is_represented(SHALL, SHALL) is True


def test_a_criterion_quoting_a_longer_span_still_represents_the_sentence():
    assert is_represented(SHALL, f"Clause 4.1(a): {SHALL} Evidence: CA certificate.") is True


def test_light_normalisation_is_matched_by_token_overlap():
    lightly_changed = "Bidder shall submit CA-certified turnover certificate FY23 FY25"
    assert is_represented(SHALL, lightly_changed) is True


def test_an_unrelated_criterion_does_not_represent_the_sentence():
    assert is_represented(SHALL, MUST) is False


@pytest.mark.parametrize(("s", "c"), [("", SHALL), (SHALL, ""), ("", "")])
def test_empty_text_never_represents_anything(s, c):
    assert is_represented(s, c) is False


def test_a_sentence_of_only_stopwords_is_not_matched_by_accident():
    # Guards the zero-division path: no content tokens means no evidence of representation.
    assert is_represented("the of to in for and or", "a completely different requirement") is False


# --- the denominator --------------------------------------------------------------------


def test_an_extracted_criterion_removes_its_sentence_from_the_backlog():
    assert unmapped_sentences([(1, SHALL)], [(1, SHALL)]) == []


def test_a_requirement_nobody_extracted_lands_in_the_backlog():
    assert unmapped_sentences([(1, f"{SHALL} {MUST}"), (2, "")], [(1, SHALL)]) == [
        RequirementSentence(page=1, text=MUST)
    ]


def test_a_criterion_on_another_page_does_not_cover_this_page():
    # Page-scoped by default: the same obligation on page 9 is not evidence that page 2's
    # copy was answered.
    assert unmapped_sentences([(2, SHALL)], [(9, SHALL)]) == [
        RequirementSentence(page=2, text=SHALL)
    ]


def test_a_criterion_with_no_anchor_is_compared_against_every_page():
    # A missing anchor is the extractor's weakness. Letting it inflate the user's backlog
    # would blame the user for it.
    assert unmapped_sentences([(4, SHALL)], [(None, SHALL)]) == []


def test_no_criteria_at_all_means_every_requirement_is_unmapped():
    found = unmapped_sentences([(1, f"{SHALL} {MUST}")], [])
    assert [f.text for f in found] == [SHALL, MUST]


def test_a_document_with_no_obligations_has_an_empty_backlog():
    assert unmapped_sentences([(1, MAY)], []) == []


@pytest.mark.parametrize(
    "text",
    [
        "The tenderer has to deposit EMD of Rs. 2,40,000 before the due date and time.",
        "Bidders shall refer to Cl. 4.1 of the NIT for the turnover requirement.",
        "Tender No. 7 of 2026 requires that the bidder must submit Annexure-VII.",
    ],
)
def test_an_abbreviation_period_does_not_cut_a_requirement_in_half(text):
    # Indian tender prose is dense with Rs./Cl./No. Splitting there drops the half carrying
    # the obligation's actual terms — a silent omission of exactly the kind this module exists
    # to prevent.
    assert split_sentences(text) == [text]


def test_a_trailing_abbreviation_at_end_of_page_is_still_emitted():
    assert split_sentences("The bidder shall pay the fee of Rs.") == [
        "The bidder shall pay the fee of Rs."
    ]
