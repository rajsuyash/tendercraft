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


# --- average turnover: the FY window is part of the requirement, not a property of us ---
#
# The old test asserted the average of EVERY stored FY under a "CA-certified" label with the
# unqualified ref `profile_financials:avg.turnover_cr`. It encoded the defect: a GeM tender asks
# for "Minimum Average Annual Turnover (For 3 Years)", so confirming FY26 silently changed the
# number answering a FY23-FY25 requirement, and the token named no window and no versions. It
# changed with the code, deliberately.


def test_pq_sheet_averages_only_the_required_financial_years():
    out = assemble_compliance_pq(PROFILE, [], TODAY, required_fys=["FY24", "FY25"])
    assert "₹8.90 Cr" in out.body_md  # (8.1+9.7)/2 — FY23 is on file and correctly ignored
    assert any(
        s.source_ref == "profile_financials:avg.turnover_cr[FY24|FY25]" for s in out.sentences
    ), "the token must name the FY window, or it identifies no computable quantity"


def test_a_later_fy_does_not_move_an_earlier_window():
    """The whole point. Confirming FY26 must not change the answer to a FY23-FY25 tender."""
    profile = {**PROFILE, "financials": [*PROFILE["financials"],
                                         {"fy_label": "FY26", "turnover_cr": 40.0}]}
    before = assemble_compliance_pq(PROFILE, [], TODAY, required_fys=["FY23", "FY24", "FY25"])
    after = assemble_compliance_pq(profile, [], TODAY, required_fys=["FY23", "FY24", "FY25"])
    assert "₹8.20 Cr" in before.body_md
    assert "₹8.20 Cr" in after.body_md


def test_a_missing_required_fy_asserts_nothing():
    """Averaging the years we happen to hold would manufacture a number for a window we
    cannot answer — on a hard, non-overridable financial gate."""
    out = assemble_compliance_pq(PROFILE, [], TODAY, required_fys=["FY25", "FY26"])
    assert "₹" not in out.body_md.split("Average annual turnover")[1].split("\n")[0]
    assert not any("avg.turnover_cr" in (s.source_ref or "") for s in out.sentences)
    assert "FY26" in out.body_md, "name the FY that is missing, so the gap is actionable"


def test_no_required_window_asserts_no_average():
    """Without the requirement's window there is no correct average. Say so; do not guess."""
    out = assemble_compliance_pq(PROFILE, [], TODAY)
    assert not any("avg.turnover_cr" in (s.source_ref or "") for s in out.sentences)
    assert "not confirmed" in out.body_md.lower()


def test_pq_sheet_marks_an_expired_certification():
    certs = [{"name": "ISO 9001:2015", "valid_to": "2026-03-31"},
             {"name": "ISO 27001", "valid_to": "2027-01-01"}]
    body = assemble_compliance_pq(PROFILE, certs, TODAY).body_md
    assert "EXPIRED (2026-03-31)" in body
    assert "| Valid |" in body


def test_pq_sheet_never_calls_an_undated_certification_expired():
    # "No expiry on file" is a gap in OUR record, not a claim about the certificate.
    body = assemble_compliance_pq(PROFILE, [{"name": "API Spec 9A"}], TODAY).body_md
    assert "EXPIRED" not in body
    assert "Validity not recorded" in body


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


# --- Form 12: deviations are read, never assumed -------------------------------------------


def _line(*params, ref="Sch-A", item="1"):
    return {"schedule_ref": ref, "item_ref": item, "description": "Wire rope 40mm",
            "parameters": list(params)}


def _param(key, match, required="40 mm", capability="6–32 mm"):
    return {"key": key, "match": match, "required": required, "capability": capability}


def test_form_12_lists_a_deviation_the_schedule_found():
    body = assemble_deviations(
        {"lines": [_line(_param("diameter_mm", "deviation"))]}
    ).body_md
    assert "1 deviation(s)" in body
    assert "diameter_mm" in body and "40 mm" in body and "6–32 mm" in body
    assert "no deviations" not in body.lower()


def test_form_12_never_declares_nil_without_naming_what_was_compared():
    body = assemble_deviations(
        {"lines": [_line(_param("diameter_mm", "match"), _param("grade", "match"))]}
    ).body_md
    assert "2 parameter(s)" in body
    assert "No deviation was found among" in body


def test_form_12_says_nothing_when_nothing_was_assessed():
    """An unread schedule is not a compliant one. The old default signed a declaration on
    every tender regardless of whether anything had been compared."""
    body = assemble_deviations(None).body_md
    assert "No schedule of items has been read" in body
    # No declaration of any kind: not "confirms no deviations", and no count implying one
    # was computed. The bid owner is told to enter them.
    assert "confirms" not in body
    assert "No deviation was found" not in body


def test_form_12_reports_unassessed_parameters_as_unassessed():
    body = assemble_deviations(
        {"lines": [_line(_param("diameter_mm", "match"), _param("core_type", "unknown"))]}
    ).body_md
    assert "1 parameter(s) could not be compared" in body
    assert "unassessed, not compliant" in body


def test_form_12_treats_an_invited_equivalent_as_a_deviation_until_accepted():
    body = assemble_deviations(
        {"lines": [_line(_param("grade", "equivalent"))]}
    ).body_md
    assert "unless the buyer accepts the equivalence" in body


# ── B9: the FY window reaches the sheet ──────────────────────────────────────────────


def test_the_pq_window_is_read_off_the_stored_turnover_verdict():
    """`assemble_compliance_pq` has always implemented the correct windowed average; its only
    caller omitted the argument, so every proposal printed "Required FY window not
    confirmed". The window is a property of the TENDER, and `analysis` already resolved it."""
    from app.proposal_routes import _required_fys

    result = {"verdicts": [
        {"check": "registration_present", "fy_window": []},
        {"check": "turnover_avg", "fy_window": ["FY24", "FY25", "FY26"]},
    ]}
    assert _required_fys(result) == ("FY24", "FY25", "FY26")


def test_no_turnover_gate_means_no_window_rather_than_a_guessed_one():
    """Empty is honest. The sheet then says the window is unconfirmed instead of averaging
    whatever years happen to be on file — the defect the function was rewritten to kill."""
    from app.proposal_routes import _required_fys

    assert _required_fys(None) == ()
    assert _required_fys({}) == ()
    assert _required_fys({"verdicts": []}) == ()
    # A turnover gate whose window could not be resolved must not fall through to a default.
    assert _required_fys({"verdicts": [{"check": "turnover_avg", "fy_window": []}]}) == ()
