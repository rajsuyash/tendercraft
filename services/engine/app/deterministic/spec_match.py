"""Does what the tender asks for fall inside what the bidder can make?

Module H, the deciding half. Pure functions over typed inputs, no model imports (CI-enforced),
100% branch coverage — this module answers UML's asks 2 and 3 and nothing a model says may
reach a verdict here (PRD §2.4). The model's only job upstream is turning prose into typed
parameters; the arithmetic below is the product's answer.

ONE RULE DOES ALL THE WORK: interval intersection. A required "20 mm" is [20,20]; "18–22 mm" is
[18,22]; "MBL ≥ 200 kN" is [200,∞); an envelope of "6–60 mm" is [6,60]. Two intervals meet when
`req_min ≤ cap_max and cap_min ≤ req_max`. That is why there is no operator column in the
schema and no branch per phrasing here.

THE ASYMMETRY THAT MATTERS. A missing or unreadable parameter is UNKNOWN, never DEVIATION. A
false "we cannot make this" costs a bid the bidder would have won and is invisible — nobody
audits the tenders they were told to skip. A false "needs a human look" costs thirty seconds.
The two errors are not comparable, and every ambiguous path below resolves to the cheap one.

WHAT 'PUBLISHED' MEANS. `catalogue_state` reads the catalogue rows the BIDDER recorded. We never
read GeM to obtain or verify them — G-1 forbids portal credentials, G-8 forbids authenticated
acquisition — so every surface rendering PUBLISHED must say whose record it is. Same posture as
`coverage.py`'s NOT_FOUND, which is not a finding of non-compliance.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from .spec_params import (
    ParamKind,
    allows_equivalent,
    convert,
    describe_range,
    normalise_unit,
    normalise_value,
    spec_for,
)


class SpecMatch(StrEnum):
    MATCH = "match"           # provably inside the capability
    DEVIATION = "deviation"   # provably outside — the pre-bid clarification trigger (ask 2)
    EQUIVALENT = "equivalent" # outside, but the tender's own words invited an equivalent
    UNKNOWN = "unknown"       # cannot be decided — never a failure


class SpecOverall(StrEnum):
    CAN_SUPPLY = "can_supply"
    DEVIATION = "deviation"
    NEEDS_REVIEW = "needs_review"


class CatalogueState(StrEnum):
    PUBLISHED = "published"          # a catalogue the bidder recorded already covers this
    CREATABLE = "creatable"          # no catalogue match, but an envelope covers it
    NOT_CREATABLE = "not_creatable"  # the best envelope deviates — clarify or decline
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ParamValue:
    """One typed parameter, on either side. A point is `num_min == num_max`; a None bound is
    unbounded. `raw_text` is the substring it was read from — cite-or-flag applies to a
    parameter exactly as it applies to a sentence."""

    key: str
    kind: ParamKind
    unit: str | None = None
    num_min: float | None = None
    num_max: float | None = None
    allowed: frozenset[str] = frozenset()
    raw_text: str = ""


@dataclass(frozen=True)
class ParamMatch:
    key: str
    match: SpecMatch
    required_display: str
    capability_display: str
    reason: str


@dataclass(frozen=True)
class CapabilitySpec:
    """An envelope or a recorded catalogue item — structurally identical, which is the point."""

    id: str
    label: str
    parameters: tuple[ParamValue, ...] = ()
    gem_catalogue_id: str | None = None


@dataclass(frozen=True)
class SpecResult:
    overall: SpecOverall
    spec_id: str | None
    spec_label: str
    parameters: tuple[ParamMatch, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CatalogueDecision:
    state: CatalogueState
    result: SpecResult | None
    gem_catalogue_id: str | None = None
    #: On CREATABLE, the parameters to publish. On NOT_CREATABLE, the ones to clarify.
    action_parameters: tuple[ParamMatch, ...] = field(default_factory=tuple)


# ── one parameter ────────────────────────────────────────────────────────────────────

def _to_canonical(value: ParamValue) -> tuple[float | None, float | None, str | None] | None:
    """Both bounds in the key's canonical unit, or None when that cannot be done honestly."""
    registered = spec_for(value.key)
    canonical = registered.canonical_unit if registered else None
    stated = normalise_unit(value.unit)

    if canonical is None:
        # A dimensionless numeric (strand_count). Any stated unit is noise; compare as given.
        return value.num_min, value.num_max, None
    if stated is None:
        # GeM item descriptions say "20 dia" constantly. Assuming the key's one canonical unit
        # is right far more often than it is wrong, and the assumption is stated in `reason`
        # so a human can see it was made.
        # ponytail: if this ever mis-fires on a real tender, return None here instead and let
        # it be UNKNOWN — the honest answer costs one review, a wrong assumption costs a bid.
        return value.num_min, value.num_max, canonical

    converted: list[float | None] = []
    for bound in (value.num_min, value.num_max):
        if bound is None:
            converted.append(None)
            continue
        moved = convert(bound, stated, canonical)
        if moved is None:
            return None
        converted.append(moved)
    return converted[0], converted[1], canonical


