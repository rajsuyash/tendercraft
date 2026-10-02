"""The tender-response evaluation metrics (ARCHITECTURE.md §7).

Of the eight metrics in that table, this module computes the seven that are answerable from
golden-shaped predictions alone (requirements/submission_documents/mapping rows, no pipeline
code required to exist yet):

  mandatory_requirement_recall, requirement_recall, requirement_precision,
  submission_document_recall, evidence_mapping_accuracy, missing_information_recall,
  unsupported_material_fact_rate

Two are stubbed to `None` ("not measured") because they score a component that is not built
yet (IMPLEMENTATION_PLAN §M-j brief, and ARCHITECTURE §7 names both explicitly as deferrable):

  template_selection_accuracy — needs the template engine (M-f).
  copy_forward_detection      — needs the copy-forward checks (M-g1 / C01-C05, C14).

`None` is a real value here, never papered over with 0.0 or 1.0 — CLAUDE.md "measured vs.
inferred": a metric nothing computed must never masquerade as a measurement.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from . import golden
from .match import MatchResult, match_requirements

_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def _index_by_id(rows: list[dict], key: str) -> dict[str, dict]:
    return {r[key]: r for r in rows}


def mandatory_requirement_recall(golds: list[dict], match: MatchResult) -> float | None:
    """golden mandatory=true, submission_stage=bid rows matched by a prediction — ARCHITECTURE
    §7's exact filter."""
    mandatory = [g for g in golds
                 if g.get("mandatory") is True and g.get("submission_stage") == "bid"]
    if not mandatory:
        return None
    hit = sum(1 for g in mandatory if g["requirement_id"] in match.matched)
    return hit / len(mandatory)


def requirement_recall(golds: list[dict], match: MatchResult) -> float:
    if not golds:
        return 1.0
    return len(match.matched) / len(golds)


def requirement_precision(preds: list[dict], match: MatchResult) -> float:
    if not preds:
        return 1.0
    return len(match.matched) / len(preds)


def submission_document_recall(gold_docs: list[dict], pred_docs: list[dict]) -> float | None:
    """By normalised document_type, scoped to golden docs whose origin means "the UML side had
    to produce this" (golden.RECALLABLE_DOC_ORIGINS). Instance-level document ids never align
    between golden and a pipeline's own predicted ids, so this is deliberately a set-membership
    check at the document-type granularity, not a 1:1 document match."""
    gold_types = {
        golden.normalize_document_type(d["document_type"])
        for d in gold_docs if d.get("origin") in golden.RECALLABLE_DOC_ORIGINS
    }
    if not gold_types:
        return None
    pred_types = {golden.normalize_document_type(d["document_type"]) for d in pred_docs}
    return len(gold_types & pred_types) / len(gold_types)


def evidence_mapping_accuracy(gold_mapping: list[dict], pred_mapping: list[dict],
                               match: MatchResult) -> float | None:
    """Per matched requirement, Jaccard overlap of `evidence_documents` sets (golden's ids vs
    the predicted mapping row's ids for the MATCHED predicted requirement). A pair where both
    sides list no evidence scores 1.0 (correctly agreeing none is needed); a requirement with
    no predicted counterpart at all is NOT scored here — it already cost the pipeline a
    recall point, scoring it again as a 0 here would double-count the same miss."""
    gold_by_id = _index_by_id(gold_mapping, "requirement_id")
    pred_by_id = _index_by_id(pred_mapping, "requirement_id")
    scores = []
    for gold_id, pred_id in match.matched.items():
        g_ev = set(gold_by_id.get(gold_id, {}).get("evidence_documents", []) or [])
        p_ev = set(pred_by_id.get(pred_id, {}).get("evidence_documents", []) or [])
        if not g_ev and not p_ev:
            scores.append(1.0)
        else:
            scores.append(len(g_ev & p_ev) / len(g_ev | p_ev))
    if not scores:
        return None
    return sum(scores) / len(scores)


def missing_information_recall(mip_occurrences: list[dict], pred_mapping: list[dict],
                                match: MatchResult) -> float | None:
    """Golden `missing_information_patterns.json` occurrences of kind information_request
    (ARCHITECTURE §7) vs the predicted mapping status for the matched requirement. A golden
    occurrence the pipeline never even matched a requirement for counts as a miss — it did not
    just mis-flag the status, it never got that far."""
    if not mip_occurrences:
        return None
    pred_by_id = _index_by_id(pred_mapping, "requirement_id")
    hits = 0
    for occ in mip_occurrences:
        pred_id = match.matched.get(occ["requirement_id"])
        row = pred_by_id.get(pred_id) if pred_id else None
        if row is not None and row.get("status") in golden.MISSING_INFO_STATUSES:
            hits += 1
    return hits / len(mip_occurrences)


def _quote_text(req: dict) -> str:
    # Mirrors the reference checker (verify_tender.py): only "summary" rows substitute
    # source_excerpt. "condensed_table" text is cell-linearised with no added words (schema,
    # PHASE2_BRIEF §STEP 1), so it is checkable as-is; "summary" text is the analyst's own
    # words and only the excerpt is a real quote.
    if req.get("quote_fidelity") == "summary":
        return req.get("source_excerpt") or ""
    return req.get("requirement_text") or ""


