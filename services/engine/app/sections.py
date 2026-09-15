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

from .deterministic.drafting import DraftSentence, template_placeholders
from .deterministic.eligibility import average_annual_turnover
from .deterministic.requirement_kind import effective_kind
from .deterministic.types import RequirementKind, SectionKind, SentenceClass


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
    # Which SIGNALS the tender must carry for this section to be included
    # (`app/deterministic/outline.py`). Empty means universal — a covering letter and an
    # evidence index belong in every bid regardless of what is being bought.
    #
    # This is what turns SECTION_SPECS from *the outline* into *the catalogue*. Derivation
    # picks entries from here; it may never mint a key, because a fresh key would have no
    # drafting brief, no assembler, no rubric emphasis and no stable `answer_usages.target`.
    requires: frozenset[str] = frozenset()


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
                "solution architecture technology platform infrastructure security integration",
                requires=frozenset({"solution"})),
    SectionSpec("approach_methodology", "Form 7(c): Technical Approach and Methodology", 50,
                SectionKind.NARRATIVE, 2500,
                "implementation methodology phases delivery governance"),
    SectionSpec("workplan", "Form 8: Proposed Work Plan", 60,
                SectionKind.NARRATIVE, 800,
                "timeline milestones deliverables work breakdown",
                requires=frozenset({"workplan"})),
    SectionSpec("team_composition", "Form 9: Team Composition", 70,
                SectionKind.COMPLIANCE, 0, requires=frozenset({"personnel"})),
    SectionSpec("cvs", "Form 10: Curriculum Vitae of Key Personnel", 80,
                SectionKind.COMPLIANCE, 0, requires=frozenset({"personnel"})),
    SectionSpec("deployment", "Form 11: Deployment of Personnel", 90,
                SectionKind.COMPLIANCE, 0, requires=frozenset({"personnel"})),
    SectionSpec("project_citations", "Form 6: Project Citation Format", 100,
                SectionKind.COMPLIANCE, 0),
    SectionSpec("qa", "Quality Assurance and Testing Approach", 110,
                SectionKind.NARRATIVE, 1200,
                "quality assurance testing UAT defect management standards"),
    SectionSpec("training", "Training and Capacity Building", 120,
                SectionKind.NARRATIVE, 1000,
                "training capacity building user manuals handholding",
                requires=frozenset({"training"})),
    SectionSpec("support_sla", "Support, SLA and Operations & Maintenance", 130,
                SectionKind.NARRATIVE, 1200,
                "support helpdesk SLA maintenance warranty operations",
                requires=frozenset({"support"})),
    SectionSpec("risk", "Risk Management and Mitigation", 140,
                SectionKind.NARRATIVE, 1000,
                "risk mitigation contingency dependencies"),
    # Goods bids: one group per schedule line, a parameter table per group. Gated on the
    # schedule actually existing, so a services tender never renders an empty grid.
    SectionSpec("item_compliance", "Item-wise Technical Compliance", 145,
                SectionKind.COMPLIANCE, 0, requires=frozenset({"schedule"})),
    SectionSpec("deviations", "Form 12: Deviations", 150,
                SectionKind.COMPLIANCE, 0),
    # The per-criterion drafts, in the document. `do_generate` already pays a model call per
    # criterion and validates every sentence, and until now that work reached the exported
    # file only as the word "Comply" in a matrix cell. Universal: every tender has
    # requirements, so every proposal answers them.
    SectionSpec("requirement_responses", "Responses to Tender Requirements", 155,
                SectionKind.COMPLIANCE, 0),
    SectionSpec("compliance_matrix", "Technical Compliance Matrix", 160,
                SectionKind.COMPLIANCE, 0),
    # An INDEX of the templates the tender prescribes and where it asks for them — never the
    # forms themselves. A drafter must not author the body of a certificate the bidder signs.
    SectionSpec("prescribed_forms", "Prescribed Forms and Declarations", 165,
                SectionKind.COMPLIANCE, 0, requires=frozenset({"forms"})),
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
    #: An assembled section used to be `drafted` unconditionally, which was true while every
    #: assembler read structured rows that either existed or did not. `item_compliance` makes
    #: a clause-by-clause claim about goods the bidder will be bound to supply, so it has to
    #: be able to say "this is not finished" in the one vocabulary the export gate reads.
    status: str = "drafted"


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
        valid_to = c.get("valid_to")
        # Three states, not two. A certificate with no expiry on file used to print "EXPIRED
        # (no expiry recorded)" in a sheet that goes to a public buyer — a false statement
        # about the bidder's own standing (seen live: four current ISO/API certs, all
        # "EXPIRED"). Unknown is unknown; only a recorded past date is an expiry.
        if not valid_to:
            position = "Validity not recorded — add the expiry date to the vendor profile"
        elif str(valid_to) >= today:
            position = "Valid"
        else:
            position = f"EXPIRED ({valid_to})"
        add(str(c.get("name") or "Certification"), position, "Copy of certificate")

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


