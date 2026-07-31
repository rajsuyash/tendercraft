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

COMPONENTS = ("extractor", "drafter", "drafter-fr", "relevance")


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


def score_drafter_fr() -> int:
    """The commercial gate for the French market.

    "It produced French" is not the bar. A French bid is only worth anything if the rules that
    make the English one trustworthy still hold in French — so this asserts the SAME properties
    as the English drafter set, plus the language:

      * no authored money figure (B-FR3). The scanner reads sentence TEXT, and "2 000 000 EUR"
        is as much a hard block as "₹8.2 Cr"; a French draft must state compliance and cite.
      * cite-or-flag (B-FR1). Evidence that proves nothing must placeholder, not pad — fluent
        French is exactly the failure mode that makes an unsupported claim look supported.
      * model failure still yields a placeholder, never invention.
    """
    from pipeline import drafter as dr

    cases = load_cases("drafter-fr")
    normal = [c for c in cases if not c.get("inject")]
    inject = [c for c in cases if c.get("inject")]

    passed = 0
    print("\n== Drafter FR golden set (live) ==")
    for c in normal:
        r = dr.draft_response(c["input"]["criterion"], c["input"]["chunks"], "fr")
        checks = _check_draft(r, c["expected"])
        text = " ".join(str(s.get("text", "")) for s in r.sentences).lower()
        # Language check without a detector dependency: these are short compliance sentences,
        # which most detectors are unreliable on. French function words and accents are enough.
        checks["language"] = (
            True
            if r.draft_status == "placeholder" and not text.strip()
            else any(w in text for w in (" le ", " la ", " les ", " des ", " du ", " est ",
                                         " et ", " aux ", " par ", " candidat"))
            or any(ch in text for ch in "éèêàçôûî")
        )
        ok = all(checks.values())
        passed += ok
        failed = [k for k, v in checks.items() if not v]
        print(f"  {c['id']:16} {'PASS' if ok else 'FAIL'}  status={r.draft_status} "
              f"flags={len(r.flags)}" + (f"  missed={failed}" if failed else ""))

    print("\n== Fault injection (fallback) ==")
    inject_passed = 0
    orig = dr.generate_json
    for c in inject:
        dr.generate_json = _raise  # type: ignore[assignment]
        ok = False
        try:
            r = dr.draft_response(c["input"]["criterion"], c["input"]["chunks"], "fr")
            ok = r.draft_status == "placeholder"
        except Exception:  # noqa: BLE001 — a crash is exactly the failure we test against
            ok = False
        finally:
            dr.generate_json = orig  # type: ignore[assignment]
        inject_passed += ok
        print(f"  {c['id']:16} {'PASS' if ok else 'FAIL'}  ({c['inject']} -> placeholder)")

    total, total_pass = len(normal) + len(inject), passed + inject_passed
    print(f"\nSUMMARY: {total_pass}/{total} cases pass "
          f"(normal {passed}/{len(normal)}, injection {inject_passed}/{len(inject)})")
    print("NOTE: this is the gate on selling the product in French. A pass means the money and "
          "cite-or-flag rules survive the language change, not that the prose is idiomatic — "
          "that still needs a French procurement reader.")
    return 0 if total_pass == total else 1


def _raise(*_a, **_k):
    from pipeline.client import ModelError

    raise ModelError("injected failure")


def score_relevance() -> int:
    """F-FR11 — the fit band.

    Two properties matter more than accuracy here, and both are pass/fail rather than a
    percentage:

      * **A band cannot hide a tender.** The model output never reaches the gate, so a wrong
        band costs one badly-ordered row. That is asserted structurally in
        tests/test_discovery_rules.py; this suite checks the band itself is sane.
      * **Cite or demote.** A non-low band with no `matched_capability` is dropped to low by
        pipeline/relevance.py — the same cite-or-flag rule the drafter follows (G-5).
    """
    from app.discovery import relevance as orchestrator
    from pipeline import relevance as rel

    cases = load_cases("relevance")
    normal = [c for c in cases if not c.get("inject")]
    inject = [c for c in cases if c.get("inject")]

    passed = 0
    print("\n== Relevance golden set (live) ==")
    for c in normal:
        i = c["input"]
        lang = c.get("language", "en")
        results = rel.score(i["capability_statement"], i["keywords"], i["tenders"], lang)
        r = results.get("t1")
        if r is None:
            print(f"  {c['id']:14} FAIL  (no band returned)")
            continue
        band_ok = r.band in c["expected"]["band_in"]
        # A French workspace must get French commentary. Checked with accented characters and
        # common French function words rather than a language-detection dependency: the
        # rationale is one sentence, which is too short for most detectors to be reliable on.
        lang_ok = True
        if c["expected"].get("language") == "fr":
            text = f"{r.rationale} {r.matched_capability}".lower()
            lang_ok = any(w in text for w in (
                " de ", " des ", " votre ", " vos ", " qui ", " est ", " pour ", " la ", " le ",
            )) or any(ch in text for ch in "éèêàçôû")
        # A cited band must actually carry its citation; an uncited one must have been demoted.
        cite_ok = bool(r.matched_capability) if c["expected"]["must_cite"] else True
        ok = band_ok and cite_ok and lang_ok
        passed += ok
        print(f"  {c['id']:14} {'PASS' if ok else 'FAIL'}  band={r.band:6} "
              f"conf={r.confidence:.2f} cited={'y' if r.matched_capability else 'n'} "
              f"lang={'ok' if lang_ok else 'WRONG'}"
              + ("" if ok else f"  expected={c['expected']['band_in']}"))

    # Fault injection: the model failing must degrade to deterministic keyword banding, visibly.
    print("\n== Fault injection (deterministic fallback) ==")
    inject_passed = 0
    orig = rel.generate_json
    for c in inject:
        rel.generate_json = _raise  # type: ignore[assignment]
        ok = False
        try:
            i = c["input"]
            patches = orchestrator.bands_for(
                [{**t, "category_codes": t["categories"].split(",")} for t in i["tenders"]],
                capability_statement=i["capability_statement"],
                keywords=i["keywords"],
            )
            patch = patches.get("t1", {})
            ok = (
                patch.get("relevance_source") == c["expected"]["fallback"]
                and patch.get("relevance_band") in c["expected"]["band_in"]
            )
        except Exception:  # noqa: BLE001 — a crash is exactly the failure we test against
            ok = False
        finally:
            rel.generate_json = orig  # type: ignore[assignment]
        inject_passed += ok
        print(f"  {c['id']:14} {'PASS' if ok else 'FAIL'}  ({c['inject']} -> keyword fallback)")

    total, total_pass = len(normal) + len(inject), passed + inject_passed
    print(f"\nSUMMARY: {total_pass}/{total} cases pass "
          f"(normal {passed}/{len(normal)}, injection {inject_passed}/{len(inject)})")
    print("NOTE: starter set. It pins the adversarial cases the live feed actually produced "
          "(adhesive gum, KRAZ TUBE INNER, a keyword collision, and a prompt-injection title), "
          "not release-grade accuracy.")
    return 0 if total_pass == total else 1


_SCORERS = {
    "extractor": score_extractor,
    "drafter": score_drafter,
    "relevance": score_relevance,
    "drafter-fr": score_drafter_fr,
}


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in COMPONENTS:
        sys.exit(f"usage: python -m evals.run <{'|'.join(COMPONENTS)}>")
    if not os.environ.get("GEMINI_API_KEY"):
        sys.exit("GEMINI_API_KEY not set — cannot run live evals")
    sys.exit(_SCORERS[sys.argv[1]]())


if __name__ == "__main__":
    main()
