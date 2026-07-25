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


def test_digits_coerce_narrative_to_claim():
    assert classify_sentence(NARR, "Deployment spans 3 phases.", NARRATIVE_SEC) is CLAIM


def test_credential_words_coerce_narrative_to_claim():
    assert classify_sentence(NARR, "Our ISO aligned process applies.", NARRATIVE_SEC) is CLAIM


def test_evidentiary_phrasing_coerces_narrative_to_claim():
    assert classify_sentence(NARR, "We have delivered similar systems.", NARRATIVE_SEC) is CLAIM


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
