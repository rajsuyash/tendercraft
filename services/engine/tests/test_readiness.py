"""Bid-readiness P0/P1/P2 priority mapping."""

from app.deterministic.readiness import compute_readiness


def _crit(cid, level="mandatory", conf=0.95, confirmed=True, page=12, clause="4.1(a)"):
    return {
        "id": cid,
        "verbatim_text": f"criterion {cid}",
        "requirement_level": level,
        "confidence": conf,
        "confirmed": confirmed,
        "anchor_page": page,
        "anchor_clause": clause,
    }


def _analysis(*verdicts):
    return {"verdicts": list(verdicts)}


def _v(cid, verdict, exempted=False, gap=""):
    return {
        "criterion_id": cid,
        "verdict": verdict,
        "exemption_granted": exempted,
        "gap_note": gap,
        "rationale": "because",
        "source_anchor": "p.12 · Cl. 4.1(a)",
    }


def _resp(cid, status):
    return {"criterion_id": cid, "draft_status": status}


def _priority(result, cid):
    return next(i["priority"] for i in result["items"] if i["criterion_id"] == cid)


def test_unconfirmed_low_confidence_is_confirm_first():
    r = compute_readiness([_crit("a", conf=0.6, confirmed=False)], None, [])
    assert _priority(r, "a") == "confirm"
    assert r["summary"]["confirm_open"] == 1
    assert r["summary"]["ready_to_generate"] is False


def test_mandatory_fail_is_p0():
    r = compute_readiness([_crit("a")], _analysis(_v("a", "fail", gap="₹1.8 Cr short")), [_resp("a", "placeholder")])
    assert _priority(r, "a") == "p0"


def test_eligible_but_undrafted_is_p1_not_blocking():
    # Passes eligibility (deterministic) but the drafter left a placeholder -> a proposal-
    # completion task, NOT a blocking P0. The export gate enforces "no placeholder" at export.
    r = compute_readiness([_crit("a")], _analysis(_v("a", "pass")), [_resp("a", "placeholder")])
    assert _priority(r, "a") == "p1"
    assert r["summary"]["p0_blocking"] == 0
    assert r["summary"]["ready_to_generate"] is True


def test_no_verdict_undrafted_is_p0():
    # Before analysis runs there's no verdict — stay conservative and block until matched.
    r = compute_readiness([_crit("a")], _analysis(), [_resp("a", "placeholder")])
    assert _priority(r, "a") == "p0"


def test_exempted_fail_is_not_p0():
    # a waived mandatory fail with a clean draft is covered, not blocking
    r = compute_readiness([_crit("a")], _analysis(_v("a", "fail", exempted=True)), [_resp("a", "drafted")])
    assert _priority(r, "a") == "covered"


def test_mandatory_needs_review_is_p1():
    r = compute_readiness([_crit("a")], _analysis(_v("a", "needs_review")), [_resp("a", "drafted")])
    assert _priority(r, "a") == "p1"


def test_unverified_draft_is_p1():
    r = compute_readiness([_crit("a")], _analysis(_v("a", "pass")), [_resp("a", "unverified")])
    assert _priority(r, "a") == "p1"


def test_mandatory_pass_drafted_is_covered():
    r = compute_readiness([_crit("a")], _analysis(_v("a", "pass")), [_resp("a", "drafted")])
    assert _priority(r, "a") == "covered"
    assert r["summary"]["ready_to_generate"] is True


def test_desirable_uncovered_is_p2():
    r = compute_readiness([_crit("d", level="desirable")], _analysis(_v("d", "fail")), [_resp("d", "placeholder")])
    assert _priority(r, "d") == "p2"


def test_desirable_covered_is_covered():
    r = compute_readiness([_crit("d", level="desirable")], _analysis(_v("d", "pass")), [_resp("d", "drafted")])
    assert _priority(r, "d") == "covered"


def test_items_sorted_confirm_p0_p1_p2_covered():
    criteria = [
        _crit("cov"),
        _crit("p2", level="desirable"),
        _crit("cf", conf=0.5, confirmed=False),
        _crit("p0"),
        _crit("p1"),
    ]
    analysis = _analysis(
        _v("cov", "pass"), _v("p2", "fail"), _v("p0", "fail"), _v("p1", "needs_review")
    )
    responses = [
        _resp("cov", "drafted"), _resp("p2", "placeholder"),
        _resp("p0", "placeholder"), _resp("p1", "drafted"),
    ]
    order = [i["priority"] for i in compute_readiness(criteria, analysis, responses)["items"]]
    assert order == ["confirm", "p0", "p1", "p2", "covered"]


