"""B-FR1/B-AC3/B-AC4/B-AC2 cite-or-flag + coverage, and the deterministic class coercion.

The coercion tests are the load-bearing ones: they prove a model cannot escape a citation
by mislabelling a sentence, which is what made the B-AC4 gate unreachable before.
"""

from app.deterministic.drafting import (
    DraftSentence,
    claim_verifiability,
    classify_sentence,
    derive_flags,
    is_money_shaped,
    mandatory_coverage,
    validate_draft,
)
from app.deterministic.types import SectionKind, SentenceClass

VALID = {"chunk-1", "chunk-2"}
CLAIM, NARR = SentenceClass.CLAIM, SentenceClass.NARRATIVE
COMPLIANCE, NARRATIVE_SEC = SectionKind.COMPLIANCE, SectionKind.NARRATIVE


def _s(text="x", citations=(), cls=CLAIM, transcluded=False, source_ref=None):
    return DraftSentence(
        text=text,
        citations=tuple(citations),
        cls=cls,
        source_ref=source_ref,
        is_transcluded=transcluded,
    )


def _flags(sentences, section=COMPLIANCE):
    return validate_draft(sentences, VALID, section).flags


# --- B-FR1 cite-or-flag ---


def test_cited_fact_is_not_flagged():
    assert _flags([_s(citations=["chunk-1"])]) == ()


def test_uncited_fact_is_flagged_unverified():
    flags = _flags([_s()])
    assert len(flags) == 1
    assert flags[0].reason == "unverified"


def test_citation_that_does_not_resolve_is_flagged():
    assert _flags([_s(citations=["ghost"])])[0].reason == "unverified"


def test_narrative_sentence_needs_no_citation():
    # Pure approach prose in a narrative section: nothing exists yet to cite.
    assert _flags([_s("We adopt a phased rollout approach.", cls=NARR)], NARRATIVE_SEC) == ()


# --- B-AC4: the hard financial gate, now driven by the TEXT ---


def test_model_authored_financial_is_hard_flagged():
    flags = _flags([_s("Our turnover is Rs 8.2 Crore.", citations=["chunk-1"])])
    assert flags[0].reason == "uncited_financial"


def test_financial_gate_fires_even_with_a_resolving_citation():
    # The whole point: a citation does NOT license the model to author an amount (B-FR3).
    flags = _flags([_s("We recorded ₹12 Cr in FY24.", citations=["chunk-1", "chunk-2"])])
    assert [f.reason for f in flags] == ["uncited_financial"]


def test_transcluded_financial_is_allowed():
    # Only an assembler can set is_transcluded, and it carries a structured source_ref.
    s = _s("₹8.2 Cr", cls=SentenceClass.ASSEMBLED, transcluded=True, source_ref="fin:1.value")
    assert _flags([s]) == ()


def test_fiscal_year_reference_is_not_money():
    # Regression: "FY23–FY25" must not trip the hard gate or every real draft breaks.
    assert not is_money_shaped("turnover requirement for FY23-FY25")
    assert _flags([_s("The bidder satisfies the turnover requirement for FY23-FY25.",
                      citations=["chunk-1"])]) == ()


def test_word_quantities_are_not_money():
    assert not is_money_shaped("completed three similar works")


def test_money_shapes_recognised():
    for t in ["₹2 Cr", "Rs 8.2 Crore", "INR 40,00,000", "5 lakh", "50%", "1,20,000 crore"]:
        assert is_money_shaped(t), t


# --- classification: coercion is one-directional ---


def test_narrative_is_coerced_to_claim_outside_narrative_sections():
    assert classify_sentence(NARR, "We follow agile delivery.", COMPLIANCE) is CLAIM


def test_narrative_survives_in_a_narrative_section():
    assert classify_sentence(NARR, "We follow an agile delivery cadence.", NARRATIVE_SEC) is NARR


def test_digits_in_a_present_tense_assertion_coerce_to_claim():
    assert classify_sentence(NARR, "We employ 200 certified engineers.", NARRATIVE_SEC) is CLAIM


def test_digits_inside_a_forward_commitment_stay_narrative():
    """Regression from the first live run: 'Level 1 (L1) helpdesk' and 'the L3 team will...'
    were flagged as unsourced claims. A number inside a promise is design detail."""
    for t in [
        "We propose a Level 1 (L1) helpdesk as the single point of contact.",
        "The L3 team will handle complex system-level problems.",
        "Deployment will span 3 phases with departmental sign-off.",
    ]:
        assert classify_sentence(NARR, t, NARRATIVE_SEC) is NARR, t


def test_credential_words_coerce_narrative_to_claim():
    assert classify_sentence(NARR, "Our ISO aligned process applies.", NARRATIVE_SEC) is CLAIM


def test_deliverable_named_certificate_is_not_a_credential_claim():
    """Regression: a bare 'certif' stem matched 'Project Closure Certificate' — a work-plan
    milestone — and demanded a source document for it."""
    t = "The phase concludes with issuance of the Project Closure Certificate."
    assert classify_sentence(NARR, t, NARRATIVE_SEC) is NARR


def test_evidentiary_phrasing_coerces_narrative_to_claim():
    for t in [
        "We have delivered similar systems.",
        "We have successfully implemented a statewide automation system.",
        "Our track record includes migration of legacy databases.",
        "Our experience includes training administrative staff.",
        "We operate a dedicated disaster recovery site.",
    ]:
        assert classify_sentence(NARR, t, NARRATIVE_SEC) is CLAIM, t


