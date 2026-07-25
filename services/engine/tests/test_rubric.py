"""Technical-competence rubric — deterministic scoring + computed improvement deltas."""

import pytest

from app.deterministic.rubric import (
    DIMENSIONS,
    MIN_AGGREGATE_FRACTION,
    MIN_DIMENSION_FRACTION,
    SectionFeatures,
    score_proposal,
)


def _sec(key, words=1000, target=1000, present=True, status="drafted",
         approved=True, subs=4, cv=1.0):
    return SectionFeatures(
        key=key, present=present, status=status, word_count=words, target_words=target,
        claim_verifiability=cv, subsection_count=subs, approved=approved,
    )


ALL_KEYS = [k for d in DIMENSIONS for k in d.sections]


def _perfect():
    return score_proposal(
        [_sec(k) for k in ALL_KEYS],
        cv_count=5, matching_experience=5, required_experience=3, valid_cert_fraction=1.0,
    )


def _empty():
    return score_proposal([], cv_count=0, matching_experience=0, valid_cert_fraction=0.0)


# --- weights and gates ---


def test_weights_sum_to_one_hundred():
    assert sum(d.weight for d in DIMENSIONS) == 100


def test_feature_weights_sum_to_one_per_dimension():
    for d in DIMENSIONS:
        assert sum(d.features.values()) == pytest.approx(1.0), d.key


def test_the_real_evaluation_gates_are_modelled():
    # CAG OIOS §7.7.4: >=45% per section AND >=65% aggregate, else technically rejected.
    assert MIN_DIMENSION_FRACTION == 0.45
    assert MIN_AGGREGATE_FRACTION == 0.65


# --- range ---


def test_a_complete_proposal_scores_full_marks():
    r = _perfect()
    assert r.total == 100.0
    assert r.technically_qualified
    assert r.failing_dimensions == ()
    assert r.suggestions == ()  # nothing left to recommend


def test_an_empty_proposal_scores_zero_and_is_disqualified():
    r = _empty()
    assert r.total == 0.0
    assert not r.technically_qualified
    assert not r.meets_aggregate_minimum
    assert len(r.failing_dimensions) == len(DIMENSIONS)


def test_score_is_reproducible():
    assert _perfect().total == _perfect().total


# --- the score actually reads the document ---


def test_a_short_section_scores_less_than_a_full_one():
    full = score_proposal([_sec("solution", words=3000, target=3000)])
    thin = score_proposal([_sec("solution", words=300, target=3000)])
    assert thin.total < full.total


def test_padding_does_not_buy_marks():
    """'Never pad with unsupported prose' as a scoring property, not just a prompt line."""
    right = score_proposal([_sec("solution", words=3000, target=3000)])
    padded = score_proposal([_sec("solution", words=30000, target=3000)])
    assert padded.total < right.total


def test_a_placeholder_section_earns_no_presence():
    r = score_proposal([_sec("qa", status="placeholder")])
    qa = next(d for d in r.dimensions if d.key == "qa")
    assert qa.features["presence"] == 0.0


def test_unapproved_narrative_costs_marks():
    approved = score_proposal([_sec("risk", approved=True)])
    unapproved = score_proposal([_sec("risk", approved=False)])
    assert unapproved.total < approved.total


def test_uncited_claims_cost_marks():
    clean = score_proposal([_sec("solution", cv=1.0)])
    dirty = score_proposal([_sec("solution", cv=0.2)])
    assert dirty.total < clean.total


# --- evidence-backed dimensions ---


def test_team_score_tracks_cv_count():
    lo = score_proposal([_sec("team_composition"), _sec("cvs"), _sec("deployment")], cv_count=0)
    hi = score_proposal([_sec("team_composition"), _sec("cvs"), _sec("deployment")], cv_count=3)
    assert hi.total > lo.total


def test_experience_score_tracks_matching_records():
    lo = score_proposal([_sec("project_citations")], matching_experience=0, required_experience=3)
    hi = score_proposal([_sec("project_citations")], matching_experience=3, required_experience=3)
    assert hi.total > lo.total