@dataclass(frozen=True)
class UnsupportedFactResult:
    rate: float | None
    numbers_checked: int
    numbers_unsupported: int


def unsupported_material_fact_rate(gdir: Path, slug: str,
                                    pred_requirements: list[dict]) -> UnsupportedFactResult:
    """Ports verify_tender.py's idea — a cited quote's numbers must occur on its cited page
    range — as a check on PREDICTIONS, scoped to the resolved source-document directory
    (golden.page_text) rather than verify_tender.py's "any doc dir with that page number"
    looseness.

    Narrow by design, and documented rather than silently incomplete:
      * Only NUMERIC tokens are checked. A fabricated clause meaning with no numbers in it
        (e.g. an invented eligibility condition) is invisible to this metric.
      * "traceable to a golden fact" (the other half of the brief's definition) is NOT
        implemented: a predicted requirement carries no binding to a company_facts/evidence
        vault id to check against — that binding doesn't exist until the vault (M-c) is wired
        into predictions. Only the page-quote half ("traceable to ... a page quote") is
        checked here.
      * Silent wherever a requirement has no digits at all (returns no evidence either way for
        that row) — most Declaration/Statutory/Compliance rows carry none.
      * Inherits golden.candidate_dirs_for_document's resolution: usually a single correctly
        identified directory, but it can fall back to a union of several candidate directories
        when the source filename shares no distinguishing word with any directory name — see
        that function's docstring.
    """
    checked = 0
    unsupported = 0
    for req in pred_requirements:
        text = unicodedata.normalize("NFKC", _quote_text(req))
        numbers = set(_NUMBER_RE.findall(text))
        if not numbers:
            continue
        page_start = int(req["page_number"])
        page_end = req.get("page_end")
        page_text = golden.page_text(gdir, slug, req["source_document"], page_start,
                                      int(page_end) if page_end else None)
        found_numbers = set(_NUMBER_RE.findall(page_text))
        checked += len(numbers)
        unsupported += len(numbers - found_numbers)
    rate = (unsupported / checked) if checked else None
    return UnsupportedFactResult(rate, checked, unsupported)


@dataclass
class TenderMetrics:
    slug: str
    n_golden_requirements: int
    n_predicted_requirements: int
    n_unmatched_golden: int
    n_unmatched_predicted: int
    mandatory_requirement_recall: float | None
    requirement_recall: float
    requirement_precision: float
    submission_document_recall: float | None
    evidence_mapping_accuracy: float | None
    missing_information_recall: float | None
    unsupported_material_fact_rate: float | None
    unsupported_numbers_checked: int = 0
    template_selection_accuracy: None = field(default=None)  # not measured — needs M-f
    copy_forward_detection: None = field(default=None)  # not measured — needs M-g1


def compute_tender_metrics(gdir: Path, gold: golden.GoldenTender, pred: golden.GoldenTender,
                            shared: golden.SharedGolden) -> TenderMetrics:
    match = match_requirements(gold.requirements, pred.requirements)
    mip = golden.mip_occurrences_for_tender(shared, gold.slug)
    unsupported = unsupported_material_fact_rate(gdir, gold.slug, pred.requirements)
    return TenderMetrics(
        slug=gold.slug,
        n_golden_requirements=len(gold.requirements),
        n_predicted_requirements=len(pred.requirements),
        n_unmatched_golden=len(match.unmatched_gold),
        n_unmatched_predicted=len(match.unmatched_pred),
        mandatory_requirement_recall=mandatory_requirement_recall(gold.requirements, match),
        requirement_recall=requirement_recall(gold.requirements, match),
        requirement_precision=requirement_precision(pred.requirements, match),
        submission_document_recall=submission_document_recall(
            gold.submission_documents, pred.submission_documents),
        evidence_mapping_accuracy=evidence_mapping_accuracy(gold.mapping, pred.mapping, match),
        missing_information_recall=missing_information_recall(mip, pred.mapping, match),
        unsupported_material_fact_rate=unsupported.rate,
        unsupported_numbers_checked=unsupported.numbers_checked,
    )


# Field names averaged across tenders when printing an overall summary. template_selection_
# accuracy and copy_forward_detection are deliberately excluded — averaging a column of Nones
# would be meaningless, and the point of "not measured" is that no number appears for them.
AVERAGED_FIELDS = (
    "mandatory_requirement_recall",
    "requirement_recall",
    "requirement_precision",
    "submission_document_recall",
    "evidence_mapping_accuracy",
    "missing_information_recall",
    "unsupported_material_fact_rate",
)


def aggregate(per_tender: list[TenderMetrics]) -> dict[str, float | None]:
    """Macro average (one vote per tender) over tenders where the metric is defined (not
    None). A metric with zero defined tenders reports None rather than a division by zero or a
    fabricated 0.0."""
    out: dict[str, float | None] = {}
    for f in AVERAGED_FIELDS:
        values = [v for m in per_tender if (v := getattr(m, f)) is not None]
        out[f] = (sum(values) / len(values)) if values else None
    return out
