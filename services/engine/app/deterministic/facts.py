"""Deciding a gate from facts the bidder actually has on file.

`analysis.decide()` used to compare an `actual_value_cr` the MODEL supplied against a
`required_value_cr` the MODEL supplied, and that branch skipped the confidence and evidence
checks the other branch applied — so a model at confidence 0.01, with no evidence at all,
produced a hard PASS. `exemption_applies` was a bare model boolean that turned NO-BID into
BID with no clause resolved, and `evidence_ids` were checked for presence and never matched
against a real row.

Here the model may only describe the REQUIREMENT. The bidder's side comes from
`db.get_profile_context` and the comparison is arithmetic — including the three comparators
in `eligibility.py` that had no production caller at all (`is_valid_on`, `completed_within`)
or none that reached them (`average_annual_turnover`).

THE ONE RULE EVERYTHING ELSE FOLLOWS FROM: a fact that is missing is UNKNOWN, never a
failure. Every branch below that cannot *prove* a shortfall returns NEEDS_REVIEW and names
what is missing. The reason is commercial rather than philosophical — a false "you do not
qualify" costs the customer a bid they would have won, and nobody audits the bids they were
told to skip, so the error is invisible. `spec_match.py` is built on the same asymmetry.

Two absences are worth calling out because the obvious reading of them is wrong:

  - `vendor_profiles.dpiit_registered` is `boolean not null default false`. `False` is
    indistinguishable from "nobody has ever been shown a form for this", so a registration
    check can never FAIL — only pass or ask.
  - a certification that is not on file is not a certification the bidder lacks. That is the
    same three-state rule the PQ sheet learned when it printed EXPIRED against four current
    ISO and API certificates.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date

from .eligibility import (
    average_annual_turnover,
    compare_numeric,
    completed_within,
    is_valid_on,
)
from .types import FUZZY_REVIEW_THRESHOLD, CheckType, Verdict

#: Registration keys a tender can demand, mapped to the profile field that answers them.
#: `make_in_india` is deliberately absent: no profile field records it, so a tender granting
#: an MII exemption can never be resolved and says so rather than guessing.
_REGISTRATION_FIELD = {
    "udyam": "udyam_registration",
    "mse": "udyam_registration",
    "msme": "udyam_registration",
    "gst": "gst",
    "pan": "pan",
    "cin": "cin",
    "dpiit": "dpiit_registered",
    "startup": "dpiit_registered",
}

#: Which registration each exemption class is proved by. Same table, read the other way.
_EXEMPTION_PROOF = {
    "mse": "udyam_registration",
    "msme": "udyam_registration",
    "udyam": "udyam_registration",
    "dpiit": "dpiit_registered",
    "startup": "dpiit_registered",
}


@dataclass(frozen=True)
class ExperienceRecord:
    id: str
    value_cr: float | None
    completion_date: date | None


@dataclass(frozen=True)
class CertRecord:
    id: str
    name: str
    valid_to: date | None


@dataclass(frozen=True)
class ProfileFacts:
    """What the bidder has on file, typed. Everything optional, because everything can be
    absent and absence is a first-class answer here."""

    fy_turnover_cr: Mapping[str, float] = field(default_factory=dict)
    net_worth_cr: float | None = None
    working_capital_cr: float | None = None
    udyam_registration: str = ""
    dpiit_registered: bool = False
    gst: str = ""
    pan: str = ""
    cin: str = ""
    experience: tuple[ExperienceRecord, ...] = ()
    certifications: tuple[CertRecord, ...] = ()


@dataclass(frozen=True)
class Requirement:
    """What the TENDER asks for. Extracted by the model, which never sees the bidder."""

    check: CheckType = CheckType.NONE
    operator: str | None = None
    threshold_cr: float | None = None
    fy_count: int | None = None
    fy_labels: tuple[str, ...] = ()
    min_count: int | None = None
    years_window: int | None = None
    certification_name: str | None = None
    registration_key: str | None = None
    exemption_for: tuple[str, ...] = ()
    exemption_clause: str = ""
    raw_text: str = ""
    confidence: float = 0.0


@dataclass(frozen=True)
class CheckOutcome:
    """A decided gate, and enough of the arithmetic to audit it afterwards.

    The stored verdict used to carry the answer and none of the working, so nobody could
    reconstruct what was compared to what. Every field below is in the persisted row.
    """

    verdict: Verdict
    check: CheckType
    rationale: str
    operator: str | None = None
    required_display: str = ""
    actual_display: str = ""
    fy_window: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    missing_facts: tuple[str, ...] = ()
    gap_note: str = ""
    exemption_granted: bool = False
    exemption_clause: str = ""


def _cr(v: float) -> str:
    return f"₹{v:.2f} Cr"


def _review(check: CheckType, why: str, missing: Sequence[str] = ()) -> CheckOutcome:
    return CheckOutcome(
        verdict=Verdict.NEEDS_REVIEW, check=check, rationale=why,
        missing_facts=tuple(missing),
    )


def _numeric(
    req: Requirement, actual: float | None, label: str, field_name: str,
    window: tuple[str, ...] = (), evidence: tuple[str, ...] = (),
) -> CheckOutcome:
    """One shape for every money comparison — turnover, net worth, working capital."""
    if req.threshold_cr is None:
        return _review(req.check, "the tender states no threshold this check could compare")
    if actual is None:
        return _review(req.check, f"{label} is not on file", (field_name,))
    op = req.operator or ">="
    passed = compare_numeric(actual, req.threshold_cr, op)
    shown = _cr(actual) + (f" (avg {'|'.join(window)})" if window else "")
    return CheckOutcome(
        verdict=Verdict.PASS if passed else Verdict.FAIL,
        check=req.check, operator=op,
        required_display=_cr(req.threshold_cr), actual_display=shown, fy_window=window,
        evidence_ids=evidence,
        rationale=f"{label} {shown} {op} {_cr(req.threshold_cr)} required",
        gap_note=(
            "" if passed
            else f"{label} {shown} vs {_cr(req.threshold_cr)} required — "
                 f"gap {_cr(abs(req.threshold_cr - actual))}"
        ),
    )


def _turnover(req: Requirement, facts: ProfileFacts, window: tuple[str, ...]) -> CheckOutcome:
    if not window:
        return _review(req.check,
                       "the tender does not say which financial years to average")
    avg = average_annual_turnover(facts.fy_turnover_cr, window)
    if avg is None:
        missing = [fy for fy in window if fy not in facts.fy_turnover_cr]
        return _review(req.check,
                       f"turnover is not on file for {', '.join(missing)}",
                       [f"profile_financials:{fy}" for fy in missing])
    return _numeric(req, avg, "average annual turnover", "profile_financials", window)


def _experience(req: Requirement, facts: ProfileFacts, bid_date: date | None) -> CheckOutcome:
    if req.min_count is None:
        return _review(req.check, "the tender states no number of works to count")
    if req.years_window and bid_date is None:
        return _review(req.check,
                       "the tender counts works within a window and this tender has no "
                       "submission date on file", ("tenders.deadline",))

    incomplete = [r.id for r in facts.experience
                  if r.value_cr is None or r.completion_date is None]
    qualifying = [
        r for r in facts.experience
        if r.value_cr is not None and r.completion_date is not None
        and (req.threshold_cr is None or r.value_cr >= req.threshold_cr)
        and (not req.years_window or bid_date is None
             or completed_within(r.completion_date, bid_date, req.years_window))
    ]
    if len(qualifying) >= req.min_count:
        return CheckOutcome(
            verdict=Verdict.PASS, check=req.check,
            required_display=f"{req.min_count} work(s)",
            actual_display=f"{len(qualifying)} qualifying",
            evidence_ids=tuple(r.id for r in qualifying[: req.min_count]),
            rationale=f"{len(qualifying)} recorded work(s) meet the stated test",
        )
    if incomplete:
        # The count is UNPROVEN, not short: a bidder with ten qualifying projects and one
        # undated row must never read as a failure.
        return _review(req.check,
                       f"{len(incomplete)} experience record(s) are missing a value or a "
                       "completion date, so the count cannot be proved",
                       tuple(f"experience_records:{i}" for i in incomplete))
    return CheckOutcome(
        verdict=Verdict.FAIL, check=req.check,
        required_display=f"{req.min_count} work(s)",
        actual_display=f"{len(qualifying)} qualifying",
        evidence_ids=tuple(r.id for r in qualifying),
        rationale=f"{len(qualifying)} of {req.min_count} required work(s) on file",
        gap_note=f"{req.min_count - len(qualifying)} more qualifying work(s) needed",
    )


def _certification(req: Requirement, facts: ProfileFacts, bid_date: date | None) -> CheckOutcome:
    if not req.certification_name:
        return _review(req.check, "the tender does not name the certification")
    wanted = req.certification_name.lower()
    matches = [c for c in facts.certifications
               if wanted in c.name.lower() or c.name.lower() in wanted]
    if not matches:
        # Not on file is not "does not hold it".
        return _review(req.check,
                       f"no certification matching '{req.certification_name}' is on file",
                       ("certifications",))
    if bid_date is None:
        return _review(req.check,
                       "this tender has no submission date on file, so validity cannot be "
                       "checked", ("tenders.deadline",))
    dated = [c for c in matches if c.valid_to is not None]
    if not dated:
        return _review(req.check,
                       f"'{matches[0].name}' is on file with no expiry date recorded",
                       (f"certifications:{matches[0].id}",))
    valid = [c for c in dated if is_valid_on(c.valid_to, bid_date)]
    if valid:
        return CheckOutcome(
            verdict=Verdict.PASS, check=req.check,
            required_display=req.certification_name,
            actual_display=f"{valid[0].name} valid to {valid[0].valid_to.isoformat()}",
            evidence_ids=(valid[0].id,),
            rationale="a matching certification is valid on the submission date",
        )
    newest = max(dated, key=lambda c: c.valid_to)
    return CheckOutcome(
        verdict=Verdict.FAIL, check=req.check,
        required_display=req.certification_name,
        actual_display=f"{newest.name} expired {newest.valid_to.isoformat()}",
        evidence_ids=(newest.id,),
        rationale="the matching certification had expired by the submission date",
        gap_note=f"renew {newest.name} — expired {newest.valid_to.isoformat()}",
    )


def _registration(req: Requirement, facts: ProfileFacts) -> CheckOutcome:
    field_name = _REGISTRATION_FIELD.get(str(req.registration_key or "").lower())
    if not field_name:
        return _review(req.check,
                       f"'{req.registration_key}' is not a registration this profile records")
    value = getattr(facts, field_name)
    if value:
        return CheckOutcome(
            verdict=Verdict.PASS, check=req.check,
            required_display=str(req.registration_key),
            actual_display="on file",
            rationale=f"{field_name} is recorded on the profile",
        )
    # NEVER a FAIL. `dpiit_registered` defaults to false and the text fields default to
    # empty, so an absent value cannot be told apart from a question nobody has been asked.
    return _review(req.check,
                   f"{field_name} is not recorded on the profile",
                   (f"vendor_profiles.{field_name}",))


def decide_requirement(
    req: Requirement, facts: ProfileFacts, bid_date: date | None = None,
    fy_window: Sequence[str] = (),
) -> CheckOutcome:
    """Decide one gate. Never raises, and never FAILs on an absent fact."""
    if req.check is CheckType.NONE:
        return _review(req.check, req.raw_text and "this requirement states no checkable "
                       "condition" or "nothing to check")
    # A requirement the model was unsure it had read correctly is not a basis for a verdict.
    # This guard applied to the fuzzy branch only; the numeric branch skipped it entirely,
    # which is how confidence 0.01 produced a hard PASS.
    if req.confidence < FUZZY_REVIEW_THRESHOLD:
        return _review(req.check,
                       "the requirement was read with low confidence — confirm the clause")

    if req.check is CheckType.TURNOVER_AVG:
        return _turnover(req, facts, tuple(fy_window) or req.fy_labels)
    if req.check is CheckType.NET_WORTH:
        return _numeric(req, facts.net_worth_cr, "net worth", "vendor_profiles.net_worth_cr")
    if req.check is CheckType.WORKING_CAPITAL:
        return _numeric(req, facts.working_capital_cr, "working capital",
                        "vendor_profiles.working_capital_cr")
    if req.check is CheckType.EXPERIENCE_COUNT:
        return _experience(req, facts, bid_date)
    if req.check is CheckType.CERTIFICATION_VALID:
        return _certification(req, facts, bid_date)
    return _registration(req, facts)


def exemption_granted(req: Requirement, facts: ProfileFacts, verdict: Verdict) -> bool:
    """Does the tender waive this failure FOR THIS BIDDER?

    Four conditions, all required. The old version was a single model boolean, so one `true`
    on a mandatory criterion flipped NO-BID to BID with nothing resolved anywhere.
    """
    if verdict is not Verdict.FAIL:
        return False
    if not req.exemption_clause or not req.exemption_for:
        return False
    for cls in req.exemption_for:
        proof = _EXEMPTION_PROOF.get(str(cls).lower())
        if proof and getattr(facts, proof):
            return True
    return False


def profile_facts(profile_context: Mapping) -> ProfileFacts:
    """Adapt `db.get_profile_context`'s dict into typed facts. Tolerates `{}` throughout —
    five existing tests call the analyzer with an empty profile, and an empty profile is
    exactly the state that must produce "unknown" rather than "fails"."""
    legal = profile_context.get("legal_identity") or {}
    return ProfileFacts(
        fy_turnover_cr={
            str(f.get("fy_label")): float(f["turnover_cr"])
            for f in (profile_context.get("financials") or [])
            if f.get("fy_label") and f.get("turnover_cr") is not None
        },
        net_worth_cr=_num(legal.get("net_worth_cr")),
        working_capital_cr=_num(legal.get("working_capital_cr")),
        udyam_registration=str(legal.get("udyam_registration") or ""),
        dpiit_registered=bool(legal.get("dpiit_registered")),
        gst=str(legal.get("gst") or ""),
        pan=str(legal.get("pan") or ""),
        cin=str(legal.get("cin") or ""),
        experience=tuple(
            ExperienceRecord(str(r.get("id") or ""), _num(r.get("value_cr")),
                             _iso(r.get("completion_date")))
            for r in (profile_context.get("experience_records") or [])
        ),
        certifications=tuple(
            CertRecord(str(c.get("id") or ""), str(c.get("name") or ""),
                       _iso(c.get("valid_to")))
            for c in (profile_context.get("certifications") or [])
        ),
    )


def _num(v) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _iso(v) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None
