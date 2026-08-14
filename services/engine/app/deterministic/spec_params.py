"""The canonical parameter registry — what a spec parameter can be, and how to compare units.

Module H, deterministic half. No model imports, ever: this module decides what two values MEAN
before `spec_match` decides whether they meet, and a model that could rename a parameter or
invent a unit would be deciding eligibility by the back door (PRD §2.4).

The registry is a module-level dict rather than a table. A dict is a table without a migration,
and the contents are the only genuinely domain-specific thing in Module H — the schema and the
comparator know nothing about rope. Domain knowledge stays data.
# ponytail: registry is a module dict; move it to a workspace-scoped table the first time a
# customer needs to add a parameter without a deploy.

`param_key` is an ALLOWLIST. The extractor's JSON schema renders its enum from `REGISTRY`, which
is what stops a hostile tender document inventing a parameter name (G-6) — the same posture the
criterion extractor takes with its category enum.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import StrEnum


class ParamKind(StrEnum):
    """Two kinds, deliberately.

    Galvanisation is an ENUM ('galvanised' / 'ungalvanised'), not a boolean, so "we do both" is
    a two-value allowed set rather than a third meaning for NULL — and NULL already carries the
    load-bearing meaning "absent, therefore unknown". Every kind added here is a branch the
    100%-branch-coverage gate on this package has to carry, so add one only when a real
    requirement cannot be expressed without it.
    """

    NUMERIC = "numeric"
    ENUM = "enum"


@dataclass(frozen=True)
class ParamSpec:
    key: str
    kind: ParamKind
    label: str
    #: Both sides normalise to this before comparison. None for dimensionless enums.
    canonical_unit: str | None = None
    #: Rendered into the extractor prompt so the model maps a tender's wording onto our key.
    synonyms: tuple[str, ...] = ()


# Nine rope parameters, five that any manufactured good has. UML's ten GeM categories are the
# seed, not the design: MIG welding wire shares almost nothing with the eight rope standards
# beside it, which is why a fixed-column schema was rejected — the generic model is required
# *within* the first customer, before a second one is even a question.
_SPECS: tuple[ParamSpec, ...] = (
    # -- universal --------------------------------------------------------------------
    ParamSpec("diameter", ParamKind.NUMERIC, "Diameter", "mm",
              ("dia", "nominal diameter", "size", "rope diameter", "nominal size")),
    ParamSpec("length", ParamKind.NUMERIC, "Length", "m",
              ("coil length", "delivery length", "cut length")),
    ParamSpec("weight", ParamKind.NUMERIC, "Weight", "kg",
              ("mass", "unit weight", "coil weight")),
    ParamSpec("standard_ref", ParamKind.ENUM, "Standard",
              synonyms=("as per", "conforming to", "specification", "is standard", "grade std")),
    ParamSpec("finish", ParamKind.ENUM, "Finish",
              synonyms=("coating", "galvanisation", "surface finish", "zinc coating")),
    # -- steel wire rope --------------------------------------------------------------
    ParamSpec("construction", ParamKind.ENUM, "Construction",
              synonyms=("rope construction", "strand construction", "lay construction")),
    ParamSpec("core_type", ParamKind.ENUM, "Core",
              synonyms=("core", "rope core", "iwrc", "fibre core")),
    ParamSpec("tensile_grade", ParamKind.NUMERIC, "Tensile grade", "N/mm2",
              ("tensile designation", "wire grade", "tensile strength", "rope grade")),
    ParamSpec("min_breaking_load", ParamKind.NUMERIC, "Minimum breaking load", "kN",
              ("mbl", "breaking load", "minimum breaking force", "breaking strength")),
    ParamSpec("lay_direction", ParamKind.ENUM, "Lay",
              synonyms=("lay", "lay type", "rope lay")),
    ParamSpec("strand_count", ParamKind.NUMERIC, "Strands",
              synonyms=("number of strands", "strands")),
    # -- welding consumables ----------------------------------------------------------
    ParamSpec("wire_class", ParamKind.ENUM, "Wire class",
              synonyms=("aws class", "classification", "electrode class")),
    ParamSpec("spool_weight", ParamKind.NUMERIC, "Spool weight", "kg",
              ("reel weight", "package weight", "spool size")),
    ParamSpec("shielding_gas", ParamKind.ENUM, "Shielding gas",
              synonyms=("gas", "shielding")),
)

REGISTRY: dict[str, ParamSpec] = {spec.key: spec for spec in _SPECS}

#: The allowlist the extractor's JSON schema renders. Sorted so a prompt diff is reviewable.
PARAM_KEYS: tuple[str, ...] = tuple(sorted(REGISTRY))


def spec_for(key: str) -> ParamSpec | None:
    """None for an unknown key. The caller drops it — an unregistered parameter is either a
    stale row or a model that ignored its enum, and neither should reach a verdict."""
    return REGISTRY.get(key)


# ── units ────────────────────────────────────────────────────────────────────────────

# Unit -> (dimension, factor to that dimension's SI base). A unit belongs to exactly one
# dimension, so a conversion is only ever attempted between comparable quantities.
#
# 'tonne' is deliberately FORCE (tonne-force, 9806.65 N) and absent from mass. Indian rope
# specifications quote breaking loads in tonnes constantly and coil weights in kg; mapping it to
# both would make the token ambiguous, and the comparator would have to guess. A weight stated
# in tonnes is therefore unconvertible and reports UNKNOWN — the honest answer, and one a human
# can fix by typing kg.
_UNIT_TO_BASE: dict[str, tuple[str, float]] = {
    # length, base metre
    "mm": ("length", 0.001), "cm": ("length", 0.01), "m": ("length", 1.0),
    "in": ("length", 0.0254), "inch": ("length", 0.0254), '"': ("length", 0.0254),
    "ft": ("length", 0.3048),
    # force, base newton
    "n": ("force", 1.0), "kn": ("force", 1000.0), "kgf": ("force", 9.80665),
    "tonne": ("force", 9806.65), "te": ("force", 9806.65), "tonnef": ("force", 9806.65),
    # stress, base pascal
    "n/mm2": ("stress", 1.0e6), "mpa": ("stress", 1.0e6), "kn/mm2": ("stress", 1.0e9),
    "ksi": ("stress", 6.894757e6), "psi": ("stress", 6894.757),
    # mass, base kilogram
    "kg": ("mass", 1.0), "g": ("mass", 0.001), "lb": ("mass", 0.45359237),
}

_SUPERSCRIPT = str.maketrans("²³", "22")


def normalise_unit(unit: str | None) -> str | None:
    """Fold the spellings a tender actually uses. None and '' both mean 'no unit stated'."""
    if not unit:
        return None
    cleaned = unit.strip().lower().translate(_SUPERSCRIPT)
    cleaned = cleaned.replace("sq.mm", "mm2").replace(" ", "").replace("^", "")
    cleaned = cleaned.rstrip(".")
    # 'N/mm²' and 'N/sqmm' and 'newton per sq mm' all land on 'n/mm2'.
    cleaned = cleaned.replace("newtonper", "n/").replace("persq", "/").replace("sq", "")
    return cleaned or None


def convert(value: float, from_unit: str | None, to_unit: str | None) -> float | None:
    """Convert between units of the same dimension. None when it cannot be done honestly.

    A None return is not an error — it becomes UNKNOWN at the comparator, which is always
    preferable to a converted-by-guesswork number deciding whether a bid is possible.
    """
    src, dst = normalise_unit(from_unit), normalise_unit(to_unit)
    if src == dst:
        return value
    if src is None or dst is None:
        # One side stated a unit and the other did not. Handled by the caller, which knows
        # whether the key has a single canonical unit worth assuming.
        return None
    a, b = _UNIT_TO_BASE.get(src), _UNIT_TO_BASE.get(dst)
    if a is None or b is None or a[0] != b[0]:
        return None
    return value * a[1] / b[1]


# ── "or equivalent" ──────────────────────────────────────────────────────────────────

# Derived in Python from the requirement's own text, never reported by a model. Letting the
# model set the field that softens its own verdict is exactly the `is_financial` defect in
# docs/known-pitfalls.md: the gate becomes unreachable and the only protection is prompt
# obedience.
_EQUIVALENCE = re.compile(
    r"\b(or\s+equivalent|or\s+similar|or\s+equal|or\s+better|equivalent\s+to|"
    r"or\s+approved\s+equal|equivalent\s+standard)\b",
    re.I,
)


def allows_equivalent(raw_text: str) -> bool:
    """Did the tender itself invite an equivalent? Only ever softens an ENUM (see spec_match)."""
    return bool(_EQUIVALENCE.search(raw_text or ""))


# ── enum values ──────────────────────────────────────────────────────────────────────

# Only the folds that change an answer. A spelling variant that silently fails to match reads
# to the user as "the product thinks we cannot make our own product".
_VALUE_SYNONYMS: dict[str, str] = {
    "galvanized": "galvanised", "zinccoated": "galvanised", "zinccoating": "galvanised",
    "gi": "galvanised", "drawngalvanised": "galvanised",
    "ungalvanized": "ungalvanised", "black": "ungalvanised", "bright": "ungalvanised",
    "selfcolour": "ungalvanised", "selfcolor": "ungalvanised",
    "independentwireropecore": "iwrc", "steelcore": "iwrc", "wsc": "iwrc",
    "fibrecore": "fc", "fibercore": "fc", "naturalfibrecore": "fc",
    "righthandordinarylay": "rhol", "righthandlanglay": "rhll",
    "lefthandordinarylay": "lhol", "lefthandlanglay": "lhll",
    "ordinarylay": "rhol", "regularlay": "rhol",
}

_PUNCT = re.compile(r"[\s:\-_,.()\[\]/]+")


def normalise_value(value: str) -> str:
    """Fold an enum value to a comparable token.

    '6 × 36', '6X36' and '6x36' are one construction. 'IS:2266', 'IS 2266' and 'IS-2266' are one
    standard. Getting this wrong does not produce an error — it produces a DEVIATION on a
    parameter that actually matched, which is a lost bid dressed up as diligence.
    """
    folded = value.strip().lower().translate(_SUPERSCRIPT).replace("×", "x")
    folded = _PUNCT.sub("", folded)
    return _VALUE_SYNONYMS.get(folded, folded)


# ── display ──────────────────────────────────────────────────────────────────────────

def _trim(number: float) -> str:
    """20.0 -> '20'; 6.35 -> '6.35'. A trailing '.0' on a diameter looks like a bug."""
    return f"{number:g}"


def describe_range(low: float | None, high: float | None, unit: str | None) -> str:
    """'20 mm' · '6–60 mm' · '≥ 200 kN' · '≤ 60 mm'. Rendered here so the engine, the API and
    the screen cannot disagree about what an interval says (known-pitfalls: four counters
    describing one object)."""
    suffix = f" {unit}" if unit else ""
    if low is not None and high is not None:
        if math.isclose(low, high):
            return f"{_trim(low)}{suffix}"
        return f"{_trim(low)}–{_trim(high)}{suffix}"
    if low is not None:
        return f"≥ {_trim(low)}{suffix}"
    if high is not None:
        return f"≤ {_trim(high)}{suffix}"
    return "unspecified"
