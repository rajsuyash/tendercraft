"""Free-text item description -> typed spec parameters. Extraction only.

Module H's single model component. It reads; `app/deterministic/spec_match.py` decides. The
separation is enforced at the schema (SPEC_PARAMS_SCHEMA carries no verdict field) rather than
at a router, because a router is one edit away from being changed and a missing field is not.

Never raises. A model failure yields an empty parameter list, which the comparator reports as
`unknown` on every parameter — "we could not read this line, please check it" — and never as a
deviation. G-5: never crash, never invent.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from pathlib import Path

from app.deterministic.spec_match import ParamValue
from app.deterministic.spec_params import ParamKind, spec_for

from .client import ModelError, generate_json
from .schemas import SPEC_PARAMS_SCHEMA

log = logging.getLogger("tendercraft.spec")

_PROMPT = (Path(__file__).resolve().parents[1] / "prompts" / "spec_extractor.md").read_text()

#: A GeM item description is a line, not a document. Anything longer is a pasted annexure and
#: truncating it costs nothing a parameter would have been in.
_MAX_DESCRIPTION = 2000


def _clamp01(value) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _number(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_param(row: dict) -> ParamValue | None:
    """One schema-valid row -> a comparable parameter, or None when it is not usable.

    The schema constrains shape, not sense: the model can still return a `numeric` with no
    bounds or an `enum` with no value, and both would compare as `unknown` forever while
    looking like data. Drop them here so the count the user sees is the count that can decide
    something.
    """
    key = str(row.get("param_key") or "")
    registered = spec_for(key)
    if registered is None:
        # Off-allowlist despite the enum. Belt and braces: an unregistered key has no canonical
        # unit and no label, so it would compare against nothing (G-6).
        log.warning("spec extractor returned unregistered param_key %r — dropped", key)
        return None

    raw_text = str(row.get("raw_text") or "")
    kind = ParamKind.NUMERIC if row.get("kind") == "numeric" else ParamKind.ENUM

    if kind is ParamKind.NUMERIC:
        low, high = _number(row.get("num_min")), _number(row.get("num_max"))
        if low is None and high is None:
            return None
        unit = row.get("unit") or None
        return ParamValue(key, kind, unit=unit, num_min=low, num_max=high, raw_text=raw_text)

    value = str(row.get("enum_value") or "").strip()
    if not value:
        return None
    return ParamValue(key, kind, allowed=frozenset({value}), raw_text=raw_text)


def parse_parameters(rows: Iterable[dict]) -> tuple[ParamValue, ...]:
    """Pure: schema-valid rows -> parameters. Separated from the call so it is testable without
    a model, which is the only way the drop rules above get covered."""
    seen: dict[str, ParamValue] = {}
    for row in rows:
        param = _to_param(row)
        # First mention wins. A description repeating "20mm ... 20 mm dia" must not produce two
        # rows for one key — the database refuses the second and the whole line item fails.
        if param is not None and param.key not in seen:
            seen[param.key] = param
    return tuple(seen.values())


def extract_parameters(description: str) -> tuple[ParamValue, ...]:
    """Read one item description. Returns () on any failure — never raises, never invents."""
    text = (description or "").strip()[:_MAX_DESCRIPTION]
    if not text:
        return ()
    try:
        result = generate_json(_PROMPT.replace("{{DESCRIPTION}}", text), SPEC_PARAMS_SCHEMA)
    except ModelError as exc:
        # The deterministic fallback is silence. Every parameter then reports `unknown`, the
        # line item asks for a human, and nothing is decided on a guess.
        log.warning("spec extraction failed, returning no parameters: %s", exc)
        return ()
    rows = result.get("parameters") if isinstance(result, dict) else None
    if not isinstance(rows, list):
        return ()
    return parse_parameters(row for row in rows if isinstance(row, dict))


def extract_many(descriptions: Sequence[str]) -> dict[str, tuple[ParamValue, ...]]:
    """Extract for a batch of DISTINCT descriptions, keyed by description.

    BOQs repeat rows heavily — the same rope at four consignee sites is four lines and one
    description. Deduping before the fan-out is the difference between 40 model calls and 6 on
    a real schedule.
    """
    unique = list(dict.fromkeys(d.strip() for d in descriptions if d and d.strip()))
    return {d: extract_parameters(d) for d in unique}
