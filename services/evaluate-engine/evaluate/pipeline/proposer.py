"""Score proposal (F7). The model PROPOSES; a named human decides.

Two rules that are not negotiable:
  1. The proposal is only ever computed AFTER the evaluator committed their own mark — the
     route enforces that, this module never sees a request that skipped it.
  2. On any failure the fallback is NO PROPOSAL. A guessed mark on a public tender is worse
     than no assistance at all.
"""

from __future__ import annotations

from pathlib import Path

from .client import ModelError, generate_json

_PROMPT = Path(__file__).resolve().parents[2] / "prompts" / "score_proposal.md"

_SCHEMA = {
    "type": "object",
    "properties": {
        "proposed_marks": {"type": "number"},
        "reasoning": {"type": "string"},
    },
    "required": ["proposed_marks", "reasoning"],
}


def propose(criterion: dict, response: dict | None) -> dict:
    """Returns {proposed_marks, reasoning, available} — `available: False` when the model
    could not be reached or returned something outside the criterion's range."""
    max_marks = criterion.get("max_marks") or 0
    evidence = (response or {}).get("excerpt") or (response or {}).get("stated_value") or ""
    if not evidence:
        return {"available": False,
                "reason": "no extracted evidence for this criterion in this bid"}
    try:
        tmpl = _PROMPT.read_text()
    except OSError:
        return {"available": False, "reason": "prompt unavailable"}

    prompt = (tmpl.replace("{{CRITERION}}", criterion.get("text", ""))
                  .replace("{{MAX_MARKS}}", str(max_marks))
                  .replace("{{EVIDENCE}}", evidence[:6000]))
    try:
        out = generate_json(prompt, _SCHEMA)
    except ModelError as exc:
        return {"available": False, "reason": f"model unavailable: {exc}"}

    mark = out.get("proposed_marks")
    if not isinstance(mark, int | float) or not (0 <= mark <= max_marks):
        # Out of range is a schema failure in substance. Refuse rather than clamp — clamping
        # would silently invent a defensible-looking number.
        return {"available": False, "reason": "model returned a mark outside the valid range"}
    return {"available": True, "proposed_marks": round(float(mark), 2),
            "reasoning": str(out.get("reasoning", ""))[:2000],
            "anchor_page": (response or {}).get("anchor_page")}
