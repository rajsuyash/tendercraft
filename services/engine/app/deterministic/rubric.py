"""Technical-competence rubric — scores the PROPOSAL, deterministically (Module D).

Distinct from app/estimator.py on purpose:
  - the estimator PREDICTS what an external evaluator will do, so it is correctly
    suppressed until 30 comparable historical outcomes exist (D-AC4)
  - this MEASURES how complete and defensible the document we are holding actually is.
    Every input is a row we own, so it needs no history and must never be suppressed.

Merging them fails either way round: the measurement inherits a suppression it doesn't
need, or the prediction escapes one it does.

Weights are taken from real Indian government technical-evaluation tables, not invented:
  - MeitY Model RFP 2018 §2.6.2.2 (QCBS Category Two): functionality 20%, technology 20%,
    team 20%, then 7% each for training, certifications, methodology, industry experience
  - CAG "One IAAD One System" 2019 §7: functionality 22, technology 25, methodology 15,
    team 10, training 5, exit/O&M 8
Both enforce a per-section minimum AND an aggregate cut-off below which a bid is
technically rejected without the commercial cover ever being opened — modelled here.

No model call anywhere in this module: the number must be reproducible from the DB.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

# CAG OIOS §7.7.4 / MeitY §2.6.2.2 — a bid must clear BOTH or it is technically rejected.
MIN_DIMENSION_FRACTION = 0.45
MIN_AGGREGATE_FRACTION = 0.65

# Anti-padding: past 2.5x the target, more words stop helping. "Never pad with unsupported
# prose" becomes a scoring property here, not just a prompt instruction.
_PAD_MULTIPLE = 2.5
_PAD_SCORE = 0.9


@dataclass(frozen=True)
class SectionFeatures:
    """What the scorer observes about one section. All of it is read off persisted rows."""

    key: str
    present: bool
    status: str  # 'drafted' | 'placeholder' | 'unverified'
    word_count: int
    target_words: int
    claim_verifiability: float = 1.0  # B-AC3, reused from app.deterministic.drafting
    subsection_count: int = 0
    approved: bool = False


@dataclass(frozen=True)
class Dimension:
    key: str
    label: str
    weight: int
    sections: tuple[str, ...]
    # feature name -> relative weight within the dimension
    features: dict[str, float]


# Weights sum to 100. Mapping from MeitY/CAG heads onto the sections we actually produce.
DIMENSIONS: tuple[Dimension, ...] = (
    Dimension("scope_understanding", "Understanding of scope", 10, ("understanding",),
              {"presence": 0.3, "depth": 0.4, "citation_integrity": 0.1, "approved": 0.2}),
    Dimension("solution_architecture", "Proposed solution & technology", 20, ("solution",),
              {"presence": 0.3, "depth": 0.4, "citation_integrity": 0.1, "approved": 0.2}),
    Dimension("methodology", "Approach, methodology & work plan", 15,
              ("approach_methodology", "workplan"),
              {"presence": 0.25, "depth": 0.35, "subsections": 0.15,
               "citation_integrity": 0.05, "approved": 0.2}),
    Dimension("team", "Team composition & key personnel", 15,
              ("team_composition", "cvs", "deployment"),
              {"presence": 0.2, "cv_backing": 0.8}),
    Dimension("experience", "Relevant experience & past performance", 15,
              ("project_citations",),
              {"presence": 0.2, "matching_records": 0.8}),
    Dimension("qa", "Quality assurance & testing", 8, ("qa",),
              {"presence": 0.3, "depth": 0.4, "cert_backing": 0.1, "approved": 0.2}),
    Dimension("training", "Training & capacity building", 6, ("training",),
              {"presence": 0.35, "depth": 0.45, "approved": 0.2}),
    Dimension("support_sla", "Support, SLA & O&M", 7, ("support_sla",),
              {"presence": 0.35, "depth": 0.45, "approved": 0.2}),
    Dimension("risk", "Risk management & mitigation", 4, ("risk",),
              {"presence": 0.35, "depth": 0.45, "approved": 0.2}),
)

# Which action a shortfall in a given feature implies. Stable strings — the UI switches on
# these and maps each to a deep link, so every suggestion is actionable by construction.
_ACTION = {
    "presence": "GENERATE_SECTION",
    "depth": "EXPAND_SECTION",
    "subsections": "ADD_SUBSECTIONS",
    "citation_integrity": "RESOLVE_UNCITED_CLAIM",
    "approved": "APPROVE_SECTION",
    "cv_backing": "ATTACH_CV",
    "matching_records": "ADD_EXPERIENCE_RECORD",
    "cert_backing": "RENEW_CERTIFICATION",
}

_ADVICE = {
    "GENERATE_SECTION": "Section is missing or unresolved — an absent section scores zero.",
    "EXPAND_SECTION": "Section is materially shorter than a government technical bid expects.",
    "ADD_SUBSECTIONS": "Add distinct sub-headings; evaluators score against a marks table "
                       "and need to find each element.",
    "RESOLVE_UNCITED_CLAIM": "Claims here have no resolving citation — attach evidence or "
                             "attest them.",
    "APPROVE_SECTION": "AI-drafted narrative is not yet human-approved, so it cannot be "
                       "exported.",
    "ATTACH_CV": "Upload CVs for key personnel — team profile carries up to 20% of the "
                 "technical marks.",
    "ADD_EXPERIENCE_RECORD": "Add completed projects matching this tender's scope and value "
                             "threshold, with completion certificates.",
    "RENEW_CERTIFICATION": "A required certification is missing or expired on the bid date.",
}


@dataclass(frozen=True)
class DimensionScore:
    key: str
    label: str
    weight: int
    score: float  # 0..1
    earned: float  # weight * score
    max_gain: float
    features: dict[str, float]
    meets_minimum: bool


@dataclass(frozen=True)
class Suggestion:
    dimension: str
    dimension_label: str
    action_code: str
    expected_delta: float  # marks actually recoverable — computed, never a fixed string
    advice: str
    observed: dict


@dataclass(frozen=True)
class RubricResult:
    total: float
    dimensions: tuple[DimensionScore, ...] = field(default_factory=tuple)
    suggestions: tuple[Suggestion, ...] = field(default_factory=tuple)
    meets_aggregate_minimum: bool = False
    failing_dimensions: tuple[str, ...] = field(default_factory=tuple)
    technically_qualified: bool = False


def _depth(words: int, target: int) -> float:
    if target <= 0:
        return 1.0
    if words >= target * _PAD_MULTIPLE:
        return _PAD_SCORE
    return min(1.0, words / target)


def _feature_values(
    dim: Dimension,
    secs: list[SectionFeatures],
    cv_count: int,
    matching_experience: int,
    required_experience: int,
    valid_cert_fraction: float,
) -> dict[str, float]:
    """Every value is 0..1 and observable — no judgement, no model."""
    n = len(secs) or 1
    # Dict dispatch rather than an elif chain: every key in DIMENSIONS.features must resolve,
    # so a typo raises here instead of silently scoring zero.
    computed = {
        "presence": lambda: sum(
            1.0 for s in secs if s.present and s.status != "placeholder"
        ) / n,
        "depth": lambda: sum(_depth(s.word_count, s.target_words) for s in secs) / n,
        "subsections": lambda: sum(min(1.0, s.subsection_count / 3) for s in secs) / n,
        "citation_integrity": lambda: sum(s.claim_verifiability for s in secs) / n,
        "approved": lambda: sum(1.0 for s in secs if s.approved) / n,
        "cv_backing": lambda: min(1.0, cv_count / 3),
        "matching_records": lambda: (
            min(1.0, matching_experience / required_experience)
            if required_experience > 0 else 1.0
        ),
        "cert_backing": lambda: valid_cert_fraction,
    }
    return {name: computed[name]() for name in dim.features}


def score_proposal(
    sections: Sequence[SectionFeatures],
    *,
    cv_count: int = 0,
    matching_experience: int = 0,
    required_experience: int = 3,
    valid_cert_fraction: float = 0.0,
) -> RubricResult:
    """Score the document. Pure: same rows in, same number out, every time."""
    by_key = {s.key: s for s in sections}
    dim_scores: list[DimensionScore] = []
    suggestions: list[Suggestion] = []

    for dim in DIMENSIONS:
        # A section that was never generated earns nothing on ANY feature — note
        # claim_verifiability=0.0, not the 1.0 default ("no claims, so all verified"),
        # which is right for real content but would pay marks for absent content.
        secs = [
            by_key.get(k)
            or SectionFeatures(k, present=False, status="missing", word_count=0,
                               target_words=1, claim_verifiability=0.0, subsection_count=0)
            for k in dim.sections
        ]
        vals = _feature_values(
            dim, secs, cv_count, matching_experience, required_experience, valid_cert_fraction
        )
        score = sum(vals[n] * w for n, w in dim.features.items())
        earned = dim.weight * score
        dim_scores.append(
            DimensionScore(
                key=dim.key, label=dim.label, weight=dim.weight, score=round(score, 4),
                earned=round(earned, 2), max_gain=round(dim.weight - earned, 2),
                features={k: round(v, 4) for k, v in vals.items()},
                meets_minimum=score >= MIN_DIMENSION_FRACTION,
            )
        )

        for name, fw in dim.features.items():
            gap = 1.0 - vals[name]
            if gap <= 0.01:
                continue
            delta = round(dim.weight * fw * gap, 2)
            if delta < 0.1:  # not worth a bidder's attention
                continue
            code = _ACTION[name]
            suggestions.append(
                Suggestion(
                    dimension=dim.key, dimension_label=dim.label, action_code=code,
                    expected_delta=delta, advice=_ADVICE[code],
                    observed={
                        "feature": name,
                        "value": round(vals[name], 3),
                        "sections": [s.key for s in secs],
                        "words": sum(s.word_count for s in secs),
                        "target_words": sum(s.target_words for s in secs),
                    },
                )
            )

    total = round(sum(d.earned for d in dim_scores), 1)
    failing = tuple(d.key for d in dim_scores if not d.meets_minimum)
    meets_aggregate = total >= MIN_AGGREGATE_FRACTION * 100

    return RubricResult(
        total=total,
        dimensions=tuple(dim_scores),
        suggestions=tuple(sorted(suggestions, key=lambda s: -s.expected_delta)),
        meets_aggregate_minimum=meets_aggregate,
        failing_dimensions=failing,
        # Both gates, exactly as a real evaluation committee applies them.
        technically_qualified=meets_aggregate and not failing,
    )
