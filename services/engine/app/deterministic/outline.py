"""Which sections a tender's proposal actually needs.

`SECTION_SPECS` stops being *the outline* and becomes *the catalogue*. A fixed seventeen-
section IT-services packet was applied to every tender, including a wire-rope supply bid,
which is why most of that document was unusable: "Training and Capacity Building" and
"Proposed Solution and Technical Architecture" against a schedule of rope.

THE DECISION THAT MAKES THE REST FALL OUT: keys are never derived, inclusion is. A
generation may not mint a section key. Every catalogue entry already carries a drafting
brief, an assembler, a rubric emphasis and a stable `answer_usages.target`, none of which a
freshly-minted key would have — so key stability is a property of the design rather than a
convention someone has to keep.

NO GOODS/SERVICES CLASSIFIER. The obvious move is a domain switch, and it misfires on all
five sample packages: these tenders are supply *plus* inspection *plus* guarantee *plus*
policy declaration at once. Instead every conditional section names a SIGNAL, each signal is
a row the tender actually contains, and the outline records which rows fired. That is
cite-or-flag applied to structure: the screen can say "Team Composition is here because of
the CV format at p.31", and equally "Training is absent because nothing in this tender asks
for it".

Set membership rather than a regex tree is what keeps this file at 100% branch coverage:
a spec is included iff `spec.requires <= signals`, and `requires=frozenset()` is universal.

MEASURED against the live corpus on 2026-09-15 — 2,000 criteria across eleven real tenders,
not a fixture:

    NABARD rural-survey RFP        17 sections   solution, training, personnel, workplan,
                                                 eval_heads
    a software services tender     12 sections   solution, support
    NMDC ore-handling supply       12 sections   forms, schedule — and none of solution,
                                                 workplan, personnel, training, support
    Oil India wire rope            13 sections   forms, schedule, support
    a bare purchase order          10 sections   no signal at all: the universal spine

WHICH WAY TO BE WRONG. Over-inclusion costs a thin section the bidder can delete; omission
costs a section the buyer asked for and the bid does not contain, which is a rejected bid.
So the patterns are tuned to be narrow rather than absent, and every included section names
the row that put it there — a section the user did not expect is answerable rather than
arbitrary. One known over-inclusion survives on the wire-rope bid: a local-content
declaration listing "after sales service support like AMC/CMC etc." among things EXCLUDED
from local content pulls in the Support/SLA section. The clause is genuinely in the tender,
the reason is shown, and reading "excluded from" as a negation is not something a pattern
can do.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .requirement_kind import effective_kind
from .types import RequirementKind

#: Each signal is a question about rows the tender contains, never about what kind of thing
#: is being bought. The patterns are deliberately narrow: a signal that fires on everything
#: rebuilds the fixed packet with extra steps.
#:
#: `support` is the one to read twice. It does NOT include a bare "warranty": every goods
#: tender in the corpus carries "the warranty period shall be 24 months", and matching it
#: would put a Support/SLA/O&M section on every rope bid — which is the defect, not the fix.
#: Ongoing service has its own vocabulary and that is what is matched.
#:
#: Four terms were in the first cut and were removed after measuring their reach against the
#: live corpus rather than reasoning about them. Every one fired on wire-rope tenders:
#:
#:   `\bapi\b`         23 hits, all of them **API Specification 9A** — the American
#:                      Petroleum Institute's rope standard, not a software interface.
#:   `platform`        the **TReDS** and **SFMS** platforms, which are banking payment rails
#:                      named in an MSME registration clause and a bank-guarantee clause.
#:   `application`     "…their selection for various applications" in a rope description.
#:   bare `training`   one hit inside a local-content declaration that mentions it in
#:                      passing; `training` now needs a provisioning verb or a real noun
#:                      phrase beside it.
#:
#: The lesson is the one `discovery.py` already learned about bounded stems: a term short
#: enough to be an acronym will collide with a standard number, and the corpus is the only
#: place that shows it.
_SIGNAL_PATTERNS: dict[str, re.Pattern[str]] = {
    "personnel": re.compile(
        r"\b(?:curriculum vitae|\bcvs?\b|key personnel|team composition|manpower"
        r"|deployment of personnel|project manager|team leader|resource deployment"
        r"|qualification of (?:the )?(?:staff|personnel|team))\b", re.I),
    # `software`, `architecture` and `ai/ml` are bare stems and that is deliberate: measured
    # against the live corpus they have ZERO hits across every goods tender and real reach on
    # the services ones. `system` was measured with them and rejected — "TWO Part Bid System".
    "solution": re.compile(
        r"\b(?:software|architecture|ai\s*/?\s*ml"
        r"|solution design|technology stack|database design|network design"
        r"|web application|mobile application|digital platform|it infrastructure"
        r"|system integration)\b", re.I),
    # The verb and the noun are allowed up to three words apart: the live phrasing is "the
    # field staff ... would have to be provided with adequate training by the agency", and an
    # adjacent-words rule missed it — a false negative on the one tender that plainly needs a
    # training section.
    "training": re.compile(
        r"\b(?:capacity building|user manuals?|train the trainer|knowledge transfer"
        r"|training (?:programme|program|plan|module|session|shall|will|is to be|to be)"
        r"|(?:impart|provide|conduct|deliver)\w*(?:\s+\w+){0,3}\s+training)\b", re.I),
    "support": re.compile(
        r"\b(?:helpdesk|help desk|service level agreement|\bsla\b|\bamc\b"
        r"|annual maintenance contract|operations? (?:and|&) maintenance|\bo ?& ?m\b"
        r"|post[- ]implementation support|support services)\b", re.I),
    "workplan": re.compile(
        r"\b(?:work ?plan|project plan|gantt|milestones?|implementation schedule"
        r"|phase[- ]wise|delivery schedule|completion period|project timeline)\b", re.I),
}



@dataclass(frozen=True)
class Signal:
    """One reason a section is in the document, with the row that put it there.

    `because` is the whole point of recording a signal rather than a boolean: a section the
    user did not expect is answerable ("it is here because of this clause") instead of
    arbitrary.
    """

    name: str
    because: str


def detect_signals(
    criteria: Sequence[Mapping], line_items: Sequence[Mapping] = ()
) -> dict[str, Signal]:
    """What this tender contains, as named rows. Deterministic, no model call.

    First hit wins per signal: the outline needs ONE citable reason, and listing every
    matching clause turns an explanation into a wall.
    """
    found: dict[str, Signal] = {}

    if line_items:
        first = line_items[0]
        ref = " ".join(str(first.get(k) or "") for k in ("schedule_ref", "item_ref")).strip()
        found["schedule"] = Signal(
            "schedule",
            f"{len(line_items)} schedule line(s), first at {ref or 'an unlabelled row'}",
        )

    for row in criteria:
        text = str(row.get("verbatim_text") or "")
        anchor = _where(row)
        kind = effective_kind(row)

        if "forms" not in found and kind is RequirementKind.FORM:
            found["forms"] = Signal("forms", f"a prescribed form at {anchor}")
        if "eval_heads" not in found and row.get("evaluation_weight") is not None:
            found["eval_heads"] = Signal(
                "eval_heads", f"a published evaluation weight at {anchor}")

        # A FORM's prose does not vote on what the document must contain. A blank template is
        # boilerplate the bidder fills in, not the buyer asking for something — and the
        # measurement is unambiguous: the local-content declaration on the live wire-rope bid
        # says "after sales service support like AMC/CMC etc." inside a list of what is
        # EXCLUDED from local content, and that one sentence put a Support/SLA/O&M section on
        # a rope supply bid. Its existence is still a signal; its wording is not.
        if kind is RequirementKind.FORM:
            continue

        for name, pattern in _SIGNAL_PATTERNS.items():
            if name not in found and pattern.search(text):
                found[name] = Signal(name, f"{_quote(text)} at {anchor}")

    return found


def _where(row: Mapping) -> str:
    page = row.get("anchor_page")
    clause = row.get("anchor_clause")
    if page and clause:
        return f"p.{page} · Cl. {clause}"
    if page:
        return f"p.{page}"
    return "an unanchored clause"


def _quote(text: str, limit: int = 60) -> str:
    """The clause, short enough to sit on one line. Truncation is marked, because a sentence
    silently cut at a word boundary reads as the tender's own wording."""
    flat = " ".join(text.split())
    return f"“{flat[:limit]}…”" if len(flat) > limit else f"“{flat}”"


