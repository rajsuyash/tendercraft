"""Tender identity extraction — every screen used to say "rfp.pdf"."""

from app.deterministic.tender_meta import TenderMeta, display_title, extract_tender_meta

REAL = """GOVERNMENT OF MAHARASHTRA
DIRECTORATE OF MUNICIPAL ADMINISTRATION

REQUEST FOR PROPOSAL

Tender No. MAHA/DMA/2026/0917
Name of Work: Design, Development and Implementation of an Integrated
Property Tax Management System for 14 Municipal Councils

Estimated Contract Value: Rs. 6.40 Crore
"""


def test_reads_number_title_and_authority_from_a_real_rfp():
    m = extract_tender_meta([REAL])
    assert m.tender_number == "MAHA/DMA/2026/0917"
    assert m.title.startswith("Design, Development and Implementation")
    assert "Property Tax Management System" in m.title
    assert m.authority is not None and "MUNICIPAL" in m.authority.upper()


def test_title_is_joined_across_the_wrapped_line():
    # The label's value wraps mid-sentence in every real RFP; a line-bounded regex truncates it.
    assert "14 Municipal Councils" in extract_tender_meta([REAL]).title


def test_alternative_labels():
    for text, num in (
        ("NIT No: 42/2026-27", "42/2026-27"),
        ("RFP Reference: DGS-IT-2026-88", "DGS-IT-2026-88"),
        ("e-Tender No. GEM/2026/B/5127401", "GEM/2026/B/5127401"),
    ):
        assert extract_tender_meta([text]).tender_number == num


def test_subject_line_is_accepted_as_a_title():
    assert extract_tender_meta(["Subject: Supply of 500 desktop computers"]).title == (
        "Supply of 500 desktop computers"
    )


def test_absent_labels_yield_none_never_a_guess():
    """The whole point: an unlabelled document keeps its filename rather than inventing one."""
    m = extract_tender_meta(["Some prose with no tender labels at all whatsoever."])
    assert m == TenderMeta()


def test_empty_input_is_safe():
    assert extract_tender_meta([]) == TenderMeta()
    assert extract_tender_meta(["", "  "]) == TenderMeta()


def test_only_the_first_pages_are_scanned():
    pages = ["cover"] * 3 + ["Tender No. LATE/2026/1"]
    assert extract_tender_meta(pages).tender_number is None


def test_a_title_that_merely_repeats_the_number_is_dropped():
    m = extract_tender_meta(["Tender No. ABC/2026/9\nName of Work: ABC/2026/9"])
    assert m.tender_number == "ABC/2026/9"
    assert m.title is None


def test_display_title_falls_back_to_the_filename():
    assert display_title(TenderMeta(), "rfp.pdf") == "rfp.pdf"
    assert display_title(TenderMeta(title="Property Tax System"), "rfp.pdf") == (
        "Property Tax System"
    )


PDF_SHAPED = (
    "GOVERNMENT OF MAHARASHTRA\n"
    "DIRECTORATE OF MUNICIPAL ADMINISTRATION\n"
    "REQUEST FOR PROPOSAL\n"
    "Tender No. MAHA/DMA/2026/0917\n"
    "Name of Work: Design, Development and Implementation of an Integrated\n"
    "Property Tax Management System for 14 Municipal Councils\n"
    "Estimated Contract Value: Rs. 6.40 Crore\n"
    "Bid Submission Deadline: 20 August 2026, 15:00 hrs IST\n"
)


def test_real_pdf_text_has_no_blank_lines_between_fields():
    """Regression from a live upload: pypdf output runs the title straight into the next
    label, so a terminator that only matched a SINGLE-word label ("Foo:") missed it and the
    bid stayed named after its filename."""
    m = extract_tender_meta([PDF_SHAPED])
    assert m.tender_number == "MAHA/DMA/2026/0917"
    assert m.title == (
        "Design, Development and Implementation of an Integrated "
        "Property Tax Management System for 14 Municipal Councils"
    )
    assert m.authority == "DIRECTORATE OF MUNICIPAL ADMINISTRATION"


def test_title_stops_at_the_next_label_not_at_the_end_of_the_page():
    assert "Estimated" not in (extract_tender_meta([PDF_SHAPED]).title or "")
    assert "Crore" not in (extract_tender_meta([PDF_SHAPED]).title or "")
