"""evals/tender_response/metrics.py — the seven computable ARCHITECTURE §7 metrics, plus the
three corrupted-prediction controls the task brief requires (a/b/c) at the metrics layer.

Synthetic data throughout except the unsupported-material-fact-rate tests, which read the
committed fixture's page text (still synthetic, not customer data).
"""

from __future__ import annotations

from pathlib import Path

from evals.tender_response import golden, metrics
from evals.tender_response.match import match_requirements

FIXTURES = Path(__file__).parent.parent / "evals" / "tender_response" / "fixtures"


def _req(rid: str, page: int, text: str, mandatory=False, stage="bid", page_end=None,
         quote_fidelity="verbatim", source_excerpt=None, source_document="doc.pdf") -> dict:
    return {
        "requirement_id": rid, "page_number": page, "page_end": page_end,
        "requirement_text": text, "mandatory": mandatory, "submission_stage": stage,
        "quote_fidelity": quote_fidelity, "source_excerpt": source_excerpt,
        "source_document": source_document,
    }


class TestMandatoryRequirementRecall:
    def test_none_when_no_mandatory_bid_stage_rows(self):
        golds = [_req("G1", 1, "optional note", mandatory=False)]
        m = match_requirements(golds, golds)
        assert metrics.mandatory_requirement_recall(golds, m) is None

    def test_perfect_when_all_mandatory_rows_matched(self):
        golds = [_req(f"G{i}", i, f"unique mandatory clause number {i} text", mandatory=True)
                 for i in range(1, 6)]
        m = match_requirements(golds, golds)
        assert metrics.mandatory_requirement_recall(golds, m) == 1.0

    def test_corrupted_control_a_drop_every_10th_mandatory_row(self):
        # control (a): drop every 10th mandatory row -> recall ~= 0.90. Assert the drop landed
        # first, then assert the metric reflects it.
        golds = [_req(f"G{i}", i, f"unique mandatory clause number {i} filler text here",
                      mandatory=True) for i in range(1, 21)]  # 20 mandatory bid-stage rows
        dropped_ids = {g["requirement_id"] for i, g in enumerate(golds, start=1) if i % 10 == 0}
        assert dropped_ids == {"G10", "G20"}  # the drop landed: exactly 2 of 20
        preds = [g for i, g in enumerate(golds, start=1) if i % 10 != 0]
        assert len(preds) == 18

        m = match_requirements(golds, preds)
        recall = metrics.mandatory_requirement_recall(golds, m)
        assert recall == 0.90


class TestRequirementRecallPrecision:
    def test_empty_golden_is_perfect_recall(self):
        assert metrics.requirement_recall([], match_requirements([], [])) == 1.0

    def test_empty_predictions_is_perfect_precision_trivially(self):
        assert metrics.requirement_precision([], match_requirements([], [])) == 1.0

    def test_hallucinated_predictions_cost_precision_not_recall(self):
        golds = [_req("G1", 1, "a real requirement about factory licence validity")]
        preds = [golds[0], _req("P2", 9, "an entirely invented requirement about nothing real")]
        m = match_requirements(golds, preds)
        assert metrics.requirement_recall(golds, m) == 1.0
        assert metrics.requirement_precision(preds, m) == 0.5


class TestSubmissionDocumentRecall:
    def test_recall_by_normalized_type_ignores_non_recallable_origins(self):
        gold_docs = [
            {"document_type": "GST Certificate", "origin": "Usha Martin reusable company evidence"},
            {"document_type": "Award Letter", "origin": "Buyer supplied"},  # excluded from denom
        ]
        pred_docs = [{"document_type": "gst certificate"}]
        assert metrics.submission_document_recall(gold_docs, pred_docs) == 1.0

    def test_none_when_golden_has_no_recallable_documents(self):
        gold_docs = [{"document_type": "Award Letter", "origin": "Buyer supplied"}]
        assert metrics.submission_document_recall(gold_docs, []) is None

    def test_missing_type_in_prediction_costs_recall(self):
        gold_docs = [
            {"document_type": "GST Certificate", "origin": "Usha Martin generated"},
            {"document_type": "PAN Card", "origin": "Usha Martin generated"},
        ]
        pred_docs = [{"document_type": "GST Certificate"}]
        assert metrics.submission_document_recall(gold_docs, pred_docs) == 0.5


class TestEvidenceMappingAccuracy:
    def test_both_empty_counts_as_correct_abstention(self):
        text = "declaration of no banning or de-listing under any government authority"
        gold_map = [{"requirement_id": "G1", "evidence_documents": []}]
        pred_map = [{"requirement_id": "P1", "evidence_documents": []}]
        m = match_requirements([_req("G1", 1, text)], [_req("P1", 1, text)])
        assert metrics.evidence_mapping_accuracy(gold_map, pred_map, m) == 1.0

    def test_partial_overlap_is_jaccard(self):
        text = "declaration of no banning or de-listing under any government authority"
        gold_map = [{"requirement_id": "G1", "evidence_documents": ["EV-1", "EV-2"]}]
        pred_map = [{"requirement_id": "P1", "evidence_documents": ["EV-2", "EV-3"]}]
        m = match_requirements([_req("G1", 1, text)], [_req("P1", 1, text)])
        # intersection {EV-2} / union {EV-1,EV-2,EV-3} = 1/3
        assert metrics.evidence_mapping_accuracy(gold_map, pred_map, m) == 1 / 3

    def test_none_when_nothing_matched(self):
        m = match_requirements([_req("G1", 1, "alpha beta gamma delta")],
                                [_req("P1", 9, "completely different unrelated words")])
        assert metrics.evidence_mapping_accuracy([], [], m) is None