def test_no_analysis_yet_mandatory_reads_as_p0():
    # before "Analyze & match": a confirmed mandatory with no analysis/draft needs work
    r = compute_readiness([_crit("a")], None, [])
    assert _priority(r, "a") == "p0"


def test_missing_anchor_reads_no_anchor():
    c = _crit("a", page=None, clause=None)
    r = compute_readiness([c], _analysis(_v("a", "pass")), [_resp("a", "drafted")])
    # verdict provides a source_anchor; drop it so the fallback path is exercised
    r2 = compute_readiness([c], {"verdicts": [{"criterion_id": "a", "verdict": "pass"}]}, [_resp("a", "drafted")])
    item = next(i for i in r2["items"] if i["criterion_id"] == "a")
    assert item["source_anchor"] == "no anchor"
    assert r["items"]  # sanity


def test_summary_counts_and_ready_flag():
    criteria = [_crit("a"), _crit("b")]
    r = compute_readiness(criteria, _analysis(_v("a", "pass"), _v("b", "pass")),
                          [_resp("a", "drafted"), _resp("b", "drafted")])
    assert r["summary"]["covered"] == 2
    assert r["summary"]["p0_open"] == 0
    assert r["summary"]["ready_to_generate"] is True


# ---------- per-item decisions ----------
def _dec(cid, decision, comment="", document_id=None):
    return {"criterion_id": cid, "decision": decision, "comment": comment, "document_id": document_id}


def _p0():
    return [_crit("a")], _analysis(_v("a", "fail")), [_resp("a", "placeholder")]


def test_default_decision_is_resolve_and_p0_blocks():
    crit, an, resp = _p0()
    r = compute_readiness(crit, an, resp)  # no decisions -> default resolve
    item = r["items"][0]
    assert item["decision"] == "resolve" and item["comment"] == "" and item["document_id"] is None
    assert r["summary"]["p0_blocking"] == 1
    assert r["summary"]["p0_overridden"] == 0
    assert r["summary"]["ready_to_generate"] is False


def test_ignored_p0_stops_blocking_but_still_shows():
    crit, an, resp = _p0()
    r = compute_readiness(crit, an, resp, [_dec("a", "ignore", "accepting the gap")])
    assert _priority(r, "a") == "p0"  # still a P0 visually
    assert r["summary"]["p0_open"] == 1
    assert r["summary"]["p0_blocking"] == 0
    assert r["summary"]["p0_overridden"] == 1
    assert r["summary"]["ready_to_generate"] is True
    assert r["items"][0]["comment"] == "accepting the gap"


def test_do_not_proceed_p0_also_stops_blocking():
    crit, an, resp = _p0()
    r = compute_readiness(crit, an, resp, [_dec("a", "do_not_proceed")])
    assert r["summary"]["p0_blocking"] == 0
    assert r["summary"]["ready_to_generate"] is True


def test_one_ignored_one_open_still_blocks():
    criteria = [_crit("a"), _crit("b")]
    an = _analysis(_v("a", "fail"), _v("b", "fail"))
    resp = [_resp("a", "placeholder"), _resp("b", "placeholder")]
    r = compute_readiness(criteria, an, resp, [_dec("a", "ignore")])
    assert r["summary"]["p0_open"] == 2
    assert r["summary"]["p0_overridden"] == 1
    assert r["summary"]["p0_blocking"] == 1
    assert r["summary"]["ready_to_generate"] is False


def test_decision_document_id_surfaces_on_item():
    crit, an, resp = _p0()
    r = compute_readiness(crit, an, resp, [_dec("a", "resolve", document_id="doc-123")])
    assert r["items"][0]["document_id"] == "doc-123"


def test_confirm_item_carries_decision_fields():
    r = compute_readiness([_crit("a", conf=0.6, confirmed=False)], None, [],
                          [_dec("a", "ignore", "note")])
    item = r["items"][0]
    assert item["priority"] == "confirm"
    assert item["decision"] == "ignore" and item["comment"] == "note"
