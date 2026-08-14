"""Module H comparator — the arithmetic that decides whether UML can supply a schedule line.

100% branch coverage is CI-gated on app/deterministic/. These tests exist for a sharper reason
than the number: every wrong answer here is silent. A false DEVIATION tells a manufacturer to
skip a tender they would have won, and nobody ever audits the bids they were told not to make.
"""

from __future__ import annotations

import pytest

from app.deterministic.spec_match import (
    CapabilitySpec,
    CatalogueState,
    ParamKind,
    ParamValue,
    SpecMatch,
    SpecOverall,
    best_match,
    catalogue_state,
    match_parameter,
    match_spec,
)
from app.deterministic.spec_params import (
    PARAM_KEYS,
    REGISTRY,
    allows_equivalent,
    convert,
    describe_range,
    normalise_unit,
    normalise_value,
    spec_for,
)


def num(key, low, high=..., unit=None, raw=""):
    """A numeric parameter. One bound means a point value, which is the common case."""
    return ParamValue(key, ParamKind.NUMERIC, unit=unit, num_min=low,
                      num_max=low if high is ... else high, raw_text=raw)


def enum(key, *values, raw=""):
    return ParamValue(key, ParamKind.ENUM, allowed=frozenset(values), raw_text=raw)


def envelope(*params, id="env-1", label="Rope envelope", gem=None):
    return CapabilitySpec(id=id, label=label, parameters=tuple(params), gem_catalogue_id=gem)


# ── interval intersection: the one rule ──────────────────────────────────────────────

@pytest.mark.parametrize("req_low,req_high,cap_low,cap_high,expected", [
    (20, 20, 6, 60, SpecMatch.MATCH),        # a point inside an envelope — the common case
    (20, 20, 24, 60, SpecMatch.DEVIATION),   # below the plant's smallest
    (72, 72, 6, 60, SpecMatch.DEVIATION),    # above the plant's largest
    (6, 6, 6, 60, SpecMatch.MATCH),          # exactly the lower bound, inclusive
    (60, 60, 6, 60, SpecMatch.MATCH),        # exactly the upper bound, inclusive
    (18, 22, 20, 60, SpecMatch.MATCH),       # ranges that overlap partially still meet
    (18, 22, 24, 60, SpecMatch.DEVIATION),   # ranges that do not touch
    (200, None, 100, 500, SpecMatch.MATCH),  # "at least 200" against a bounded capability
    (600, None, 100, 500, SpecMatch.DEVIATION),
    (None, 30, 6, 60, SpecMatch.MATCH),      # "at most 30"
    (None, 4, 6, 60, SpecMatch.DEVIATION),
    (20, 20, 6, None, SpecMatch.MATCH),      # an open-ended capability
    (20, 20, None, 60, SpecMatch.MATCH),
])
def test_a_requirement_meets_a_capability_when_their_intervals_intersect(
    req_low, req_high, cap_low, cap_high, expected
):
    got = match_parameter(num("diameter", req_low, req_high, unit="mm"),
                          num("diameter", cap_low, cap_high, unit="mm"))
    assert got.match is expected


def test_an_out_of_range_diameter_names_both_sides_so_the_gap_is_actionable():
    got = match_parameter(num("diameter", 72, unit="mm"), num("diameter", 6, 60, unit="mm"))
    assert got.match is SpecMatch.DEVIATION
    assert got.required_display == "72 mm"
    assert got.capability_display == "6–60 mm"
    assert "outside" in got.reason


# ── the asymmetry: unknown is never a failure ────────────────────────────────────────

def test_a_capability_we_never_recorded_is_unknown_not_a_deviation():
    """The decisive test in the file. If this ever returns DEVIATION, an incomplete envelope
    silently tells the bidder they cannot make things they make every day."""
    got = match_parameter(num("core_type", 1), None)
    assert got.match is SpecMatch.UNKNOWN
    assert got.capability_display == "not recorded"


def test_incomparable_units_are_unknown_rather_than_a_guess():
    got = match_parameter(num("min_breaking_load", 200, unit="kN"),
                          num("min_breaking_load", 500, unit="kg"))
    assert got.match is SpecMatch.UNKNOWN
    assert "not comparable" in got.reason


def test_a_requirement_and_a_capability_recorded_as_different_kinds_is_unknown():
    got = match_parameter(num("tensile_grade", 1960, unit="N/mm2"),
                          enum("tensile_grade", "1960"))
    assert got.match is SpecMatch.UNKNOWN
    assert "recorded differently" in got.reason


