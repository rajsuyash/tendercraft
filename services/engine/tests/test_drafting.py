"""B-FR1/B-AC3/B-AC4/B-AC2 cite-or-flag + coverage."""

from app.deterministic.drafting import (
    DraftSentence,
    claim_verifiability,
    mandatory_coverage,
    validate_citations,
)

VALID = {"chunk-1", "chunk-2"}


def _s(text="x", citations=(), requires=False, financial=False, transcluded=False):
    return DraftSentence(text, tuple(citations), requires, financial, transcluded)


def test_cited_fact_is_not_flagged():
    flags = validate_citations([_s(citations=["chunk-1"], requires=True)], VALID)
    assert flags == ()


def test_uncited_fact_is_flagged_unverified():
    flags = validate_citations([_s(requires=True)], VALID)
    assert len(flags) == 1
    assert flags[0].reason == "unverified"


def test_citation_that_does_not_resolve_is_flagged():
    flags = validate_citations([_s(citations=["ghost"], requires=True)], VALID)
    assert flags[0].reason == "unverified"


def test_non_fact_sentence_needs_no_citation():
    assert validate_citations([_s(requires=False)], VALID) == ()


def test_model_authored_financial_is_hard_flagged():
    # B-AC4: a financial value the model wrote (not transcluded) can never stand
    flags = validate_citations([_s(financial=True, transcluded=False, requires=True)], VALID)
    assert flags[0].reason == "uncited_financial"


def test_transcluded_financial_is_allowed():
    assert validate_citations([_s(financial=True, transcluded=True)], VALID) == ()


def test_verifiability_ratio():
    sents = [
        _s(citations=["chunk-1"], requires=True),
        _s(requires=True),  # unverified
        _s(requires=False),  # not a fact — excluded
    ]
    assert claim_verifiability(sents, VALID) == 0.5


def test_verifiability_no_facts_is_one():
    assert claim_verifiability([_s(requires=False)], VALID) == 1.0


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