def assemble_deviations(schedule: dict | None = None) -> AssembledSection:
    """Form 12 — deviations, read from the schedule fit rather than assumed.

    This used to return a flat "The bidder confirms **no deviations**" on every tender,
    which is a declaration to a public buyer that nothing in the document had checked —
    and it could contradict the same workspace's own schedule screen, where `spec_match`
    had already found a parameter outside the plant's range. A nil-deviation statement is
    not a safe default; it is a claim, and the bidder signs it.

    So there are three outcomes and never one:
      - deviations found  → they are listed, with the tender's requirement beside the
        recorded capability, for the bid owner to accept, withdraw or clarify.
      - nothing found AND something was assessed → a nil statement QUALIFIED by what was
        actually compared, because "no deviations among the 14 parameters we could read"
        is true and "no deviations" is not.
      - nothing assessed (no schedule read, or no capability recorded) → no statement at
        all. An unassessed parameter is unknown, never compliant (the same asymmetry
        `spec_match` is built on).

    Still deliberately NOT model-generated: proposing a deviation is a commercial decision
    with contractual consequences, and an invented one could invalidate the bid.
    """
    lines = list((schedule or {}).get("lines") or [])
    deviating: list[list[str]] = []
    equivalent: list[list[str]] = []
    assessed = 0
    unknown = 0
    for line in lines:
        ref = " · ".join(
            str(x) for x in (line.get("schedule_ref"), line.get("item_ref")) if x
        ) or (line.get("description") or "—")[:60]
        for param in line.get("parameters") or []:
            state = param.get("match")
            row = [ref, str(param.get("key") or "—"), str(param.get("required") or "—"),
                   str(param.get("capability") or "—")]
            if state == "deviation":
                assessed += 1
                deviating.append(row)
            elif state == "equivalent":
                assessed += 1
                equivalent.append(row)
            elif state == "match":
                assessed += 1
            else:
                unknown += 1

    if not assessed and not unknown:
        return AssembledSection(
            "_No schedule of items has been read for this tender, so no deviation statement "
            "can be made here. The bid owner must enter deviations — or confirm there are "
            "none — before submission._",
            (),
        )

    parts: list[str] = []
    if deviating:
        parts.append(
            f"**{len(deviating)} deviation(s)** were found by comparing this tender's schedule "
            "against the manufacturing capability recorded in this workspace. Each must be "
            "accepted, withdrawn or raised as a pre-bid clarification before submission."
        )
        parts.append(_table(
            ["Schedule line", "Parameter", "Tender requires", "Recorded capability"], deviating
        ))
    if equivalent:
        parts.append(
            f"A further **{len(equivalent)}** parameter(s) fall outside the recorded capability "
            "on a requirement whose own wording invites an equivalent. They are deviations "
            "unless the buyer accepts the equivalence."
        )
        parts.append(_table(
            ["Schedule line", "Parameter", "Tender requires", "Recorded capability"], equivalent
        ))
    if not deviating and not equivalent:
        parts.append(
            f"No deviation was found among the **{assessed} parameter(s)** compared against "
            "the manufacturing capability recorded in this workspace."
        )
    if unknown:
        parts.append(
            f"_{unknown} parameter(s) could not be compared, because no capability is recorded "
            "for them. They are unassessed, not compliant — a nil-deviation declaration should "
            "not be signed until they are checked._"
        )
    return AssembledSection("\n\n".join(parts), ())


