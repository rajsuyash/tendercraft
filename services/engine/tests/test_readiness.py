"""Bid-readiness P0/P1/P2 priority mapping."""

from app.deterministic.readiness import compute_readiness


def _crit(cid, level="mandatory", conf=0.95, confirmed=True, page=12, clause="4.1(a)",
          kind="gate"):
    """A criterion row. `kind_override="gate"` by default because these tests are about the
    PRIORITY mapping for things that can pass or fail; a non-gate never reaches those branches
    and `criterion {cid}` classifies as an obligation. The non-gate path has its own tests at
    the bottom of this file."""
    return {
        "id": cid,
        "verbatim_text": f"criterion {cid}",
        "requirement_level": level,
        "confidence": conf,
        "confirmed": confirmed,
        "anchor_page": page,
        "anchor_clause": clause,
        "kind_override": kind,
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



# --- non-gates never block ------------------------------------------------------------------


def test_a_post_award_obligation_never_blocks_generation():
    """The regression this pairs with: `analyze` evaluates gates only, so a non-gate has no
    verdict — and the mandatory fallthrough is "no verdict yet, block until matched". Without
    a kind branch every obligation on the tender would become a blocking P0 the moment gates
    started being filtered, which is worse than the defect being fixed."""
    duty = _crit("o", kind="obligation")

    out = compute_readiness([duty], None, [], [])

    assert _priority(out, "o") == "p2"
    assert out["summary"]["p0_blocking"] == 0
    assert out["summary"]["ready_to_generate"] is True


def test_every_non_gate_kind_says_what_it_is():
    """A checklist that reads "Run analysis to check eligibility" against a blank declaration
    form has told the user nothing and asked them to do the wrong thing."""
    rows = [
        _crit("o", kind="obligation"), _crit("i", kind="instruction"),
        _crit("f", kind="form"), _crit("s", kind="spec"),
    ]

    items = {i["criterion_id"]: i for i in compute_readiness(rows, None, [], [])["items"]}

    assert "Post-award" in items["o"]["status"]
    assert "submit" in items["i"]["status"]
    assert items["f"]["action"] == "upload"
    assert "schedule" in items["s"]["status"]
    assert all(i["priority"] == "p2" for i in items.values())


def test_a_low_confidence_non_gate_is_still_confirmed_first():
    """Confirmation is about whether the EXTRACTION is right, which is a question about every
    requirement regardless of what it later turns out to be."""
    row = _crit("x", conf=0.6, confirmed=False, kind="obligation")

    assert _priority(compute_readiness([row], None, [], []), "x") == "confirm"


# --- a gate the analysis declined to score ------------------------------------------------------


def _demoted(cid: str, *verdicts) -> dict:
    """What `analyze` stores when the classifier says gate and the reading finds nothing."""
    return {
        "verdicts": list(verdicts),
        "checklist": [{
            "criterion_id": cid, "verbatim_text": "x", "kind": "gate",
            "requirement_level": "mandatory", "source_anchor": "p.5",
            "note": "This reads like an eligibility condition, but the clause states nothing "
                    "that can be checked against your profile, so it is not scored.",
        }],
    }


def _status(result, cid):
    return next(i["status"] for i in result["items"] if i["criterion_id"] == cid)


def test_a_gate_the_analysis_declined_to_score_does_not_block():
    """The regression this test exists for, measured live on the Oil India bid before it was
    fixed: five criteria classified as gates, none of them scored, each filed as a blocking
    P0 reading "Run analysis to check eligibility" — on a tender whose analysis HAD run and
    would never produce a verdict for them. `ready_to_generate` went false and the Generate
    button became "Clear the blocking items first", pointing at five items no user could ever
    clear. The same dead end the non-gate branch prevents, arriving through a second door."""
    r = compute_readiness([_crit("a")], _demoted("a"), [])

    assert _priority(r, "a") == "p2"
    assert "nothing checkable" in _status(r, "a")
    assert r["summary"]["p0_blocking"] == 0
    assert r["summary"]["ready_to_generate"] is True


def test_a_gate_with_no_analysis_at_all_still_blocks():
    """The guard must not be so broad that it swallows the real case. A criterion with no
    verdict because analysis was never RUN is a genuine blocker, and the checklist is the only
    thing that separates the two."""
    r = compute_readiness([_crit("a")], None, [])
    assert _priority(r, "a") == "p0"
    assert r["summary"]["ready_to_generate"] is False


def test_a_scored_gate_is_unaffected_by_another_row_s_demotion():
    r = compute_readiness(
        [_crit("a"), _crit("b")],
        _demoted("b", _v("a", "fail", gap="short")),
        [_resp("a", "placeholder")],
    )
    assert _priority(r, "a") == "p0"   # a real eligibility gap still blocks
    assert _priority(r, "b") == "p2"


def test_a_checklist_entry_without_a_note_is_not_a_demoted_gate():
    """Ordinary non-gates reach the checklist too, carrying no note. They are already handled
    by their kind, and reading them as demoted gates would give them the wrong status line."""
    analysis = {"verdicts": [], "checklist": [{"criterion_id": "a", "kind": "obligation",
                                               "note": ""}]}
    r = compute_readiness([_crit("a", kind="obligation")], analysis, [])
    assert _priority(r, "a") == "p2"
    assert "Post-award duty" in _status(r, "a")