def test_enumeration_labels_are_not_quantities():
    """Regression from live run 2: nine support-model sentences were flagged as unsourced
    claims because 'Tier 1' / 'Severity 3' contain digits. A label identifies, it doesn't
    quantify."""
    for t in [
        "Tier 1 support serves as the initial point of contact for all user inquiries.",
        "Incidents are systematically escalated to Tier 2 support.",
        "Critical outages are classified as Severity 1.",
        "Minor issues fall under Severity 4.",
        "Phase 2 covers requirements sign-off.",
        "We, Merdian Technology, submit our proposal in response to Tender No. MAHA/IT/2026/4415.",
    ]:
        assert classify_sentence(NARR, t, NARRATIVE_SEC) is NARR, t


def test_a_real_quantity_still_coerces_even_beside_a_label():
    t = "Tier 1 support is staffed by 40 engineers."
    assert classify_sentence(NARR, t, NARRATIVE_SEC) is CLAIM


def test_money_is_caught_regardless_of_forward_phrasing():
    """The forward-commitment exemption must never reach the hard financial gate."""
    v = validate_draft(
        [_s("We will deliver the programme for ₹8.2 Cr.", cls=NARR)], VALID, NARRATIVE_SEC
    )
    assert [f.reason for f in v.flags] == ["uncited_financial"]


def test_claim_is_never_softened_to_narrative():
    assert classify_sentence(CLAIM, "Purely stylistic prose.", NARRATIVE_SEC) is CLAIM


def test_python_only_classes_pass_through():
    assert classify_sentence(SentenceClass.ASSEMBLED, "₹8.2 Cr", COMPLIANCE) is (
        SentenceClass.ASSEMBLED
    )
    assert classify_sentence(SentenceClass.PLACEHOLDER, "⬚ insert", COMPLIANCE) is (
        SentenceClass.PLACEHOLDER
    )


def test_a_mislabelled_financial_claim_cannot_dodge_the_gate():
    """The defect this phase closes: 'narrative' + a rupee figure must still hard-block."""
    flags = _flags([_s("Our turnover is ₹8.2 Cr.", cls=NARR, citations=["chunk-1"])],
                   NARRATIVE_SEC)
    assert [f.reason for f in flags] == ["uncited_financial"]


def test_derive_flags_reads_text_not_labels():
    assert derive_flags("plain prose", CLAIM) == (True, False)
    assert derive_flags("plain prose", NARR) == (False, False)
    assert derive_flags("₹5 Cr", CLAIM) == (True, True)
    # An assembled value is a transclusion from a structured row, not an authored figure.
    assert derive_flags("₹5 Cr", SentenceClass.ASSEMBLED) == (False, False)


# --- validation result shape ---


def test_validation_reports_status_and_narrative_count():
    v = validate_draft(
        [_s("We phase the rollout.", cls=NARR), _s(citations=["chunk-1"])],
        VALID,
        NARRATIVE_SEC,
    )
    assert v.status == "drafted"
    assert v.narrative_sentences == 1
    assert v.claim_verifiability == 1.0


def test_validation_status_flips_on_any_flag():
    assert validate_draft([_s()], VALID, COMPLIANCE).status == "unverified"


def test_default_section_is_the_strict_one():
    # Callers that don't opt in to narrative get today's behaviour exactly.
    assert validate_draft([_s(cls=NARR)], VALID).sentences[0].cls is CLAIM


# --- B-AC3 ---


def test_verifiability_ratio():
    v = validate_draft([_s(citations=["chunk-1"]), _s(), _s(cls=NARR)], VALID, NARRATIVE_SEC)
    assert v.claim_verifiability == 0.5


def test_verifiability_no_facts_is_one():
    assert claim_verifiability([_s(cls=NARR)], VALID) == 1.0


# --- B-AC2 coverage ---


def test_coverage_counts_placeholder_as_addressed():
    criteria = [
        {"requirement_level": "mandatory", "draft_status": "drafted"},
        {"requirement_level": "mandatory", "draft_status": "placeholder"},
        {"requirement_level": "mandatory", "draft_status": "missing"},
    ]
    assert mandatory_coverage(criteria) == 2 / 3


def test_coverage_ignores_desirable():
    criteria = [
        {"requirement_level": "mandatory", "draft_status": "drafted"},
        {"requirement_level": "desirable", "draft_status": "missing"},
    ]
    assert mandatory_coverage(criteria) == 1.0


def test_coverage_no_mandatory_is_full():
    assert mandatory_coverage([{"requirement_level": "desirable", "draft_status": "missing"}]) == 1.0


# --- unfilled template detection (an uploaded blank form is not evidence) ---


def test_detects_square_bracket_placeholders():
    from app.deterministic.drafting import template_placeholders

    found = template_placeholders(
        "I, [Insert Name], as the [Insert Designation] of Merdian Technology, declare..."
    )
    assert "[Insert Name]" in found
    assert "[Insert Designation]" in found


def test_detects_other_common_marker_styles():
    from app.deterministic.drafting import template_placeholders

    assert template_placeholders("Signed by <<Authorised Signatory>>")
    assert template_placeholders("Company: {{company_name}}")
    assert template_placeholders("Name: __________")


def test_a_filled_document_reports_nothing():
    from app.deterministic.drafting import template_placeholders

    assert template_placeholders(
        "I, Priya Sharma, as the Managing Director of Meridian Infotech Pvt Ltd, declare "
        "that the firm has not been blacklisted by any department."
    ) == []


def test_ordinary_brackets_are_not_placeholders():
    from app.deterministic.drafting import template_placeholders

    assert template_placeholders("Turnover [see Annexure A] exceeds the threshold.") == []


def test_results_are_deduplicated_and_capped():
    from app.deterministic.drafting import template_placeholders

    text = " ".join(["[Insert Name]"] * 20)
    assert template_placeholders(text) == ["[Insert Name]"]
