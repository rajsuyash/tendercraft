"""Eval runner: load golden cases -> call the component -> score -> report.

Usage: uv run python -m evals.run attribution

Ported by COPY from the bidder engine's evals/run.py. Not imported: the F13 wall forbids a
shared module between the two products and tools/check-wall.sh fails the build on a stray
`from app…`. Duplication is the cheaper failure here.

Never edit a case, a label, or a threshold to make a run pass. Thresholds change by human PRD
edit only — an eval you can tune until it is green measures nothing.

Components not yet implemented report NOT_IMPLEMENTED and exit 2. That is the scaffold working:
the harness is provable on day one, before the component it will score exists.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# component -> (milestone that builds it, dotted module path it will live at)
COMPONENTS: dict[str, tuple[str, str]] = {
    "attribution": ("N1", "evaluate.pipeline.attributor"),
    "ocr": ("N1", "evaluate.pipeline.ocr"),
    "offers": ("N3", "evaluate.pipeline.offer_extractor"),
    "clause": ("N4", "evaluate.pipeline.clause_drafter"),
    "debrief": ("N5", "evaluate.pipeline.debriefer"),
}


def load_cases(component: str) -> list[dict]:
    path = Path(__file__).parent / component / "cases.jsonl"
    if not path.exists():
        sys.exit(f"NO GOLDEN SET at {path} — write cases before scoring {component}")
    cases: list[dict] = []
    for i, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("//"):
            continue
        try:
            cases.append(json.loads(line))
        except json.JSONDecodeError as e:
            sys.exit(f"MALFORMED golden case {path}:{i} — {e}")
    return cases


def resolve(component: str):
    """Import the component, or explain which milestone builds it."""
    milestone, dotted = COMPONENTS[component]
    try:
        module = __import__(dotted, fromlist=["_"])
    except ImportError:
        print(f"NOT_IMPLEMENTED: {component} — built in milestone {milestone} ({dotted})")
        print("The harness is wired and the golden set loads. Nothing to score yet.")
        sys.exit(2)
    return module


def report(component: str, results: list[dict]) -> int:
    total = len(results)
    passed = sum(1 for r in results if r["pass"])
    print(f"\n{component}: {passed}/{total} cases passed")
    for r in results:
        if not r["pass"]:
            print(f"  FAIL {r['id']}: {r.get('why', '')}")

    starters = sum(1 for r in results if r.get("starter"))
    if starters:
        print(
            f"\n{starters} of {total} cases are marked \"starter\": true — these are seeds, not a "
            "release gate. Expand from real tender documents before trusting the score."
        )
    return 0 if passed == total else 1


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in COMPONENTS:
        sys.exit(f"usage: python -m evals.run <{'|'.join(COMPONENTS)}>")

    component = sys.argv[1]
    cases = load_cases(component)
    print(f"{component}: {len(cases)} golden cases loaded")

    module = resolve(component)  # exits 2 with a named milestone if not built yet
    score = getattr(module, "score_eval_case", None)
    if score is None:
        sys.exit(
            f"{component} exists but exposes no score_eval_case(case) -> (bool, str). "
            "The component owns its scoring: only it knows what its fields mean."
        )

    results = []
    for case in cases:
        ok, why = score(case)
        results.append({"id": case["id"], "pass": ok, "why": why, "starter": case.get("starter")})
    return report(component, results)


if __name__ == "__main__":
    raise SystemExit(main())
