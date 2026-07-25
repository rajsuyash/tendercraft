"""Wires persisted rows into the deterministic rubric (app/deterministic/rubric.py).

Mapping only — every judgement stays in the pure module, so the score remains reproducible
from the database.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pipeline.retrieval import _tokens

from .deterministic.rubric import RubricResult, SectionFeatures, score_proposal
from .sections import SPEC_BY_KEY

# Certifications that carry marks in Indian government IT technical evaluations
# (MeitY §2.6.2.2 "Certifications and Credentials", CAG OIOS).
_SCORED_CERTS = ("iso 9001", "iso 27001", "cmmi")


def _claim_verifiability(section: dict) -> float:
    """B-AC3 over one section's persisted sentences: claims whose citation resolved."""
    sents = section.get("sentences") or []
    claims = [s for s in sents if s.get("requires_citation")]
    if not claims:
        return 1.0
    flagged = {
        f.get("text") for f in (section.get("flags") or []) if f.get("reason") == "unverified"
    }
    return sum(1 for s in claims if s.get("text") not in flagged) / len(claims)


def _matching_experience(experience: list[dict], criteria: list[dict]) -> int:
    """Experience records whose scope overlaps what this tender actually asks for.

    A record for a hardware supply does not evidence a software-implementation criterion,
    and evaluators score exactly that distinction (MeitY's relevant-strengths heads).
    """
    crit_tokens: set[str] = set()
    for c in criteria:
        crit_tokens |= _tokens(c.get("verbatim_text") or "")
    if not crit_tokens:
        return len(experience)
    return sum(
        1 for e in experience
        if (_tokens(" ".join(e.get("scope_tags") or []) + " " + (e.get("project_name") or ""))
            & crit_tokens)
    )


def _valid_cert_fraction(certs: list[dict], today: str) -> float:
    have = 0
    for name in _SCORED_CERTS:
        for c in certs:
            cname = (c.get("name") or "").lower()
            valid = not c.get("valid_to") or str(c["valid_to"]) >= today
            if name in cname and valid:
                have += 1
                break
    return have / len(_SCORED_CERTS)


def compute(sections: list[dict], criteria: list[dict], profile: dict,
            library: list[dict]) -> RubricResult:
    today = datetime.now(UTC).date().isoformat()
    feats = [
        SectionFeatures(
            key=s.get("key", ""),
            present=bool((s.get("body_md") or "").strip()),
            status=s.get("status", "missing"),
            word_count=int(s.get("word_count") or 0),
            target_words=SPEC_BY_KEY[s["key"]].target_words if s.get("key") in SPEC_BY_KEY else 0,
            claim_verifiability=_claim_verifiability(s),
            subsection_count=(s.get("body_md") or "").count("### "),
            approved=bool(s.get("approved_at")),
        )
        for s in sections
    ]
    return score_proposal(
        feats,
        cv_count=sum(1 for d in library if (d.get("doc_type") or "") == "cv"),
        matching_experience=_matching_experience(
            profile.get("experience_records") or [], criteria
        ),
        required_experience=3,
        valid_cert_fraction=_valid_cert_fraction(profile.get("certifications") or [], today),
    )


def payload(r: RubricResult) -> dict:
    return {
        "total": r.total,
        "technically_qualified": r.technically_qualified,
        "meets_aggregate_minimum": r.meets_aggregate_minimum,
        "failing_dimensions": list(r.failing_dimensions),
        "dimensions": [
            {"key": d.key, "label": d.label, "weight": d.weight, "score": d.score,
             "earned": d.earned, "max_gain": d.max_gain, "features": d.features,
             "meets_minimum": d.meets_minimum}
            for d in r.dimensions
        ],
        "suggestions": [
            {"dimension": s.dimension, "dimension_label": s.dimension_label,
             "action_code": s.action_code, "expected_delta": s.expected_delta,
             "advice": s.advice, "observed": s.observed}
            for s in r.suggestions
        ],
    }
