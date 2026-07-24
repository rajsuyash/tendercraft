"""Thin eval runner: load cases -> call component -> schema-validate -> score -> JSON report.

Usage: uv run python -m evals.run <component>   (components: extractor, eligibility-matcher)

Wire-up happens at M1/M2 when the pipeline components exist; until then this
validates the harness (cases parse, schema stubs load) and exits non-zero on
malformed cases so CI catches golden-set corruption early.

Rules (binding, see .claude/agents/eval-runner.md):
- never edit cases/thresholds to make a run pass
- fault-injection cases ("inject": ...) must exercise retry-cap-1 + deterministic fallback
- report schema-validity, per-field accuracy, p95 latency, cost per case
"""
import json
import sys
from pathlib import Path

# ponytail: harness-only until pipeline components exist (M1); real invocation slots in here
COMPONENTS = ("extractor", "eligibility-matcher")


def load_cases(component: str) -> list[dict]:
    path = Path(__file__).parent / component / "cases.jsonl"
    cases = []
    for i, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            cases.append(json.loads(line))
        except json.JSONDecodeError as e:
            sys.exit(f"MALFORMED golden case {path}:{i} — {e}")
    return cases


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in COMPONENTS:
        sys.exit(f"usage: python -m evals.run <{'|'.join(COMPONENTS)}>")
    component = sys.argv[1]
    cases = load_cases(component)
    starters = sum(1 for c in cases if c.get("starter"))
    injections = sum(1 for c in cases if c.get("inject"))
    print(json.dumps({
        "component": component,
        "cases": len(cases),
        "starter_cases": starters,
        "fault_injections": injections,
        "status": "harness-ok (pipeline not wired yet — see run.py TODO at M1)",
    }, indent=2))


if __name__ == "__main__":
    main()