class TestMissingInformationRecall:
    def test_hit_when_matched_prediction_carries_a_missing_info_status(self):
        golds = [_req("G1", 1, "EMD payment instrument required with the bid")]
        preds = golds
        m = match_requirements(golds, preds)
        pred_map = [{"requirement_id": "G1", "status": "NOT_FOUND_IN_ARCHIVE"}]
        occ = [{"requirement_id": "G1", "tender_slug": "T"}]
        assert metrics.missing_information_recall(occ, pred_map, m) == 1.0

    def test_unmatched_golden_requirement_counts_as_a_miss(self):
        golds = [_req("G1", 1, "EMD payment instrument required with the bid")]
        preds = [_req("P1", 9, "something with absolutely no shared vocabulary at all")]
        m = match_requirements(golds, preds)
        occ = [{"requirement_id": "G1", "tender_slug": "T"}]
        assert metrics.missing_information_recall(occ, [], m) == 0.0

    def test_none_when_tender_has_no_information_request_occurrences(self):
        assert metrics.missing_information_recall([], [], match_requirements([], [])) is None


class TestUnsupportedMaterialFactRate:
    def test_golden_vs_golden_on_fixture_is_fully_supported(self):
        reqs = golden.load_tender(FIXTURES, "FIX_DEMO_001").requirements
        result = metrics.unsupported_material_fact_rate(FIXTURES, "FIX_DEMO_001", reqs)
        assert result.numbers_checked > 0
        assert result.numbers_unsupported == 0
        assert result.rate == 0.0

    def test_fabricated_number_is_caught(self):
        reqs = golden.load_tender(FIXTURES, "FIX_DEMO_001").requirements
        tampered = [dict(r) for r in reqs]
        # EMD row: swap the real 50000 for a number never on that page.
        tampered[0] = dict(tampered[0],
                            requirement_text="Earnest Money Deposit of Rs 999999999 shall be submitted with the bid.")
        result = metrics.unsupported_material_fact_rate(FIXTURES, "FIX_DEMO_001", tampered)
        assert result.numbers_unsupported >= 1
        assert result.rate > 0.0

    def test_no_numbers_in_any_requirement_yields_none(self):
        reqs = [_req("G1", 1, "no digits anywhere in this clause at all",
                      source_document="BID DOC/bid.pdf")]
        result = metrics.unsupported_material_fact_rate(FIXTURES, "FIX_DEMO_001", reqs)
        assert result.numbers_checked == 0
        assert result.rate is None

    def test_summary_rows_are_checked_against_source_excerpt_not_requirement_text(self):
        # the "16-09-2020" / "50" numbers live in source_excerpt for FIX-REQ-003, and ONLY
        # there — requirement_text for that row has no numbers at all.
        reqs = golden.load_tender(FIXTURES, "FIX_DEMO_001").requirements
        summary_row = next(r for r in reqs if r["quote_fidelity"] == "summary")
        result = metrics.unsupported_material_fact_rate(FIXTURES, "FIX_DEMO_001", [summary_row])
        assert result.numbers_checked > 0
        assert result.numbers_unsupported == 0


class TestNotMeasuredStubs:
    def test_template_and_copy_forward_are_none_not_a_fake_number(self):
        t = metrics.TenderMetrics(
            slug="x", n_golden_requirements=0, n_predicted_requirements=0,
            n_unmatched_golden=0, n_unmatched_predicted=0,
            mandatory_requirement_recall=None, requirement_recall=1.0,
            requirement_precision=1.0, submission_document_recall=None,
            evidence_mapping_accuracy=None, missing_information_recall=None,
            unsupported_material_fact_rate=None,
        )
        assert t.template_selection_accuracy is None
        assert t.copy_forward_detection is None
        assert "template_selection_accuracy" not in metrics.AVERAGED_FIELDS
        assert "copy_forward_detection" not in metrics.AVERAGED_FIELDS


def test_compute_tender_metrics_end_to_end_on_fixture():
    gold = golden.load_tender(FIXTURES, "FIX_DEMO_001")
    shared = golden.load_shared(FIXTURES)
    m = metrics.compute_tender_metrics(FIXTURES, gold, gold, shared)  # golden-vs-golden
    assert m.mandatory_requirement_recall == 1.0
    assert m.requirement_recall == 1.0
    assert m.requirement_precision == 1.0
    assert m.submission_document_recall == 1.0
    assert m.evidence_mapping_accuracy == 1.0
    assert m.missing_information_recall == 1.0
    assert m.unsupported_material_fact_rate == 0.0


def test_aggregate_skips_none_rather_than_treating_as_zero():
    m1 = metrics.TenderMetrics(
        slug="a", n_golden_requirements=1, n_predicted_requirements=1,
        n_unmatched_golden=0, n_unmatched_predicted=0,
        mandatory_requirement_recall=None, requirement_recall=1.0, requirement_precision=1.0,
        submission_document_recall=None, evidence_mapping_accuracy=None,
        missing_information_recall=None, unsupported_material_fact_rate=None,
    )
    m2 = metrics.TenderMetrics(
        slug="b", n_golden_requirements=1, n_predicted_requirements=1,
        n_unmatched_golden=0, n_unmatched_predicted=0,
        mandatory_requirement_recall=0.5, requirement_recall=0.5, requirement_precision=0.5,
        submission_document_recall=0.5, evidence_mapping_accuracy=0.5,
        missing_information_recall=0.5, unsupported_material_fact_rate=0.5,
    )
    agg = metrics.aggregate([m1, m2])
    # mandatory_requirement_recall: only m2 is defined -> average is 0.5, not 0.25
    assert agg["mandatory_requirement_recall"] == 0.5
    assert agg["requirement_recall"] == 0.75