@dataclass(frozen=True)
class OutlineEntry:
    key: str
    heading: str
    order: int
    because: str  # "" for a universal section — it is in every proposal and needs no reason


def derive(specs: Sequence, signals: Mapping[str, Signal]) -> tuple[OutlineEntry, ...]:
    """Which catalogue entries this tender gets, in catalogue order.

    A spec is included iff every signal it requires was detected. `requires=frozenset()` is
    universal, which is most of the document: a covering letter, a PQ compliance sheet and an
    evidence index belong in every bid regardless of what is being bought.
    """
    out = []
    for spec in specs:
        required = getattr(spec, "requires", frozenset())
        if not required <= set(signals):
            continue
        out.append(OutlineEntry(
            key=spec.key, heading=spec.heading, order=spec.order,
            because=" · ".join(signals[name].because for name in sorted(required)),
        ))
    return tuple(sorted(out, key=lambda e: e.order))


#: What each signal means in a sentence a bidder can read. The signal NAME is an internal
#: token — "personnel", "eval_heads" — and three absent sections all reporting "(personnel)"
#: told a reader nothing they could act on.
_SIGNAL_MEANING = {
    "schedule": "it states no schedule of items",
    "forms": "it prescribes no forms",
    "personnel": "it asks for no named personnel or CVs",
    "solution": "it asks for no software or system design",
    "training": "it asks for no training",
    "support": "it asks for no ongoing support, SLA or maintenance",
    "workplan": "it states no plan, milestones or delivery schedule",
    "eval_heads": "it publishes no evaluation weights",
}


@dataclass(frozen=True)
class AbsentEntry:
    key: str
    heading: str
    missing: str   # the raw signal names, for a machine
    because: str   # why, in a sentence, for a person


def absent(specs: Sequence, signals: Mapping[str, Signal]) -> tuple[AbsentEntry, ...]:
    """What was left out, and why.

    Reported rather than silently omitted, on the same reasoning as the analysis checklist:
    a section the user expected and did not get is a bug report they cannot file unless the
    screen says why it is gone. It carries the HEADING as well as the key — a user-facing
    list rendering `team_composition` is showing someone a database identifier.
    """
    missing = []
    for spec in specs:
        required = getattr(spec, "requires", frozenset())
        gaps = sorted(set(required) - set(signals))
        if gaps:
            missing.append(AbsentEntry(
                key=spec.key,
                heading=getattr(spec, "heading", spec.key),
                missing=", ".join(gaps),
                because=" and ".join(_SIGNAL_MEANING.get(g, f"it raises no {g} signal")
                                     for g in gaps),
            ))
    return tuple(missing)
