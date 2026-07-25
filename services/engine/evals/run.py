"""Eval runner: load golden cases -> call the component -> score -> report.

Usage: uv run python -m evals.run extractor

Scores the Extractor against evals/extractor/cases.jsonl using live Gemini. Fault-injection
cases ("inject") verify the deterministic fallback fires (empty result, no crash, no
invention). Never edit cases/thresholds to make a run pass — thresholds are human PRD edits.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

COMPONENTS = ("extractor", "drafter")


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


def _check_case(crits, expected: dict) -> dict[str, bool]:
    checks: dict[str, bool] = {"count": len(crits) == expected["count"]}
    if expected["count"] > 0 and crits:
        first = crits[0]
        if "category" in expected:
            checks["category"] = first.category == expected["category"]
        if "requirement_level" in expected:
            checks["req_level"] = first.requirement_level == expected["requirement_level"]
        if "anchor_clause" in expected:
            checks["anchor"] = expected["anchor_clause"] in first.anchor_clause
        if "verbatim_contains" in expected:
            needle = expected["verbatim_contains"].lower()
            checks["verbatim"] = needle in first.verbatim_text.lower()
    return checks


def score_extractor() -> int:
    from pipeline import extractor as ex

    cases = load_cases("extractor")
    normal = [c for c in cases if not c.get("inject")]
    inject = [c for c in cases if c.get("inject")]

    passed = 0
    print("\n== Extractor golden set (live) ==")
    for c in normal:
        crits = ex.extract_from_page(c["input"]["text"], c["input"]["page"])
        checks = _check_case(crits, c["expected"])
        ok = all(checks.values())
        passed += ok
        failed = [k for k, v in checks.items() if not v]
        print(f"  {c['id']:10} {'PASS' if ok else 'FAIL'}  extracted={len(crits)}"
              + (f"  missed={failed}" if failed else ""))

    # Fault injection: model failure must yield [] (fallback), never a crash or invention.
    print("\n== Fault injection (fallback) ==")
    inject_passed = 0
    orig = ex.generate_json
    for c in inject:
        ex.generate_json = _raise  # type: ignore[assignment]
        try:
            crits = ex.extract_from_page(c["input"]["text"], c["input"]["page"])
            ok = crits == []
        except Exception:  # noqa: BLE001 — a crash is exactly the failure we test against
            ok = False
        finally:
            ex.generate_json = orig  # type: ignore[assignment]
        inject_passed += ok
        print(f"  {c['id']:10} {'PASS' if ok else 'FAIL'}  ({c['inject']} -> fallback)")

    total = len(normal) + len(inject)
    total_pass = passed + inject_passed
    print(f"\nSUMMARY: {total_pass}/{total} cases pass "
          f"(normal {passed}/{len(normal)}, injection {inject_passed}/{len(inject)})")
    print("NOTE: starter set proves the harness + fallback, not release-grade accuracy "
          "(gold set is the PRD §6 corpus). Thresholds A-AC1/A-AC2 gate at that scale.")
    return 0 if total_pass == total else 1


def _check_draft(r, expected: dict) -> dict[str, bool]:
    checks: dict[str, bool] = {}
    if "draft_status" in expected:
        checks["status"] = r.draft_status == expected["draft_status"]
    if expected.get("no_uncited_financial"):
        # B-AC4: an evidence-backed draft must not author a figure (hard flag).
        checks["no_uncited_fin"] = all(f["reason"] != "uncited_financial" for f in r.flags)
    if "cited" in expected:
        has_cite = any(s.get("citations") for s in r.sentences)
        checks["cited"] = has_cite == expected["cited"]
    return checks


def score_drafter() -> int:
    from pipeline import drafter as dr

    cases = load_cases("drafter")
    normal = [c for c in cases if not c.get("inject")]
    inject = [c for c in cases if c.get("inject")]

    passed = 0
    print("\n== Drafter golden set (live) ==")
    for c in normal:
        r = dr.draft_response(c["input"]["criterion"], c["input"]["chunks"])
        checks = _check_draft(r, c["expected"])
        ok = all(checks.values())
        passed += ok
        failed = [k for k, v in checks.items() if not v]
        print(f"  {c['id']:10} {'PASS' if ok else 'FAIL'}  status={r.draft_status} "
              f"flags={len(r.flags)}" + (f"  missed={failed}" if failed else ""))

    # Fault injection: model failure must yield a placeholder, never a crash or invention.
    print("\n== Fault injection (fallback) ==")
    inject_passed = 0
    orig = dr.generate_json
    for c in inject:
        dr.generate_json = _raise  # type: ignore[assignment]
        ok = False
        try:
            r = dr.draft_response(c["input"]["criterion"], c["input"]["chunks"])
            ok = r.draft_status == "placeholder"
        except Exception:  # noqa: BLE001 — a crash is exactly the failure we test against
            ok = False
        finally:
            dr.generate_json = orig  # type: ignore[assignment]
        inject_passed += ok
        print(f"  {c['id']:10} {'PASS' if ok else 'FAIL'}  ({c['inject']} -> fallback)")

    total = len(normal) + len(inject)
    total_pass = passed + inject_passed
    print(f"\nSUMMARY: {total_pass}/{total} cases pass "
          f"(normal {passed}/{len(normal)}, injection {inject_passed}/{len(inject)})")
    print("NOTE: starter set proves the harness + the B-AC4/B-FR3 no-authored-figure property, "
          "not release-grade quality (gold set is the PRD §6 corpus).")
    return 0 if total_pass == total else 1


def _raise(*_a, **_k):
    from pipeline.client import ModelError

    raise ModelError("injected failure")


_SCORERS = {"extractor": score_extractor, "drafter": score_drafter}


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in COMPONENTS:
        sys.exit(f"usage: python -m evals.run <{'|'.join(COMPONENTS)}>")
    if not os.environ.get("GEMINI_API_KEY"):
        sys.exit("GEMINI_API_KEY not set — cannot run live evals")
    sys.exit(_SCORERS[sys.argv[1]]())


if __name__ == "__main__":
    main()
