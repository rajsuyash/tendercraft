"""Module H orchestration — schedule in, fit out.

Three jobs, kept apart on purpose:

  `persist_schedule`  BOQ rows (and technical criteria) -> tender_line_items
  `extract_schedule`  line item descriptions -> typed parameters, via the model
  `assess_schedule`   line items x the bidder's specs -> a fit per line, via pure functions

Only the middle one talks to a model, and it decides nothing: `assess_schedule` reads rows out
of the database and hands them to `deterministic/spec_match.py`. If the extractor were removed
entirely the assessment would still run and would report `unknown` everywhere, which is exactly
what it should say when nobody has read the specification.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from . import db
from .deterministic.boq import BoqRow
from .deterministic.clarification import build_queries, merge_with_stored
from .deterministic.spec_match import (
    CapabilitySpec,
    CatalogueState,
    ParamKind,
    ParamValue,
    SpecOverall,
    catalogue_state,
)
from .deterministic.spec_params import ParamKind as _Kind  # noqa: F401  (re-export clarity)

log = logging.getLogger("tendercraft.spec")

#: Technical criteria become line items too. Most GeM rope bids state the specification in NIT
#: prose and ship no BOQ at all, so a schedule built only from spreadsheets would work on
#: roughly one tender in five.
_TECHNICAL = "technical"


# ── persistence ──────────────────────────────────────────────────────────────────────

def schedule_rows(boq: Sequence[BoqRow], criteria: Sequence[dict]) -> list[dict]:
    """The tender's schedule from both sources, in the shape `tender_line_items` expects."""
    rows: list[dict] = [
        {
            "description": item.description,
            "schedule_ref": item.schedule_ref or None,
            "item_ref": item.item_ref or None,
            "quantity": item.quantity,
            "uom": item.uom,
            "anchor_document": item.document,
            "anchor_page": item.sheet_index,
            "anchor_row": item.row_number,
        }
        for item in boq
    ]
    rows.extend(
        {
            "description": c["verbatim_text"],
            "anchor_document": c.get("anchor_document"),
            "anchor_page": c.get("anchor_page"),
            "source_criterion_id": c["id"],
        }
        for c in criteria
        if c.get("category") == _TECHNICAL and (c.get("verbatim_text") or "").strip()
    )
    return rows


def persist_schedule(
    workspace_id: str, tender_id: str, boq: Sequence[BoqRow], criteria: Sequence[dict]
) -> list[dict]:
    rows = schedule_rows(boq, criteria)
    if not rows:
        return []
    return db.replace_line_items(workspace_id, tender_id, rows)


# ── extraction (the only model call in Module H) ─────────────────────────────────────

def extract_schedule(workspace_id: str, line_items: Sequence[dict]) -> int:
    """Read every distinct description once and store the parameters. Returns lines populated.

    Import is local so `app.spec_service` stays importable — and the assessment path stays
    runnable — in a deployment where the model client is not configured at all.
    """
    from pipeline.spec_extractor import extract_many

    by_description = extract_many([i.get("description", "") for i in line_items])
    populated = 0
    for item in line_items:
        params = by_description.get((item.get("description") or "").strip(), ())
        if not params:
            continue
        db.replace_line_item_parameters(
            workspace_id, item["id"],
            [
                {
                    "param_key": p.key,
                    "kind": p.kind.value,
                    "unit": p.unit,
                    "num_min": p.num_min,
                    "num_max": p.num_max,
                    "allowed_values": sorted(p.allowed),
                    "raw_text": p.raw_text,
                }
                for p in params
            ],
        )
        populated += 1
    return populated


# ── rows -> domain ───────────────────────────────────────────────────────────────────

