"""Score a pipeline's predicted tender-response output against the golden corpus.

Usage:
    uv run python -m evals.tender_response.run --pred <dir> [--tender <slug>]
    uv run python -m evals.tender_response.run --self-check [--tender <slug>]

`--pred <dir>` is a directory shaped exactly like $TC_GOLDEN_DIR itself: `requirements/<slug>
.json`, `submission_documents/<slug>.json`, `mapping/<slug>.json` — a pipeline's predictions,
not yet produced by anything in this repo (M-b/M-d/M-f are unbuilt), so for now predictions are
hand-built or golden-derived test fixtures in that same shape.

`--self-check` scores the golden set against itself (predictions = golden) — it must print 1.0
on every measured metric; see IMPLEMENTATION_PLAN.md §M-j's acceptance criteria.

No model calls anywhere in this module. $GEMINI_API_KEY is not read, let alone required.

This is intentionally its own entry point rather than a mode of evals/run.py's `_SCORERS`
dispatch: that dispatch takes a single component name, requires a live model key
unconditionally (`main()` hard-exits without `GEMINI_API_KEY`), and scores a component against
`cases.jsonl` fixtures baked into the repo. This harness scores a PREDICTION DIRECTORY against
golden customer data that is never in the repo, takes positional/flag arguments evals/run.py's
parser doesn't support, and must work with zero model calls — it does not fit that call shape,
so evals/run.py is left untouched (see the task brief's own "say so" clause).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import golden
from .metrics import TenderMetrics, aggregate, compute_tender_metrics


def _fmt(v: float | None) -> str:
    return "   —  " if v is None else f"{v:6.3f}"


def _run(gdir: Path, pred_dir: Path, tenders: list[str],
          shared: golden.SharedGolden) -> list[TenderMetrics]:
    results = []
    for slug in tenders:
        gold = golden.load_tender(gdir, slug)
        pred = golden.load_tender(pred_dir, slug)
        results.append(compute_tender_metrics(gdir, gold, pred, shared))
    return results


def _print_report(results: list[TenderMetrics]) -> None:
    total_reqs = sum(m.n_golden_requirements for m in results)
    print(f"tenders={len(results)} requirements={total_reqs}")
    print()
    print(f"{'slug':40} {'mand_rec':>8} {'req_rec':>8} {'req_prec':>8} {'doc_rec':>8} "
          f"{'ev_acc':>8} {'mip_rec':>8} {'unsup':>8}")
    for m in results:
        print(f"{m.slug:40} {_fmt(m.mandatory_requirement_recall):>8} "
              f"{_fmt(m.requirement_recall):>8} {_fmt(m.requirement_precision):>8} "
              f"{_fmt(m.submission_document_recall):>8} {_fmt(m.evidence_mapping_accuracy):>8} "
              f"{_fmt(m.missing_information_recall):>8} "
              f"{_fmt(m.unsupported_material_fact_rate):>8}")

    agg = aggregate(results)
    print()
    print("OVERALL (macro average across tenders where the metric is defined):")
    for k, v in agg.items():
        print(f"  {k:32} {_fmt(v)}")
    print()
    print("not measured (needs a component with no predictions to score yet):")
    print("  template_selection_accuracy    — needs M-f (template engine)")
    print("  copy_forward_detection         — needs M-g1 (copy-forward checks)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m evals.tender_response.run")
    ap.add_argument("--pred", type=Path, help="predicted-output directory, golden-shaped")
    ap.add_argument("--tender", help="restrict to one tender slug")
    ap.add_argument("--self-check", action="store_true",
                     help="golden-vs-golden: predictions ARE the golden set")
    args = ap.parse_args(argv)

    if not args.self_check and not args.pred:
        ap.error("one of --pred or --self-check is required")

    try:
        gdir = golden.golden_dir()
        shared = golden.load_shared(gdir)
        tenders = [args.tender] if args.tender else golden.list_tenders(gdir)
        if not tenders:
            print(f"ERROR: no tenders found under {gdir}/requirements/", file=sys.stderr)
            return 1
        pred_dir = gdir if args.self_check else args.pred
        results = _run(gdir, pred_dir, tenders, shared)
    except golden.GoldenError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    _print_report(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