def _intervals_meet(
    r_low: float | None, r_high: float | None, c_low: float | None, c_high: float | None
) -> bool:
    lo_r = -math.inf if r_low is None else r_low
    hi_r = math.inf if r_high is None else r_high
    lo_c = -math.inf if c_low is None else c_low
    hi_c = math.inf if c_high is None else c_high
    return lo_r <= hi_c and lo_c <= hi_r


def _numeric_match(required: ParamValue, capable: ParamValue, label: str) -> ParamMatch:
    r = _to_canonical(required)
    c = _to_canonical(capable)
    if r is None or c is None:
        return ParamMatch(
            required.key, SpecMatch.UNKNOWN,
            describe_range(required.num_min, required.num_max, required.unit),
            describe_range(capable.num_min, capable.num_max, capable.unit),
            f"{label}: {required.unit or 'no unit'} and {capable.unit or 'no unit'} are not "
            "comparable — record the capability in the same unit",
        )
    r_low, r_high, r_unit = r
    c_low, c_high, _ = c
    req_display = describe_range(r_low, r_high, r_unit)
    cap_display = describe_range(c_low, c_high, r_unit)

    assumed = ""
    if r_unit is not None and normalise_unit(required.unit) is None:
        assumed = f" (no unit stated; read as {r_unit})"

    if _intervals_meet(r_low, r_high, c_low, c_high):
        return ParamMatch(required.key, SpecMatch.MATCH, req_display, cap_display,
                          f"{label} {req_display} is within {cap_display}{assumed}")
    return ParamMatch(required.key, SpecMatch.DEVIATION, req_display, cap_display,
                      f"{label} {req_display} is outside {cap_display}{assumed}")


def _enum_match(required: ParamValue, capable: ParamValue, label: str) -> ParamMatch:
    req_values = {normalise_value(v) for v in required.allowed}
    cap_values = {normalise_value(v) for v in capable.allowed}
    req_display = " / ".join(sorted(required.allowed)) or "unspecified"
    cap_display = " / ".join(sorted(capable.allowed)) or "unspecified"

    if not req_values or not cap_values:
        return ParamMatch(required.key, SpecMatch.UNKNOWN, req_display, cap_display,
                          f"{label}: no value recorded on one side")
    if req_values & cap_values:
        return ParamMatch(required.key, SpecMatch.MATCH, req_display, cap_display,
                          f"{label} {req_display} is offered")
    # Numeric requirements are NEVER softened this way. A 22 mm rope is not "equivalent" to a
    # 20 mm one, and letting an "or equivalent" clause blur a dimension is how a bid gets
    # technically rejected after we told the bidder it was fine.
    if allows_equivalent(required.raw_text):
        return ParamMatch(required.key, SpecMatch.EQUIVALENT, req_display, cap_display,
                          f"{label} {req_display} not offered, but the tender permits an "
                          f"equivalent — confirm {cap_display} qualifies")
    return ParamMatch(required.key, SpecMatch.DEVIATION, req_display, cap_display,
                      f"{label} {req_display} not offered; you have {cap_display}")