def test_an_enum_with_no_values_on_either_side_is_unknown():
    assert match_parameter(enum("finish"), enum("finish", "galvanised")).match is SpecMatch.UNKNOWN
    assert match_parameter(enum("finish", "galvanised"), enum("finish")).match is SpecMatch.UNKNOWN


# ── units ────────────────────────────────────────────────────────────────────────────

def test_units_are_converted_before_comparison():
    """2 cm is 20 mm. A plant that records centimetres must not fail a millimetre tender."""
    got = match_parameter(num("diameter", 2.0, unit="cm"), num("diameter", 6, 60, unit="mm"))
    assert got.match is SpecMatch.MATCH


@pytest.mark.parametrize("value,unit,expected_mm", [
    (1, "in", 25.4), (1, "inch", 25.4), (1, '"', 25.4), (1, "ft", 304.8), (1, "m", 1000.0),
])
def test_imperial_and_metric_lengths_land_on_the_same_number(value, unit, expected_mm):
    assert convert(value, unit, "mm") == pytest.approx(expected_mm)


@pytest.mark.parametrize("unit,expected", [
    ("N/mm²", "n/mm2"), ("N/mm2", "n/mm2"), ("MPa", "mpa"), (" KN ", "kn"), ("", None),
    (None, None), ("mm.", "mm"),
])
def test_unit_spellings_a_tender_actually_uses_all_fold(unit, expected):
    assert normalise_unit(unit) == expected


def test_mpa_and_n_per_mm2_are_the_same_stress():
    assert convert(1960, "MPa", "N/mm2") == pytest.approx(1960)


def test_a_tonne_is_force_not_mass_so_a_weight_in_tonnes_refuses_to_convert():
    """Indian rope specs quote breaking loads in tonnes and coil weights in kg. Mapping the
    token to both dimensions would make the comparator guess; refusing is the honest answer."""
    assert convert(1, "tonne", "kN") == pytest.approx(9.80665)
    assert convert(1, "tonne", "kg") is None


def test_an_unrecognised_unit_never_converts():
    assert convert(5, "furlong", "mm") is None
    assert convert(5, "mm", "furlong") is None


def test_converting_with_a_unit_on_only_one_side_refuses():
    """`convert` is public and its callers are not all in this package. On its own it cannot
    know whether a bare number was metres or millimetres — only the key knows that, which is
    why the canonical-unit assumption lives in `_to_canonical` and not here."""
    assert convert(5, None, "mm") is None
    assert convert(5, "mm", None) is None
    assert convert(5, None, None) == 5  # nothing stated either side: compare as given


def test_a_bare_number_is_read_in_the_keys_canonical_unit_and_says_so():
    """GeM item descriptions say "20 dia" constantly. The assumption is made, and stated."""
    got = match_parameter(num("diameter", 20, unit=None), num("diameter", 6, 60, unit="mm"))
    assert got.match is SpecMatch.MATCH
    assert "read as mm" in got.reason


def test_a_dimensionless_parameter_compares_without_units():
    got = match_parameter(num("strand_count", 6), num("strand_count", 6, 8))
    assert got.match is SpecMatch.MATCH


def test_only_the_stated_bound_is_converted_when_the_other_is_open():
    got = match_parameter(num("length", 1000, None, unit="m"), num("length", 0, 5000, unit="m"))
    assert got.match is SpecMatch.MATCH


# ── enums, folding, and "or equivalent" ──────────────────────────────────────────────

@pytest.mark.parametrize("written", ["6x36", "6X36", "6 × 36", "6 x 36", " 6x36 "])
def test_one_construction_written_five_ways_is_one_construction(written):
    got = match_parameter(enum("construction", written), enum("construction", "6x36"))
    assert got.match is SpecMatch.MATCH


def test_a_hyphen_is_not_a_construction_separator():
    """'6-36' is not folded into '6x36', deliberately. A hyphen overwhelmingly means a RANGE in
    tender prose ('6-36 mm'), so reading it as a strand separator would invent a match on a
    parameter nobody stated. The cost of being strict here is one review; the cost of being
    loose is a bid submitted against a construction the plant does not make."""
    got = match_parameter(enum("construction", "6-36"), enum("construction", "6x36"))
    assert got.match is SpecMatch.DEVIATION


@pytest.mark.parametrize("written", ["IS 2266", "IS:2266", "IS-2266", "is2266"])
def test_a_standard_reference_folds_across_punctuation(written):
    got = match_parameter(enum("standard_ref", written), enum("standard_ref", "IS 2266"))
    assert got.match is SpecMatch.MATCH