def test_no_experience_requirement_is_not_a_penalty():
    r = score_proposal([_sec("project_citations")], matching_experience=0, required_experience=0)
    exp = next(d for d in r.dimensions if d.key == "experience")
    assert exp.features["matching_records"] == 1.0


# --- suggestions: computed, actionable, ordered ---


def test_suggestions_are_ordered_by_recoverable_marks():
    deltas = [s.expected_delta for s in _empty().suggestions]
    assert deltas == sorted(deltas, reverse=True)


def test_expected_delta_is_computed_not_a_fixed_string():
    """Replaces estimator.py's hardcoded '+2-5 marks' / '+1-3 marks'."""
    for s in _empty().suggestions:
        assert isinstance(s.expected_delta, float)
        assert s.expected_delta > 0


def test_recoverable_marks_reconcile_with_the_total():
    r = _empty()
    assert sum(s.expected_delta for s in r.suggestions) == pytest.approx(100.0, abs=0.5)


def test_every_suggestion_carries_a_stable_action_code_and_advice():
    for s in _empty().suggestions:
        assert s.action_code.isupper()
        assert len(s.advice) > 20
        assert s.observed["feature"]


def test_missing_cvs_recommends_attaching_them():
    r = score_proposal([_sec("team_composition"), _sec("cvs"), _sec("deployment")], cv_count=0)
    codes = {s.action_code for s in r.suggestions}
    assert "ATTACH_CV" in codes


def test_unapproved_section_recommends_approval():
    r = score_proposal([_sec("risk", approved=False)])
    assert "APPROVE_SECTION" in {s.action_code for s in r.suggestions}


def test_trivial_gaps_are_not_reported():
    r = score_proposal([_sec("solution", words=2999, target=3000)])
    solution = [s for s in r.suggestions if s.dimension == "solution_architecture"]
    assert all(s.expected_delta >= 0.1 for s in solution)


# --- the two-gate verdict ---


def test_a_strong_aggregate_with_one_weak_dimension_is_still_rejected():
    """The gate real committees apply: aggregate alone is not enough."""
    secs = [_sec(k) for k in ALL_KEYS if k != "qa"]
    secs.append(_sec("qa", present=False, status="placeholder", approved=False, words=0))
    r = score_proposal(secs, cv_count=5, matching_experience=5, valid_cert_fraction=1.0)
    assert r.meets_aggregate_minimum          # still well above 65
    assert "qa" in r.failing_dimensions       # but below 45% on one head
    assert not r.technically_qualified


def test_a_section_with_no_word_target_is_not_penalised_on_depth():
    """A section carrying no word target (a table) must not be scored on length."""
    r = score_proposal([_sec("qa", words=20, target=0)])
    qa = next(d for d in r.dimensions if d.key == "qa")
    assert qa.features["depth"] == 1.0


def test_every_declared_feature_resolves_to_a_computation():
    # A typo in DIMENSIONS.features must raise, not silently score zero.
    for d in DIMENSIONS:
        r = score_proposal([_sec(k) for k in d.sections])
        got = next(x for x in r.dimensions if x.key == d.key)
        assert set(got.features) == set(d.features), d.key


def test_a_sub_tenth_of_a_mark_gap_is_not_reported():
    # risk: weight 4 x depth weight 0.45 = 1.8 max; a 5% shortfall is 0.09 -> below the floor.
    r = score_proposal([_sec("risk", words=950, target=1000)])
    depth_hints = [
        s for s in r.suggestions
        if s.dimension == "risk" and s.observed["feature"] == "depth"
    ]
    assert depth_hints == []


def test_max_gain_is_the_headroom_on_each_dimension():
    for d in _empty().dimensions:
        assert d.max_gain == pytest.approx(d.weight)
    for d in _perfect().dimensions:
        assert d.max_gain == pytest.approx(0.0)