def match_parameter(required: ParamValue, capable: ParamValue | None) -> ParamMatch:
    """Decide one parameter. Every path that cannot prove a deviation returns UNKNOWN."""
    registered = spec_for(required.key)
    label = registered.label if registered else required.key

    if capable is None:
        return ParamMatch(
            required.key, SpecMatch.UNKNOWN,
            describe_range(required.num_min, required.num_max, required.unit)
            if required.kind is ParamKind.NUMERIC
            else (" / ".join(sorted(required.allowed)) or "unspecified"),
            "not recorded",
            f"no {label.lower()} recorded in your capability — add it to compare",
        )
    if required.kind is not capable.kind:
        # A requirement read as a number against a capability recorded as a set (or the
        # reverse). Comparable only by guessing, so we do not.
        return ParamMatch(required.key, SpecMatch.UNKNOWN, required.raw_text or "—",
                          capable.raw_text or "—",
                          f"{label}: requirement and capability are recorded differently")
    if required.kind is ParamKind.NUMERIC:
        return _numeric_match(required, capable, label)
    return _enum_match(required, capable, label)


# ── one spec ─────────────────────────────────────────────────────────────────────────

def match_spec(
    required: Sequence[ParamValue], capability: CapabilitySpec
) -> SpecResult:
    """Compare a line item's requirements against one envelope or catalogue item.

    Roll-up is conservative in the shape `eligibility.recommend()` already uses: one proven
    deviation decides the row, and anything unresolved goes to a human rather than through.
    EQUIVALENT never reaches CAN_SUPPLY on its own — ET-1, borderline never auto-passes.
    """
    by_key = {p.key: p for p in capability.parameters}
    matches = tuple(match_parameter(r, by_key.get(r.key)) for r in required)

    if not matches:
        # Nothing readable was extracted. Saying "can supply" here would be a verdict about a
        # requirement we never read.
        return SpecResult(SpecOverall.NEEDS_REVIEW, capability.id, capability.label, matches)

    states = {m.match for m in matches}
    if SpecMatch.DEVIATION in states:
        overall = SpecOverall.DEVIATION
    elif states <= {SpecMatch.MATCH}:
        overall = SpecOverall.CAN_SUPPLY
    else:
        overall = SpecOverall.NEEDS_REVIEW
    return SpecResult(overall, capability.id, capability.label, matches)


#: CAN_SUPPLY beats NEEDS_REVIEW beats DEVIATION. An unresolved parameter is more hopeful than a
#: proven mismatch, so the best-of search must not let a deviating envelope hide a promising one.
_RANK = {SpecOverall.CAN_SUPPLY: 2, SpecOverall.NEEDS_REVIEW: 1, SpecOverall.DEVIATION: 0}


def best_match(
    required: Sequence[ParamValue], candidates: Sequence[CapabilitySpec]
) -> SpecResult | None:
    """The most favourable outcome across candidates, ties broken by first-listed."""
    results = [match_spec(required, c) for c in candidates]
    if not results:
        return None
    return max(results, key=lambda r: _RANK[r.overall])


# ── the two questions UML asked ──────────────────────────────────────────────────────

def catalogue_state(
    required: Sequence[ParamValue],
    catalogues: Sequence[CapabilitySpec],
    envelopes: Sequence[CapabilitySpec],
) -> CatalogueDecision:
    """Ask 3: is the catalogue for this schedule already there, or can it be created?

    Catalogues first — an existing listing is the answer that saves the most work. Only when
    none covers the line do we ask whether the plant could make it, which is what turns
    "no" into "create this SKU, with these parameters".
    """
    listed = best_match(required, catalogues)
    if listed is not None and listed.overall is SpecOverall.CAN_SUPPLY:
        gem_id = next((c.gem_catalogue_id for c in catalogues if c.id == listed.spec_id), None)
        return CatalogueDecision(CatalogueState.PUBLISHED, listed, gem_id)

    makeable = best_match(required, envelopes)
    if makeable is None:
        return CatalogueDecision(CatalogueState.UNKNOWN, None)
    if makeable.overall is SpecOverall.CAN_SUPPLY:
        # Everything needed to publish the SKU, already matched parameter by parameter.
        return CatalogueDecision(CatalogueState.CREATABLE, makeable, None, makeable.parameters)
    if makeable.overall is SpecOverall.DEVIATION:
        # The clarification list: exactly the parameters that put this outside the plant.
        blockers = tuple(m for m in makeable.parameters if m.match is SpecMatch.DEVIATION)
        return CatalogueDecision(CatalogueState.NOT_CREATABLE, makeable, None, blockers)
    gaps = tuple(m for m in makeable.parameters if m.match is not SpecMatch.MATCH)
    return CatalogueDecision(CatalogueState.UNKNOWN, makeable, None, gaps)