def _to_param(row: dict) -> ParamValue | None:
    """A stored parameter row -> a comparable value. None when the row cannot decide anything.

    The database CHECK constraints already refuse an unbounded numeric and a valueless enum, so
    this is defensive rather than load-bearing — but a row written before a constraint existed,
    or by a future migration, must be dropped rather than silently compared as empty.
    """
    kind = ParamKind.NUMERIC if row.get("kind") == "numeric" else ParamKind.ENUM
    key = row.get("param_key")
    if not key:
        return None
    if kind is ParamKind.NUMERIC:
        low, high = row.get("num_min"), row.get("num_max")
        if low is None and high is None:
            return None
        return ParamValue(
            key, kind, unit=row.get("unit"),
            num_min=None if low is None else float(low),
            num_max=None if high is None else float(high),
            raw_text=row.get("raw_text") or "",
        )
    # `.strip()` before the truthiness test, not after: " " is truthy, and a whitespace-only
    # value normalises to an empty token that would then match another empty token — a silent
    # false MATCH on a parameter nobody stated.
    allowed = frozenset(s for v in (row.get("allowed_values") or []) if (s := str(v).strip()))
    if not allowed:
        return None
    return ParamValue(key, kind, allowed=allowed, raw_text=row.get("raw_text") or "")


def _params(row: dict) -> tuple[ParamValue, ...]:
    return tuple(
        p for p in (_to_param(r) for r in row.get("spec_parameters") or []) if p is not None
    )


def _capabilities(spec_rows: Sequence[dict]) -> tuple[list[CapabilitySpec], list[CapabilitySpec]]:
    catalogues, envelopes = [], []
    for row in spec_rows:
        spec = CapabilitySpec(
            id=row["id"], label=row.get("label") or "",
            parameters=_params(row), gem_catalogue_id=row.get("gem_catalogue_id"),
        )
        (catalogues if row.get("spec_kind") == "catalogue" else envelopes).append(spec)
    return catalogues, envelopes


# ── assessment (pure once the rows are loaded) ───────────────────────────────────────

def assess_schedule(workspace_id: str, tender_id: str) -> dict[str, Any]:
    """Fit every schedule line against what the bidder can make and what they have listed.

    Two queries, then arithmetic in memory. A per-line query would be the N+1 in
    docs/known-pitfalls.md multiplied by however many lines a schedule has.
    """
    line_rows = db.get_line_items(tender_id, workspace_id)
    spec_rows = db.get_capability_specs(workspace_id)
    catalogues, envelopes = _capabilities(spec_rows)

    lines: list[dict[str, Any]] = []
    for row in line_rows:
        required = _params(row)
        decision = catalogue_state(required, catalogues, envelopes)
        result = decision.result
        lines.append(
            {
                "id": row["id"],
                "schedule_ref": row.get("schedule_ref"),
                "item_ref": row.get("item_ref"),
                "description": row.get("description"),
                "quantity": row.get("quantity"),
                "uom": row.get("uom"),
                "anchor": _anchor_label(row),
                "parameters_read": len(required),
                "catalogue_state": decision.state.value,
                "gem_catalogue_id": decision.gem_catalogue_id,
                "matched_spec": result.spec_label if result else None,
                "overall": result.overall.value if result else SpecOverall.NEEDS_REVIEW.value,
                "parameters": [
                    {
                        "key": m.key, "match": m.match.value, "required": m.required_display,
                        "capability": m.capability_display, "reason": m.reason,
                    }
                    for m in (result.parameters if result else ())
                ],
                "action_parameters": [m.key for m in decision.action_parameters],
            }
        )

    return {
        "lines": lines,
        "summary": _summarise(lines),
        # Said once, here, so no screen has to invent the wording. We never read GeM to obtain
        # or verify a catalogue (G-1/G-8) — "published" is the bidder's own record.
        "catalogue_source": "recorded_by_you",
        "has_capability": bool(envelopes or catalogues),
    }


# ── pre-bid clarifications (UML ask 2) ───────────────────────────────────────────────

