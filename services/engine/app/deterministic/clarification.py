"""What to ask the buyer before bidding — UML ask 2, step 2 of their process flow.

Module H already computes this and throws it away. `spec_match.catalogue_state` returns
`action_parameters`, documented at its definition as "the pre-bid clarification trigger", and
`ScheduleFit.tsx` renders the word "Clarify:" beside the parameter keys. Nothing turns that into
a question anybody can send. This module does, and nothing here decides anything the comparator
did not already decide — it is a renderer over verdicts.

TWO RULES SHAPE EVERY TEMPLATE HERE.

**The bidder's capability never appears in query text.** GeM publishes a buyer's clarification
answers to every bidder on the tender (UML's own diagram: "Responses are shared by Buyer"), so a
question phrased as "our manufacturing range is 24-60 mm, will you accept that?" hands a
competitor the plant's limits and tells the buyer we are non-compliant before the bid opens.
The capability is why the question exists; it is not part of the question. It travels in
`rationale`, which is workspace-internal, and never in `text`.

**No model writes any of it.** A pre-bid query goes to a public buyer over the client's name and
becomes part of the tender record. `deterministic/style.py` established the boundary for a much
weaker artefact — a style brief that only shapes prose — and a question that commits the bidder
in front of a government buyer sits far on the other side of it. Every sentence below is a
format string over typed values the comparator produced.

A DEVIATION asks whether the stated value is mandatory. An UNKNOWN asks the buyer to state the
value at all. A MATCH asks nothing, and an EQUIVALENT asks nothing either — the tender's own
words already invited the alternative, so raising it would be asking permission that was granted
in the document we are quoting.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from .spec_params import REGISTRY


class QueryKind(StrEnum):
    #: The comparator proved the requirement lies outside the bidder's envelope.
    RELAXATION = "relaxation"
    #: The requirement could not be read at all. Asking is cheaper than assuming either way.
    CONFIRMATION = "confirmation"


@dataclass(frozen=True)
class LineRef:
    """Where a question came from. Every query carries these so an answer can be applied back
    to the exact schedule lines it settles, rather than to a parameter name in the abstract."""

    line_id: str
    schedule_ref: str | None
    item_ref: str | None
    anchor: str


@dataclass(frozen=True)
class ClarificationQuery:
    param_key: str
    label: str
    kind: QueryKind
    #: The requirement as the comparator displayed it — the buyer's own number, not ours.
    required_display: str
    #: Workspace-internal. Never rendered into `text`; see the module docstring.
    rationale: str
    text: str
    lines: tuple[LineRef, ...]


@dataclass(frozen=True)
class ClarificationPack:
    #: Bounded by `spec_params.REGISTRY` without needing a cap: queries fold by parameter key,
    #: and the extractor's output schema is an enum over the registry (the G-6 allowlist), so a
    #: schedule of any size yields at most one query per registered parameter. There is
    #: deliberately no truncation here — a silently shortened list of things a buyer must answer
    #: reads as "these are all the problems", which is the one thing it would not be.
    queries: tuple[ClarificationQuery, ...]


def _label(param_key: str) -> str:
    registered = REGISTRY.get(param_key)
    return registered.label if registered else param_key.replace("_", " ")


def _line_ref(line: dict) -> LineRef:
    return LineRef(
        line_id=str(line.get("id") or ""),
        schedule_ref=line.get("schedule_ref") or None,
        item_ref=line.get("item_ref") or None,
        anchor=line.get("anchor") or "no anchor",
    )


def _where(lines: Sequence[LineRef]) -> str:
    """"Schedule-A item 14" for one line, "3 schedule lines" for several.

    Naming every line for a parameter that deviates across a whole schedule would produce a
    question longer than the answer. The full list is still attached to the query; this is the
    sentence, not the record.
    """
    if len(lines) > 1:
        return f"{len(lines)} schedule lines"
    first = lines[0]
    parts = [p for p in (first.schedule_ref, first.item_ref) if p]
    return " ".join(parts) if parts else first.anchor


def _text(kind: QueryKind, label: str, required: str, where: str) -> str:
    if kind is QueryKind.RELAXATION:
        return (
            f"{where}: the specification states {label.lower()} of {required}. "
            f"Please confirm whether this value is mandatory, or whether an alternative "
            f"specification meeting the functional requirement would be acceptable."
        )
    return (
        f"{where}: the required {label.lower()} could not be determined from the tender "
        f"documents. Please confirm the {label.lower()} required."
    )


def build_queries(lines: Sequence[dict]) -> ClarificationPack:
    """Assessed schedule lines -> the questions worth asking, one per parameter.

    Takes `spec_service.assess_schedule`'s `lines` directly rather than the database, so the
    whole module is testable on literals and cannot acquire an I/O dependency later.

    Questions fold by parameter: one diameter deviating across nine schedule lines is one
    question carrying nine line references, not nine questions. All nine references travel with
    it, so an answer applies back to every line it settles.
    """
    #: param_key -> (kind, required_display, rationale, [LineRef]). Insertion-ordered, so the
    #: pack follows schedule order and two runs over the same schedule agree.
    found: dict[str, tuple[QueryKind, str, str, list[LineRef]]] = {}

    for line in lines:
        actionable = set(line.get("action_parameters") or ())
        ref = _line_ref(line)
        for param in line.get("parameters") or ():
            key = param.get("key")
            if not key:
                continue
            match = param.get("match")
            if match == "deviation":
                kind = QueryKind.RELAXATION
            elif match == "unknown" and key in actionable:
                kind = QueryKind.CONFIRMATION
            else:
                # MATCH needs nothing. EQUIVALENT needs nothing: the tender invited it.
                continue

            if key in found:
                existing = found[key]
                # A deviation outranks a confirmation on the same parameter: one line proving
                # the value is outside the envelope is a stronger question than another line
                # failing to state it, and asking both would be asking twice.
                if existing[0] is QueryKind.CONFIRMATION and kind is QueryKind.RELAXATION:
                    found[key] = (kind, param.get("required") or "—",
                                  param.get("reason") or "", existing[3])
                existing[3].append(ref)
                continue

            found[key] = (kind, param.get("required") or "—", param.get("reason") or "", [ref])

    # Deviations first — they are the ones that lose the bid if unanswered. `sorted` is stable,
    # so within each kind the pack stays in schedule order and two runs agree.
    ordered = sorted(
        found.items(), key=lambda item: 0 if item[1][0] is QueryKind.RELAXATION else 1
    )

    queries: list[ClarificationQuery] = []
    for key, (kind, required, rationale, refs) in ordered:
        label = _label(key)
        queries.append(
            ClarificationQuery(
                param_key=key,
                label=label,
                kind=kind,
                required_display=required,
                rationale=rationale,
                text=_text(kind, label, required, _where(refs)),
                lines=tuple(refs),
            )
        )

    return ClarificationPack(tuple(queries))


# ── derived questions x what has already happened to them ────────────────────────────

@dataclass(frozen=True)
class ClarificationView:
    """One row of the pack screen: the question, plus whatever has become of it.

    `stale` is the field worth explaining. A stored question whose parameter no longer appears
    in the derived pack has been overtaken — the corrigendum relaxed the requirement, or the
    bidder widened the envelope. A DRAFT in that state is simply deleted. One already SENT is
    kept and flagged, because it was asked: the buyer may still answer it, and a product that
    quietly erased a question it had put to a public buyer would be rewriting the record.
    """

    param_key: str
    label: str
    kind: QueryKind
    required_display: str
    rationale: str
    text: str
    lines: tuple[LineRef, ...]
    clarification_id: str | None
    status: str
    answer_text: str | None
    answer_source: str | None
    sent_at: str | None
    answered_at: str | None
    stale: bool


def _view(query: ClarificationQuery, stored: dict | None, *, stale: bool) -> ClarificationView:
    status = (stored or {}).get("status") or "draft"
    # The TEXT of a sent question is what was actually put in front of the buyer. The derived
    # text may have moved since; showing the new one would misreport what was asked.
    text = (stored or {}).get("query_text") if status != "draft" else None
    return ClarificationView(
        param_key=query.param_key,
        label=query.label,
        kind=query.kind,
        required_display=query.required_display,
        rationale=query.rationale,
        text=text or query.text,
        lines=query.lines,
        clarification_id=(stored or {}).get("id"),
        status=status,
        answer_text=(stored or {}).get("answer_text"),
        answer_source=(stored or {}).get("answer_source"),
        sent_at=(stored or {}).get("sent_at"),
        answered_at=(stored or {}).get("answered_at"),
        stale=stale,
    )


def _query_from_stored(stored: dict) -> ClarificationQuery:
    """Rebuild a question from its stored row, for one that the schedule no longer raises."""
    kind = (
        QueryKind.RELAXATION
        if stored.get("kind") == QueryKind.RELAXATION.value
        else QueryKind.CONFIRMATION
    )
    key = stored.get("param_key") or ""
    return ClarificationQuery(
        param_key=key,
        label=_label(key),
        kind=kind,
        required_display=stored.get("required_display") or "—",
        rationale=stored.get("rationale") or "",
        text=stored.get("query_text") or "",
        lines=(),
    )


def merge_with_stored(
    pack: ClarificationPack, stored: Sequence[dict]
) -> tuple[ClarificationView, ...]:
    """The derived pack joined to what has already been asked and answered.

    Both directions matter. A derived question with no stored row is a draft nobody has acted
    on. A stored row with no derived question has been overtaken by a change to the schedule or
    the envelope — kept only if it was actually sent, and flagged when it is.
    """
    by_key = {row.get("param_key"): row for row in stored if row.get("param_key")}

    views = [_view(q, by_key.get(q.param_key), stale=False) for q in pack.queries]

    derived_keys = {q.param_key for q in pack.queries}
    views.extend(
        _view(_query_from_stored(row), row, stale=True)
        for key, row in by_key.items()
        if key not in derived_keys and row.get("status") != "draft"
    )
    return tuple(views)