@pytest.mark.parametrize("written,canonical", [
    ("Galvanized", "galvanised"), ("Zinc Coated", "galvanised"), ("GI", "galvanised"),
    ("Black", "ungalvanised"), ("Bright", "ungalvanised"),
    ("Independent Wire Rope Core", "iwrc"), ("Fibre Core", "fc"),
    ("Right Hand Ordinary Lay", "rhol"),
])
def test_spelling_variants_that_would_otherwise_lose_a_bid(written, canonical):
    assert normalise_value(written) == canonical


def test_a_capability_offering_both_finishes_matches_either_requirement():
    both = enum("finish", "galvanised", "ungalvanised")
    assert match_parameter(enum("finish", "galvanised"), both).match is SpecMatch.MATCH
    assert match_parameter(enum("finish", "black"), both).match is SpecMatch.MATCH


def test_an_unmatched_enum_deviates_when_the_tender_demands_that_exact_thing():
    got = match_parameter(enum("core_type", "IWRC"), enum("core_type", "FC"))
    assert got.match is SpecMatch.DEVIATION
    assert "you have" in got.reason


@pytest.mark.parametrize("clause", [
    "Core shall be IWRC or equivalent", "IWRC or similar", "IWRC or equal",
    "equivalent to IWRC", "IWRC or better", "IWRC or approved equal",
])
def test_the_tenders_own_words_can_soften_an_enum_to_equivalent(clause):
    got = match_parameter(enum("core_type", "IWRC", raw=clause), enum("core_type", "FC"))
    assert got.match is SpecMatch.EQUIVALENT
    assert "confirm" in got.reason


def test_equivalence_never_softens_a_number():
    """A 22 mm rope is not equivalent to a 20 mm one. Letting an 'or equivalent' clause blur a
    dimension is how a bid is technically rejected after we told the bidder it was fine."""
    got = match_parameter(num("diameter", 72, unit="mm", raw="72 mm dia or equivalent"),
                          num("diameter", 6, 60, unit="mm"))
    assert got.match is SpecMatch.DEVIATION


def test_equivalence_is_read_from_the_requirement_text_only():
    """It is derived in Python from the tender's words, so no model can set the field that
    softens its own verdict — the `is_financial` defect in known-pitfalls, not repeated."""
    assert allows_equivalent("or equivalent") is True
    assert allows_equivalent("the equivalent circuit shall be earthed") is False
    assert allows_equivalent("") is False


# ── rolling up a whole line item ─────────────────────────────────────────────────────

def test_all_parameters_matching_means_the_bidder_can_supply():
    result = match_spec(
        [num("diameter", 20, unit="mm"), enum("construction", "6x36")],
        envelope(num("diameter", 6, 60, unit="mm"), enum("construction", "6x36", "6x19")),
    )
    assert result.overall is SpecOverall.CAN_SUPPLY


def test_one_deviation_decides_the_line_however_much_else_matches():
    result = match_spec(
        [num("diameter", 20, unit="mm"), enum("core_type", "IWRC")],
        envelope(num("diameter", 6, 60, unit="mm"), enum("core_type", "FC")),
    )
    assert result.overall is SpecOverall.DEVIATION


def test_an_unknown_holds_the_line_at_needs_review_rather_than_passing_it():
    result = match_spec(
        [num("diameter", 20, unit="mm"), enum("core_type", "IWRC")],
        envelope(num("diameter", 6, 60, unit="mm")),
    )
    assert result.overall is SpecOverall.NEEDS_REVIEW


def test_an_equivalent_never_reaches_can_supply_on_its_own():
    """ET-1: borderline never auto-passes. Someone must confirm the equivalent qualifies."""
    result = match_spec(
        [enum("core_type", "IWRC", raw="IWRC or equivalent")],
        envelope(enum("core_type", "FC")),
    )
    assert result.overall is SpecOverall.NEEDS_REVIEW


def test_a_line_item_with_nothing_readable_is_needs_review_not_can_supply():
    """Zero requirements would vacuously satisfy 'all matched'. Saying can_supply here is a
    verdict about a requirement we never read."""
    result = match_spec([], envelope(num("diameter", 6, 60, unit="mm")))
    assert result.overall is SpecOverall.NEEDS_REVIEW
    assert result.parameters == ()


def test_a_deviation_beside_an_unknown_still_deviates():
    result = match_spec(
        [num("diameter", 72, unit="mm"), enum("core_type", "IWRC")],
        envelope(num("diameter", 6, 60, unit="mm")),
    )
    assert result.overall is SpecOverall.DEVIATION


# ── best-of across several envelopes ─────────────────────────────────────────────────