def clarification_pack(workspace_id: str, tender_id: str) -> dict[str, Any]:
    """The questions this tender raises, joined to what has already been asked and answered.

    Read-only. The pack is re-derived from the schedule on every call, so it costs one extra
    query over `assess_schedule` and no model call — which is deliberate: a bidder checking what
    they still need to ask, during a model outage, gets the real answer rather than a spinner.
    """
    assessment = assess_schedule(workspace_id, tender_id)
    pack = build_queries(assessment["lines"])
    stored = db.get_clarifications(tender_id, workspace_id)
    views = merge_with_stored(pack, stored)

    return {
        "clarifications": [
            {
                "id": v.clarification_id,
                "param_key": v.param_key,
                "label": v.label,
                "kind": v.kind.value,
                "required": v.required_display,
                # Workspace-internal, and it names the bidder's own capability. Safe on this
                # screen, never in `text` — GeM publishes a buyer's answers to every bidder.
                "rationale": v.rationale,
                "text": v.text,
                "lines": [
                    {"id": ref.line_id, "schedule_ref": ref.schedule_ref,
                     "item_ref": ref.item_ref, "anchor": ref.anchor}
                    for ref in v.lines
                ],
                "status": v.status,
                "answer_text": v.answer_text,
                "answer_source": v.answer_source,
                "sent_at": v.sent_at,
                "answered_at": v.answered_at,
                "stale": v.stale,
            }
            for v in views
        ],
        "summary": _clarification_summary(views),
        # Said once, here. Every surface must repeat it: we do not post to GeM (G-1), so `sent`
        # records that the BIDDER posted the question, exactly as `published` records that the
        # bidder listed the catalogue item.
        "posting": "by_you",
        "schedule_lines": assessment["summary"]["total"],
    }


def _clarification_summary(views: Sequence[Any]) -> dict[str, int]:
    """One function computes the counts, so no screen can show a number nothing explains."""
    statuses = [v.status for v in views]
    return {
        "total": len(views),
        "draft": statuses.count("draft"),
        "sent": statuses.count("sent"),
        "answered": statuses.count("answered"),
        "withdrawn": statuses.count("withdrawn"),
        "open": sum(1 for v in views if v.status in ("draft", "sent")),
    }


def save_clarification_drafts(workspace_id: str, tender_id: str, created_by: str) -> dict[str, int]:
    """Persist the derived pack. Idempotent, and it never touches a question already asked.

    Two writes, in this order for a reason: upsert first, then drop the drafts the schedule no
    longer raises. Dropping first would leave a window in which a concurrent read shows an empty
    pack for a tender that has questions.
    """
    assessment = assess_schedule(workspace_id, tender_id)
    pack = build_queries(assessment["lines"])

    db.upsert_clarification_drafts(workspace_id, tender_id, [
        {
            "param_key": q.param_key,
            "kind": q.kind.value,
            "query_text": q.text,
            "required_display": q.required_display,
            "rationale": q.rationale,
            "line_ids": [ref.line_id for ref in q.lines if ref.line_id],
            "created_by": created_by,
        }
        for q in pack.queries
    ])
    db.delete_stale_clarification_drafts(
        workspace_id, tender_id, [q.param_key for q in pack.queries]
    )
    return {"saved": len(pack.queries)}


def _anchor_label(row: dict) -> str:
    """"BOQ.xlsx · Schedule-A · row 14" — where a human goes to check the line."""
    parts = [p for p in (row.get("anchor_document"),) if p]
    if row.get("anchor_row"):
        parts.append(f"row {row['anchor_row']}")
    elif row.get("anchor_page"):
        parts.append(f"p.{row['anchor_page']}")
    return " · ".join(parts) or "no anchor"


def _summarise(lines: Sequence[dict]) -> dict[str, int]:
    """One function computes the counts, so a screen can never show a number nothing explains
    (docs/known-pitfalls.md: four counters describing one object will disagree)."""
    states = [line["catalogue_state"] for line in lines]
    return {
        "total": len(lines),
        "published": states.count(CatalogueState.PUBLISHED.value),
        "creatable": states.count(CatalogueState.CREATABLE.value),
        "not_creatable": states.count(CatalogueState.NOT_CREATABLE.value),
        "unknown": states.count(CatalogueState.UNKNOWN.value),
    }
