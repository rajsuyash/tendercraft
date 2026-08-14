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