def test_the_most_favourable_envelope_wins_and_a_deviating_one_cannot_hide_it():
    small = envelope(num("diameter", 6, 24, unit="mm"), id="small", label="Small line")
    large = envelope(num("diameter", 25, 60, unit="mm"), id="large", label="Heavy line")
    result = best_match([num("diameter", 40, unit="mm")], [small, large])
    assert result.overall is SpecOverall.CAN_SUPPLY
    assert result.spec_id == "large"


def test_needs_review_is_preferred_over_a_proven_deviation():
    unknown_side = envelope(enum("finish", "galvanised"), id="u")
    deviating = envelope(num("diameter", 6, 10, unit="mm"), id="d")
    result = best_match([num("diameter", 40, unit="mm")], [unknown_side, deviating])
    assert result.overall is SpecOverall.NEEDS_REVIEW
    assert result.spec_id == "u"


def test_best_match_over_nothing_is_none():
    assert best_match([num("diameter", 20, unit="mm")], []) is None


# ── ask 3: is the catalogue there, or can it be made ─────────────────────────────────

REQ = [num("diameter", 20, unit="mm"), enum("construction", "6x36")]
PLANT = envelope(num("diameter", 6, 60, unit="mm"), enum("construction", "6x36", "6x19"),
                 id="env", label="Rope plant")


def test_an_existing_listing_is_reported_with_the_sku_that_covers_it():
    listed = envelope(num("diameter", 20, unit="mm"), enum("construction", "6x36"),
                      id="cat", label="SKU-4471", gem="GEM-CAT-4471")
    decision = catalogue_state(REQ, [listed], [PLANT])
    assert decision.state is CatalogueState.PUBLISHED
    assert decision.gem_catalogue_id == "GEM-CAT-4471"


def test_no_listing_but_the_plant_can_make_it_yields_the_parameters_to_publish():
    decision = catalogue_state(REQ, [], [PLANT])
    assert decision.state is CatalogueState.CREATABLE
    assert {p.key for p in decision.action_parameters} == {"diameter", "construction"}


def test_a_listing_that_does_not_cover_the_line_falls_through_to_the_envelope():
    wrong_sku = envelope(num("diameter", 8, unit="mm"), enum("construction", "6x19"), id="cat")
    decision = catalogue_state(REQ, [wrong_sku], [PLANT])
    assert decision.state is CatalogueState.CREATABLE


def test_outside_the_plant_names_exactly_the_parameters_to_clarify():
    """This is ask 2's deliverable: the pre-bid clarification list, not a verdict."""
    decision = catalogue_state(
        [num("diameter", 72, unit="mm"), enum("construction", "6x36")], [], [PLANT]
    )
    assert decision.state is CatalogueState.NOT_CREATABLE
    assert [p.key for p in decision.action_parameters] == ["diameter"]


def test_an_unresolved_line_is_unknown_and_lists_what_is_missing():
    decision = catalogue_state([enum("core_type", "IWRC")], [], [PLANT])
    assert decision.state is CatalogueState.UNKNOWN
    assert [p.key for p in decision.action_parameters] == ["core_type"]


def test_with_no_envelope_recorded_at_all_nothing_can_be_concluded():
    decision = catalogue_state(REQ, [], [])
    assert decision.state is CatalogueState.UNKNOWN
    assert decision.result is None


# ── the registry itself ──────────────────────────────────────────────────────────────

def test_every_registered_key_is_reachable_and_self_consistent():
    for key in PARAM_KEYS:
        spec = spec_for(key)
        assert spec is not None and spec.key == key
        # A numeric key either has a canonical unit or is deliberately dimensionless.
        if spec.kind is ParamKind.ENUM:
            assert spec.canonical_unit is None


def test_the_allowlist_is_the_registry_so_a_model_cannot_invent_a_parameter():
    assert set(PARAM_KEYS) == set(REGISTRY)
    assert PARAM_KEYS == tuple(sorted(PARAM_KEYS))


def test_an_unregistered_key_still_compares_and_falls_back_to_its_own_name():
    got = match_parameter(num("unregistered_thing", 5), num("unregistered_thing", 1, 10))
    assert got.match is SpecMatch.MATCH
    assert spec_for("unregistered_thing") is None


@pytest.mark.parametrize("low,high,unit,expected", [
    (20, 20, "mm", "20 mm"),
    (6, 60, "mm", "6–60 mm"),
    (200, None, "kN", "≥ 200 kN"),
    (None, 60, "mm", "≤ 60 mm"),
    (None, None, "mm", "unspecified"),
    (6.35, 6.35, None, "6.35"),
])
def test_an_interval_reads_the_same_everywhere_it_is_rendered(low, high, unit, expected):
    assert describe_range(low, high, unit) == expected
