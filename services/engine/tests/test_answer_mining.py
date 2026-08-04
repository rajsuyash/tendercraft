"""Mining a past bid into requirement -> answer pairs (G-FR3). Deterministic layer only."""

from __future__ import annotations

from app.deterministic.answer_mining import match_section_key, mine_answers

SPECS = (
    ("understanding", "Form 7(b): Understanding of the Project"),
    ("approach_methodology", "Form 7(c): Technical Approach and Methodology"),
    ("letter_of_proposal", "Form 5: Letter of Proposal"),
)

_LONG = (
    "Our delivery model places a dedicated programme manager at the client site for the "
    "duration of the engagement, supported by a core team of engineers who have executed "
    "comparable state-government platforms across three states."
)


def test_heading_starts_a_pair_and_prose_beneath_it_is_the_answer():
    pages = [("bid.pdf", f"Form 7(c): Technical Approach and Methodology\n{_LONG}")]
    mined = mine_answers(pages, SPECS)
    assert len(mined) == 1
    assert mined[0].requirement_text.startswith("Form 7(c)")
    assert mined[0].answer_text == _LONG
    assert mined[0].mined_by == "heading"


def test_section_key_survives_a_different_authoritys_form_number():
    # "Form 11" at one authority is "Form 7(b)" at another — the key is semantic on purpose.
    assert match_section_key("Form 11: Understanding of the Project", SPECS) == "understanding"


def test_an_unrelated_heading_maps_to_no_section():
    assert match_section_key("Bank Guarantee Format", SPECS) is None


def test_compliance_table_row_is_a_pair_on_its_own():
    row = f"Bidder shall have executed three similar works | {_LONG}"
    mined = mine_answers([("boq.xlsx · PQ", row)], SPECS)
    assert len(mined) == 1
    assert mined[0].mined_by == "table"
    assert mined[0].requirement_text.startswith("Bidder shall have executed")


def test_a_bare_complied_is_not_an_answer():
    # "Complied" satisfies a requirement and reuses into nothing.
    assert mine_answers([("bid.pdf", "Bidder shall hold ISO 9001 certification | Complied")]) == ()


def test_a_heading_with_nothing_under_it_is_not_mined():
    mined = mine_answers([("bid.pdf", "Form 5: Letter of Proposal\nsee attached")], SPECS)
    assert mined == ()


def test_page_furniture_never_becomes_a_requirement():
    pages = [("bid.pdf", f"Page 14 of 92\nConfidential\n1. Scope of Work\n{_LONG}")]
    mined = mine_answers(pages, SPECS)
    assert [m.requirement_text for m in mined] == ["Scope of Work"]


def test_pairs_keep_document_order_across_a_package():
    pages = [
        ("NIT-response.pdf", f"1. Understanding\n{_LONG}"),
        ("Annexure-II.pdf", f"2. Methodology\n{_LONG}"),
    ]
    mined = mine_answers(pages, SPECS)
    assert [m.document for m in mined] == ["NIT-response.pdf", "Annexure-II.pdf"]