def assemble_compliance_matrix(
    criteria: list[dict], responses: list[dict], has_responses_section: bool = False
) -> AssembledSection:
    """Clause-by-clause index of where each requirement is answered.

    IT NO LONGER SAYS "Comply". A draft status of `drafted` means a model wrote a response
    and the citation validator did not flag it; it does not mean the bidder complies, and
    printing that word to a public buyer on the strength of it is a claim nobody made. The
    same mapping turned `placeholder` into "Not addressed", which reads as a decision rather
    than as unfinished work.

    So the column becomes a cross-reference into `requirement_responses`, where the actual
    answer now lives, and the state column describes the RESPONSE rather than the bidder:
    answered / source pending / not yet answered. Whether the bidder complies is a judgement
    the bid owner makes and signs, which is the same reasoning that keeps `assemble_deviations`
    from defaulting to a nil-deviation statement.
    """
    by_crit = {r.get("criterion_id"): r for r in responses}
    state_label = {
        "drafted": "Answered",
        "unverified": "Answered — source pending",
        "placeholder": "Not yet answered",
        "missing": "Not yet answered",
    }
    rows = []
    for i, c in enumerate(criteria, 1):
        r = by_crit.get(c["id"], {})
        rows.append([
            (c.get("verbatim_text") or "")[:160],
            str(c.get("requirement_level") or "—"),
            state_label.get(r.get("draft_status"), "Not yet answered"),
            f"Requirement responses, item {i}" if has_responses_section else "—",
            str(c.get("source_anchor") or c.get("anchor_clause") or "—"),
        ])
    return AssembledSection(
        "_This index says where each requirement is answered, not whether the bidder "
        "complies. Compliance is the bid owner's judgement to make and sign._\n\n"
        + _table(
            ["Requirement", "Level", "Response state", "Answered in", "Tender reference"],
            rows,
        ),
        (),
    )


def assemble_item_compliance(schedule: dict | None = None) -> AssembledSection:
    """One group per schedule line, a parameter table per group. The goods path's answer to
    a Technical Compliance section, and the first place the goods path transcludes anything.

    THE RULE THIS SECTION IS SHAPED AROUND: an unassessed parameter renders "Not assessed",
    never "Comply". The same asymmetry `spec_match` is built on, and it matters more here
    than anywhere else in the document — this table is a clause-by-clause statement to a
    public buyer about goods the bidder will be contractually bound to supply. So a line
    carrying any unknown forces the SECTION to `placeholder`, which the export gate blocks
    on, rather than exporting a compliance claim nobody checked.

    The negative test that shaped it is the Oil India package, whose BOQ csv is an unfilled
    template — literal `Title1` / `Description1` cells. Against that input this must render
    "not assessed" and refuse to export, not claim compliance against `Description1`.
    """
    lines = list((schedule or {}).get("lines") or [])
    if not lines:
        return AssembledSection(_EMPTY, (), status="placeholder")

    label = {"match": "Comply", "deviation": "Deviation", "equivalent": "Equivalent offered",
             "unknown": "Not assessed"}
    blocks: list[str] = []
    sents: list[DraftSentence] = []
    unassessed = 0

    for line in lines:
        ref = " · ".join(
            str(x) for x in (line.get("schedule_ref"), line.get("item_ref")) if x
        ) or "Unnumbered line"
        desc = " ".join(str(line.get("description") or "").split())[:120] or "—"
        blocks.append(f"**{ref}** — {desc}")

        params = list(line.get("parameters") or [])
        if not params:
            unassessed += 1
            blocks.append(
                "_No technical parameter was read from this line, so nothing has been "
                "compared. This is unknown, not compliance._"
            )
            continue

        rows = []
        for m in params:
            state = str(m.get("match") or "unknown")
            unassessed += state == "unknown"
            offered = str(m.get("capability") or "").strip()
            rows.append([str(m.get("key") or "—"), str(m.get("required") or "—"),
                         offered or "Not recorded", label.get(state, "Not assessed")])
            if state in ("match", "equivalent") and offered:
                # The offered value comes from a structured `product_specs` row, so it
                # transcludes — the goods path's first exemption from B-AC4, and the only
                # honest way to state a number the bidder will be held to.
                sents.append(_val(offered, f"product_specs:{line.get('id')}.{m.get('key')}"))
        blocks.append(_table(["Parameter", "Tender requires", "Offered", "Status"], rows))

    if unassessed:
        blocks.append(
            f"_{unassessed} parameter(s) could not be assessed. Record the capability on "
            "/capability, or state the offer for each line, before this section can be "
            "exported._"
        )
    return AssembledSection(
        "\n\n".join(blocks), tuple(sents),
        status="placeholder" if unassessed else "drafted",
    )


