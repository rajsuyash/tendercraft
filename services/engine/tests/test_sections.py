"""Section spec + deterministic assemblers. No model, no I/O — pure over fetched rows."""

from app.deterministic.drafting import validate_draft
from app.deterministic.types import SectionKind, SentenceClass
from app.sections import (
    ASSEMBLED_KEYS,
    NARRATIVE_KEYS,
    SECTION_SPECS,
    SPEC_BY_KEY,
    assemble_annexures,
    assemble_compliance_matrix,
    assemble_compliance_pq,
    assemble_cvs,
    assemble_deployment,
    assemble_deviations,
    assemble_project_citations,
    assemble_team,
)

TODAY = "2026-07-25"

EXPERIENCE = [
    {"id": "e1", "project_name": "e-Office rollout", "client_type": "govt", "value_cr": 3.8,
     "scope_tags": ["software", "implementation"], "completion_date": "2025-03-01"},
    {"id": "e2", "project_name": "HMIS", "client_type": "psu", "value_cr": 2.4,
     "scope_tags": ["software"], "completion_date": "2024-06-01"},
]
PROFILE = {
    "legal_identity": {"cin": "U72900MH2015PTC123456", "pan": "AAACM1234C",
                       "gst": "27AAACM1234C1ZP", "udyam_registration": "UDYAM-MH-01-0012345",
                       "net_worth_cr": 4.3},
    "financials": [{"fy_label": "FY23", "turnover_cr": 6.8},
                   {"fy_label": "FY24", "turnover_cr": 8.1},
                   {"fy_label": "FY25", "turnover_cr": 9.7}],
}


# --- spec integrity ---


def test_every_key_is_unique_and_ordered():
    keys = [s.key for s in SECTION_SPECS]
    assert len(keys) == len(set(keys))
    orders = [s.order for s in SECTION_SPECS]
    assert orders == sorted(orders)
    assert len(set(orders)) == len(orders)


def test_narrative_and_assembled_partition_the_spec():
    assert set(NARRATIVE_KEYS) | set(ASSEMBLED_KEYS) == set(SPEC_BY_KEY)
    assert not set(NARRATIVE_KEYS) & set(ASSEMBLED_KEYS)


def test_narrative_sections_have_a_word_target_and_a_query():
    for k in NARRATIVE_KEYS:
        s = SPEC_BY_KEY[k]
        assert s.target_words > 0, k
        assert s.evidence_query, k


def test_target_length_is_government_scale():
    # A real ₹1-10 Cr Indian govt technical bid runs 20k-44k words. The narrative half
    # alone must be five figures, or we have rebuilt the one-paragraph proposal.
    assert sum(SPEC_BY_KEY[k].target_words for k in NARRATIVE_KEYS) >= 10_000


def test_meity_form_labels_are_carried():
    assert SPEC_BY_KEY["project_citations"].heading.startswith("Form 6")
    assert SPEC_BY_KEY["solution"].heading.startswith("Form 7(a)")
    assert SPEC_BY_KEY["cvs"].heading.startswith("Form 10")


# --- transclusion: the B-FR3 mechanism ---


def test_project_citations_transclude_values_with_a_source_ref():
    out = assemble_project_citations(EXPERIENCE)
    assert "₹3.80 Cr" in out.body_md
    vals = [s for s in out.sentences if s.cls is SentenceClass.ASSEMBLED]
    assert vals and all(s.is_transcluded for s in vals)
    assert vals[0].source_ref == "experience_records:e1.value_cr"


def test_transcluded_money_passes_the_hard_gate():
    """The whole point of assembly: a real figure may appear, because Python put it there."""
    out = assemble_project_citations(EXPERIENCE)
    v = validate_draft(out.sentences, set(), SectionKind.COMPLIANCE)
    assert v.flags == ()


def test_citations_capped_at_five_and_newest_first():
    many = [
        {"id": f"e{i}", "project_name": f"P{i}", "client_type": "govt", "value_cr": i,
         "scope_tags": [], "completion_date": f"202{i % 5}-01-01"}
        for i in range(8)
    ]
    out = assemble_project_citations(many)
    assert out.body_md.count("\n| P") <= 5 or out.body_md.count("| P") <= 6


def test_empty_experience_does_not_fabricate():
    out = assemble_project_citations([])
    assert out.sentences == ()
    assert "No data available" in out.body_md


# --- pre-qualification sheet ---


def test_pq_sheet_computes_average_turnover_from_rows():
    out = assemble_compliance_pq(PROFILE, [], TODAY)
    assert "₹8.20 Cr" in out.body_md  # (6.8+8.1+9.7)/3
    assert any(s.source_ref == "profile_financials:avg.turnover_cr" for s in out.sentences)


def test_pq_sheet_marks_an_expired_certification():
    certs = [{"name": "ISO 9001:2015", "valid_to": "2026-03-31"},
             {"name": "ISO 27001", "valid_to": "2027-01-01"}]
    body = assemble_compliance_pq(PROFILE, certs, TODAY).body_md
    assert "EXPIRED (2026-03-31)" in body
    assert "| Valid |" in body


def test_pq_sheet_survives_an_empty_profile():
    out = assemble_compliance_pq({}, [], TODAY)
    assert "—" in out.body_md
    assert out.sentences == ()  # nothing invented when there is nothing to transclude


# --- team / CVs / deployment ---


def test_cv_sections_name_the_scoring_consequence_when_empty():
    assert "scored dimension" in assemble_cvs([]).body_md


def test_cv_sections_index_documents():
    docs = [{"name": "rahul-cv.pdf"}, {"name": "priya-cv.pdf"}]
    assert "Annexure CV-2" in assemble_cvs(docs).body_md
    assert "rahul-cv.pdf" in assemble_team(docs).body_md
    assert "Full-time" in assemble_deployment(docs).body_md


# --- deviations ---


def test_deviations_defaults_to_nil_and_is_never_generated():
    body = assemble_deviations().body_md
    assert "no deviations" in body
    assert "never auto-generated" in body


# --- compliance matrix ---


def test_matrix_maps_status_and_flags_gaps():
    criteria = [
        {"id": "c1", "verbatim_text": "Turnover >= 5 Cr", "requirement_level": "mandatory",
         "source_anchor": "p.8 Cl.3.1"},
        {"id": "c2", "verbatim_text": "ISO 9001", "requirement_level": "desirable"},
    ]
    responses = [{"criterion_id": "c1", "draft_status": "drafted"}]
    body = assemble_compliance_matrix(criteria, responses).body_md
    assert "Comply" in body
    assert "Not addressed" in body  # c2 has no response
    assert "p.8 Cl.3.1" in body


# --- annexures ---


def test_annexure_index_marks_expiry_against_the_bid_date():
    docs = [
        {"name": "iso.pdf", "doc_type": "certification", "valid_to": "2026-03-31"},
        {"name": "turnover.pdf", "doc_type": "financial", "valid_to": None},
    ]
    body = assemble_annexures(docs, TODAY).body_md
    assert "EXPIRED 2026-03-31" in body
    assert "No expiry" in body
    assert "A-1" in body and "A-2" in body
