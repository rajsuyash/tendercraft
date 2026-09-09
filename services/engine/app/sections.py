"""Long-form proposal sections — the spec, and the deterministic assemblers.

Section identity follows the MeitY Model RFP Appendix-I Form packet, because that is what
Indian government evaluators actually mark against. Form numbering varies between issuing
authorities (MeitY/MoSPI "Form 7" == CAG "Format 9" == Chhattisgarh "Form 11"), so the key
is semantic and the form label is display-only.

Two kinds of section:
  - ASSEMBLED: built here, in Python, from structured rows. No model call, so no citation
    problem — and this is where B-FR3 transclusion actually happens: a figure comes from
    experience_records.value_cr with a source_ref, never from a model.
  - NARRATIVE: the bidder's proposed approach, drafted by pipeline.section_drafter.

Assemblers are pure functions over already-fetched rows (no I/O) so they unit-test directly.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .deterministic.drafting import DraftSentence
from .deterministic.eligibility import average_annual_turnover
from .deterministic.types import SectionKind, SentenceClass


@dataclass(frozen=True)
class SectionSpec:
    key: str
    heading: str  # includes the MeitY form label where one exists
    order: int
    kind: SectionKind
    target_words: int  # 0 for assembled sections — depth is not a word-count question
    evidence_query: str = ""  # what to retrieve for this section (narrative only)
    # Can this section only be written from bidder evidence? Methodology, QA, risk etc. are
    # written from the tender requirements plus professional practice, so a thin library is
    # NOT grounds to skip them — an empty section scores zero. Whether a section may bail is
    # a deterministic decision; left to the model it self-vetoes on noisy retrieval.
    needs_bidder_evidence: bool = False


# Ordered as a bid is actually submitted: covering letter, PQ compliance, then the
# technical bid, then evidence. Target word counts are the midpoints of the observed
# ranges in real ₹1-10 Cr Indian government IT bids (80-155 generated pages total).
SECTION_SPECS: tuple[SectionSpec, ...] = (
    SectionSpec("letter_of_proposal", "Form 5: Letter of Proposal", 10,
                SectionKind.NARRATIVE, 400,
                "company profile capability undertaking authorised signatory",
                needs_bidder_evidence=True),
    SectionSpec("compliance_pq", "Form 1: Compliance Sheet for Pre-Qualification", 20,
                SectionKind.COMPLIANCE, 0),
    SectionSpec("understanding", "Form 7(b): Understanding of the Project", 30,
                SectionKind.NARRATIVE, 1500,
                "scope of work objectives deliverables requirements"),
    SectionSpec("solution", "Form 7(a): Proposed Solution and Technical Architecture", 40,
                SectionKind.NARRATIVE, 3000,
                "solution architecture technology platform infrastructure security integration"),
    SectionSpec("approach_methodology", "Form 7(c): Technical Approach and Methodology", 50,
                SectionKind.NARRATIVE, 2500,
                "implementation methodology phases delivery governance"),
    SectionSpec("workplan", "Form 8: Proposed Work Plan", 60,
                SectionKind.NARRATIVE, 800,
                "timeline milestones deliverables work breakdown"),
    SectionSpec("team_composition", "Form 9: Team Composition", 70,
                SectionKind.COMPLIANCE, 0),
    SectionSpec("cvs", "Form 10: Curriculum Vitae of Key Personnel", 80,
                SectionKind.COMPLIANCE, 0),
    SectionSpec("deployment", "Form 11: Deployment of Personnel", 90,
                SectionKind.COMPLIANCE, 0),
    SectionSpec("project_citations", "Form 6: Project Citation Format", 100,
                SectionKind.COMPLIANCE, 0),
    SectionSpec("qa", "Quality Assurance and Testing Approach", 110,
                SectionKind.NARRATIVE, 1200,
                "quality assurance testing UAT defect management standards"),
    SectionSpec("training", "Training and Capacity Building", 120,
                SectionKind.NARRATIVE, 1000,
                "training capacity building user manuals handholding"),
    SectionSpec("support_sla", "Support, SLA and Operations & Maintenance", 130,
                SectionKind.NARRATIVE, 1200,
                "support helpdesk SLA maintenance warranty operations"),
    SectionSpec("risk", "Risk Management and Mitigation", 140,
                SectionKind.NARRATIVE, 1000,
                "risk mitigation contingency dependencies"),
    SectionSpec("deviations", "Form 12: Deviations", 150,
                SectionKind.COMPLIANCE, 0),
    SectionSpec("compliance_matrix", "Technical Compliance Matrix", 160,
                SectionKind.COMPLIANCE, 0),
    SectionSpec("annexures", "Annexures and Evidence Index", 170,
                SectionKind.COMPLIANCE, 0),
)

SPEC_BY_KEY: dict[str, SectionSpec] = {s.key: s for s in SECTION_SPECS}
NARRATIVE_KEYS: tuple[str, ...] = tuple(
    s.key for s in SECTION_SPECS if s.kind is SectionKind.NARRATIVE
)
ASSEMBLED_KEYS: tuple[str, ...] = tuple(
    s.key for s in SECTION_SPECS if s.kind is SectionKind.COMPLIANCE
)

_EMPTY = "_No data available. Add records in your Vendor Profile or Content Library._"


def _val(text: str, source_ref: str) -> DraftSentence:
    """A transcluded value: it came from a structured row, so it is exempt from B-AC4.

    This is the only place is_transcluded may be set. A model can never reach it — the
    class is not in the drafter's schema enum.
    """
    return DraftSentence(
        text=text, citations=(), cls=SentenceClass.ASSEMBLED,
        source_ref=source_ref, is_transcluded=True,
    )


def _table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return _EMPTY
    out = ["| " + " | ".join(headers) + " |",
           "| " + " | ".join("---" for _ in headers) + " |"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


def _fmt_cr(v) -> str:
    return f"₹{float(v):.2f} Cr" if v not in (None, "") else "—"


@dataclass(frozen=True)
class AssembledSection:
    body_md: str
    sentences: tuple[DraftSentence, ...]


def assemble_project_citations(experience: list[dict]) -> AssembledSection:
    """Form 6 — up to 5 project citations. Values transclude from experience_records."""
    rows, sents = [], []
    for e in sorted(experience, key=lambda r: r.get("completion_date") or "", reverse=True)[:5]:
        value = _fmt_cr(e.get("value_cr"))
        rows.append([
            str(e.get("project_name") or "—"),
            str(e.get("client_type") or "—"),
            value,
            ", ".join(e.get("scope_tags") or []) or "—",
            str(e.get("completion_date") or "—"),
        ])
        sents.append(_val(value, f"experience_records:{e.get('id')}.value_cr"))
    return AssembledSection(
        _table(["Project", "Client type", "Value", "Scope", "Completed"], rows), tuple(sents)
    )


def assemble_compliance_pq(
    profile: dict, certifications: list[dict], today: str,
    required_fys: Sequence[str] | None = None,
) -> AssembledSection:
    """Form 1 — the pre-qualification compliance sheet. Every row names its evidence.

    `required_fys` is the FY window the TENDER asks about ("Minimum Average Annual Turnover
    (For 3 Years)"), not a property of the bidder. It is not optional in spirit: without it
    there is no correct average, only a plausible one.

    This used to average every stored FY and label the result a CA-certified turnover
    statement, emitting the token `profile_financials:avg.turnover_cr` — which identifies no
    window and no fact versions. Confirming FY26 then silently changed the number answering a
    FY23-FY25 requirement, on a hard non-overridable financial gate (B-FR3/B-AC4). Assembling
    the wrong figure is worse than assembling none, because the transclusion carries the
    authority of structured data.
    """
    legal = profile.get("legal_identity") or {}
    fins = profile.get("financials") or []
    fy_values = {
        str(f.get("fy_label")): float(f.get("turnover_cr") or 0)
        for f in fins
        if f.get("fy_label") is not None and f.get("turnover_cr") is not None
    }
    window = list(dict.fromkeys(required_fys)) if required_fys else []
    # Returns None when ANY required FY is absent — averaging what we happen to hold would
    # manufacture a figure for a window we cannot answer (eligibility.average_annual_turnover).
    avg = average_annual_turnover(fy_values, window) if window else None
    missing = [fy for fy in window if fy not in fy_values]

    rows, sents = [], []

    def add(requirement: str, position: str, evidence: str, ref: str | None = None):
        rows.append([requirement, position, evidence])
        if ref:
            sents.append(_val(position, ref))

    add("Legal entity (CIN)", str(legal.get("cin") or "—"), "Certificate of Incorporation",
        "vendor_profiles:cin" if legal.get("cin") else None)
    add("PAN", str(legal.get("pan") or "—"), "PAN card")
    add("GST registration", str(legal.get("gst") or "—"), "GST certificate")
    add("Udyam / MSME", str(legal.get("udyam_registration") or "—"), "Udyam certificate")
    if avg is not None:
        add("Average annual turnover", _fmt_cr(avg),
            f"CA-certified turnover statement ({', '.join(window)})",
            f"profile_financials:avg.turnover_cr[{'|'.join(window)}]")
    elif missing:
        # Name the gap rather than averaging around it: the user can act on "FY26 missing",
        # not on a number that quietly answered a different question.
        add("Average annual turnover", "—",
            f"Turnover not on file for {', '.join(missing)} — required for {', '.join(window)}")
    else:
        add("Average annual turnover", "—",
            "Required FY window not confirmed — "
            f"{len(fy_values)} FYs on file ({', '.join(sorted(fy_values)) or 'none'})")
    add("Net worth", _fmt_cr(legal.get("net_worth_cr")), "Statutory auditor certificate",
        "vendor_profiles:net_worth_cr" if legal.get("net_worth_cr") is not None else None)

    for c in certifications:
        valid = bool(c.get("valid_to")) and str(c["valid_to"]) >= today
        add(str(c.get("name") or "Certification"),
            "Valid" if valid else f"EXPIRED ({c.get('valid_to') or 'no expiry recorded'})",
            "Copy of certificate")

    return AssembledSection(
        _table(["Requirement", "Bidder's position", "Evidence"], rows), tuple(sents)
    )


def assemble_team(cv_docs: list[dict]) -> AssembledSection:
    """Form 9 — team composition, one row per CV in the content library."""
    rows = [[str(d.get("name") or "—"), "Key personnel", "Form 10 (CV attached)"] for d in cv_docs]
    return AssembledSection(
        _table(["Personnel / document", "Position assigned", "Reference"], rows), ()
    )


def assemble_cvs(cv_docs: list[dict]) -> AssembledSection:
    """Form 10 — CV index. The CVs themselves are attached, not regenerated."""
    if not cv_docs:
        return AssembledSection(
            "_No CVs in the content library. Upload key-personnel CVs — team profile is a "
            "scored dimension in every Indian government technical evaluation._", ()
        )
    body = "\n".join(f"{i}. **{d.get('name')}** — attached as Annexure CV-{i}"
                     for i, d in enumerate(cv_docs, 1))
    return AssembledSection(body, ())


def assemble_deployment(cv_docs: list[dict]) -> AssembledSection:
    """Form 11 — deployment of personnel."""
    rows = [[str(d.get("name") or "—"), "Full-time", "Project duration"] for d in cv_docs]
    return AssembledSection(
        _table(["Personnel", "Engagement", "Period"], rows), ()
    )


def assemble_deviations() -> AssembledSection:
    """Form 12 — deviations. A nil-deviation statement is the compliant default.

    Deliberately NOT model-generated: proposing a deviation is a commercial decision with
    contractual consequences, and a hallucinated one could invalidate the bid.
    """
    return AssembledSection(
        "The bidder confirms **no deviations** from the terms, conditions and specifications "
        "of the tender document.\n\n"
        "_Material or non-material deviations must be entered by the bid owner before "
        "submission; this section is never auto-generated._",
        (),
    )


def assemble_compliance_matrix(criteria: list[dict], responses: list[dict]) -> AssembledSection:
    """Clause-by-clause Comply / Not Comply table, cross-referenced to the response."""
    by_crit = {r.get("criterion_id"): r for r in responses}
    status_label = {
        "drafted": "Comply", "unverified": "Comply (source pending)",
        "placeholder": "Not addressed", "missing": "Not addressed",
    }
    rows = []
    for c in criteria:
        r = by_crit.get(c["id"], {})
        rows.append([
            (c.get("verbatim_text") or "")[:160],
            str(c.get("requirement_level") or "—"),
            status_label.get(r.get("draft_status"), "Not addressed"),
            str(c.get("source_anchor") or c.get("anchor_clause") or "—"),
        ])
    return AssembledSection(
        _table(["Requirement", "Level", "Compliance", "Tender reference"], rows), ()
    )


def assemble_annexures(docs: list[dict], today: str) -> AssembledSection:
    """Evidence index — what is attached, and whether it is still valid on the bid date."""
    rows = []
    for i, d in enumerate(docs, 1):
        valid_to = d.get("valid_to")
        validity = "No expiry" if not valid_to else (
            "Valid" if str(valid_to) >= today else f"EXPIRED {valid_to}"
        )
        rows.append([f"A-{i}", str(d.get("name") or "—"),
                     str(d.get("doc_type") or "—"), validity])
    return AssembledSection(
        _table(["Annexure", "Document", "Type", "Validity"], rows), ()
    )