def assemble_prescribed_forms(criteria: list[dict]) -> AssembledSection:
    """An INDEX of the templates this tender prescribes and where it asks for them.

    Never the forms themselves. A drafter must not author the body of a certificate the
    bidder signs — a generated undertaking is a false statement with the bidder's name on it,
    and an unfilled template reaching the library is already a known way for placeholder text
    to arrive in a submission wearing a citation.

    A form still carrying a blank marker is called out by name, because that is the state a
    bidder loses a bid to: the template was attached and nobody filled it in.
    """
    rows = []
    for c in criteria:
        if effective_kind(c) is not RequirementKind.FORM:
            continue
        text = " ".join(str(c.get("verbatim_text") or "").split())
        blanks = template_placeholders(text)
        rows.append([
            text[:140] + ("…" if len(text) > 140 else ""),
            str(c.get("requirement_level") or "—"),
            str(c.get("source_anchor") or c.get("anchor_clause")
                or (f"p.{c['anchor_page']}" if c.get("anchor_page") else "—")),
            "Blanks to fill" if blanks else "Attach signed",
        ])
    if not rows:
        return AssembledSection(_EMPTY, ())
    return AssembledSection(
        "_This tender prescribes the following forms. Attach each one signed; the text of a "
        "declaration is the bidder's to write, never this system's._\n\n"
        + _table(["Form / declaration", "Level", "Tender reference", "Action"], rows),
        (),
    )


def assemble_requirement_responses(criteria: list[dict], responses: list[dict]) -> AssembledSection:
    """The per-criterion drafts, in the document.

    `do_generate` already pays a model call per criterion and validates every sentence, and
    until now that work reached the exported document only as the word "Comply" in a matrix
    cell. Here it is the response itself.

    Flags are deliberately NOT carried across. They are already reported on the per-criterion
    layer and by the export gate; repeating them here would report one blocker twice under
    two names, which is the disagreeing-counters problem `submission.py` was written about.
    The stored sentences ARE carried, because they were validated and they hold the
    transclusions.
    """
    by_crit = {r.get("criterion_id"): r for r in responses}
    blocks: list[str] = []
    sents: list[DraftSentence] = []
    open_count = 0

    for c in criteria:
        r = by_crit.get(c["id"])
        text = " ".join(str(c.get("verbatim_text") or "").split())
        ref = str(c.get("source_anchor") or c.get("anchor_clause")
                  or (f"p.{c['anchor_page']}" if c.get("anchor_page") else "—"))
        body = " ".join(str((r or {}).get("draft_text") or "").split())
        if not body:
            open_count += 1
            body = ("_No response drafted for this requirement yet._")
        blocks.append(f"**{ref}** — {text[:200]}\n\n{body}")
        for raw in ((r or {}).get("sentences") or []):
            if isinstance(raw, dict) and raw.get("is_transcluded"):
                sents.append(_val(str(raw.get("text") or ""), str(raw.get("source_ref") or "")))

    if not blocks:
        return AssembledSection(_EMPTY, ())
    return AssembledSection(
        "\n\n".join(blocks), tuple(sents),
        status="placeholder" if open_count else "drafted",
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
