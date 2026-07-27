"""Read models the routes and the web app share. Pure assembly over db + deterministic."""

from __future__ import annotations

from decimal import Decimal

from . import db
from .config import get_settings
from .deterministic import gates, qcbs, screening
from .deterministic.types import CompareKind, Criterion, CriterionAggregate, Response


def _crit(row: dict) -> Criterion:
    return Criterion(
        id=row["id"], kind=row["kind"], text=row["text"], max_marks=row["max_marks"] or 0,
        compare_kind=CompareKind(row.get("compare_kind") or "qualitative"),
        compare_op=row.get("compare_op"), compare_value=row.get("compare_value"),
    )


def screening_matrix(tender_id: str, authority_id: str) -> dict:
    """The activation surface: every bid against every published PQ criterion."""
    crits = db.criteria(tender_id, authority_id)
    all_bids = db.bids(tender_id, authority_id)
    resp = db.responses(tender_id, authority_id)
    domain = [_crit(c) for c in crits]
    by_bid: dict[str, list[Response]] = {}
    for r in resp:
        by_bid.setdefault(r["bid_id"], []).append(
            Response(r["criterion_id"], r.get("stated_value"), r.get("anchor_page")))

    rows = []
    for b in all_bids:
        cells = screening.screen_bid(domain, by_bid.get(b["id"], []))
        rows.append({
            "bid_id": b["id"], "bidder_name": b["bidder_name"],
            "responsive": b.get("responsive"), "responsive_reason": b.get("responsive_reason"),
            "auto_fail": screening.auto_non_responsive(cells),
            "cells": [{
                "criterion_id": c.criterion_id, "verdict": str(c.verdict),
                "required": c.required, "stated": c.stated, "anchor_page": c.anchor_page,
            } for c in cells],
        })
    return {
        "criteria": [{"id": c["id"], "text": c["text"], "compare_kind": c.get("compare_kind"),
                      "compare_op": c.get("compare_op"), "compare_value": c.get("compare_value"),
                      "anchor_page": c.get("anchor_page"), "anchor_clause": c.get("anchor_clause")}
                     for c in crits if c["kind"] == "pq"],
        "bids": rows,
    }


def _aggregates(tender_id: str, authority_id: str):
    crits = [c for c in db.criteria(tender_id, authority_id) if c["kind"] == "technical"]
    sc = db.scores(tender_id, authority_id)
    cons = {(c["bid_id"], c["criterion_id"]): Decimal(str(c["agreed_mark"]))
            for c in db.consensus(tender_id, authority_id)}
    by: dict[tuple[str, str], list[Decimal]] = {}
    for s in sc:
        by.setdefault((s["bid_id"], s["criterion_id"]), []).append(Decimal(str(s["final_mark"])))
    return crits, by, cons, sc


def technical_state(tender_id: str, authority_id: str) -> dict:
    """Aggregates, variance flags and everything blocking the technical lock."""
    ev = db.tender(tender_id, authority_id)
    crits, by, cons, sc = _aggregates(tender_id, authority_id)
    threshold = get_settings().variance_threshold
    responsive = [b for b in db.bids(tender_id, authority_id) if b.get("responsive")]

    out_bids, unsettled = [], []
    for b in responsive:
        rows, aggs = [], []
        for c in crits:
            key = (b["id"], c["id"])
            a = CriterionAggregate(c["id"], c["max_marks"] or 0,
                                   tuple(by.get(key, ())), cons.get(key))
            aggs.append(a)
            needs = gates.requires_consensus(a, threshold)
            mark = gates.committee_mark(a)
            if mark is None and a.marks:
                unsettled.append(f'{b["bidder_name"]} · {c["text"][:40]}')
            rows.append({
                "criterion_id": c["id"], "criterion": c["text"], "max_marks": c["max_marks"],
                "marks": [str(m) for m in a.marks], "spread": str(a.spread),
                "requires_consensus": needs,
                "consensus": str(cons[key]) if key in cons else None,
                "committee_mark": str(mark) if mark is not None else None,
            })
        total = gates.technical_score(aggs)
        out_bids.append({
            "bid_id": b["id"], "bidder_name": b["bidder_name"],
            "criteria": rows,
            "total": str(total) if total is not None else None,
            "qualified": gates.qualified(total, ev["qualifying_marks"]),
        })

    submitted = len({s["evaluator_id"] for s in sc})
    blockers = gates.technical_lock_blockers(
        submitted_evaluators=submitted, quorum=ev["quorum"], unsettled=unsettled)
    return {
        "locked_at": ev.get("technical_locked_at"),
        "quorum": ev["quorum"], "submitted_evaluators": submitted,
        "qualifying_marks": ev["qualifying_marks"],
        "max_technical_marks": sum(c["max_marks"] or 0 for c in crits),
        "bids": out_bids,
        "blockers": [{"code": b.code, "detail": b.detail} for b in blockers],
        "can_lock": not blockers,
    }


def result(tender_id: str, authority_id: str) -> dict:
    """QCBS ranking. Only ever called after the sealed-bid gate has been checked."""
    ev = db.tender(tender_id, authority_id)
    tech = technical_state(tender_id, authority_id)
    prices = {f["bid_id"]: f for f in db.financials(tender_id, authority_id)}

    payload = [{
        "bid_id": b["bid_id"], "bidder_name": b["bidder_name"],
        "technical_score": Decimal(b["total"] or 0),
        "technically_qualified": b["qualified"],
        "amount": prices.get(b["bid_id"], {}).get("amount_inr") if b["qualified"] else None,
    } for b in tech["bids"]]

    ranked = qcbs.rank(payload, technical_weight=ev["technical_weight"],
                       financial_weight=ev["financial_weight"],
                       max_technical_marks=tech["max_technical_marks"])
    ties = qcbs.has_unresolved_tie(ranked)
    decided = db.rest("GET", "tie_break_decisions", params={
        "tender_id": f"eq.{tender_id}", "authority_id": f"eq.{authority_id}",
        "select": "*"}) or []
    return {
        "technical_weight": ev["technical_weight"], "financial_weight": ev["financial_weight"],
        "tie_break_rule": ev.get("tie_break_rule"),
        "has_unresolved_tie": ties and not decided,
        "tie_break_decision": decided[0] if decided else None,
        "rows": [{
            "bid_id": r.bid_id, "bidder_name": r.bidder_name,
            "technical_score": str(r.technical_score),
            "technically_qualified": r.technically_qualified,
            "financial_score": str(r.financial_score) if r.financial_score is not None else None,
            "combined_score": str(r.combined_score) if r.combined_score is not None else None,
            "amount_inr": (str(prices[r.bid_id]["amount_inr"])
                           if r.bid_id in prices and r.technically_qualified else None),
            "rank": r.rank, "tied_with": list(r.tied_with),
        } for r in ranked],
    }


def dashboard(authority_id: str) -> list[dict]:
    """Per-tender counts for the officer's home screen.

    Built from screening_matrix() and technical_state() rather than fresh queries, so the
    dashboard and the detail screens cannot disagree — the bidder product already shipped four
    counters describing one object and none of them matching, and this is that same trap.

    `qualified` is deliberately None until technical scores exist. Rendering "0 qualified" for
    a tender still in screening would be a number that is not merely unhelpful but false.
    """
    out = []
    for t in db.tenders(authority_id):
        matrix = screening_matrix(t["id"], authority_id)
        bids = matrix["bids"]
        not_stated_cells = sum(
            1 for b in bids for c in b["cells"] if c["verdict"] == "not_stated")
        bids_missing_info = sum(
            1 for b in bids if any(c["verdict"] == "not_stated" for c in b["cells"]))

        scored = None
        if t.get("framework_locked_at") and any(b["responsive"] for b in bids):
            tech = technical_state(t["id"], authority_id)
            if tech["bids"] and any(b["total"] is not None for b in tech["bids"]):
                scored = {
                    "qualified": sum(1 for b in tech["bids"] if b["qualified"]),
                    "not_qualified": sum(
                        1 for b in tech["bids"] if b["total"] is not None and not b["qualified"]),
                    "unsettled": sum(1 for b in tech["bids"] if b["total"] is None),
                }

        out.append({
            "id": t["id"], "title": t["title"], "tender_number": t.get("tender_number"),
            "created_at": t.get("created_at"),
            "framework_locked_at": t.get("framework_locked_at"),
            "technical_locked_at": t.get("technical_locked_at"),
            "criteria_total": len(matrix["criteria"]),
            "bids_received": len(bids),
            "responsive": sum(1 for b in bids if b["responsive"] is True),
            "non_responsive": sum(1 for b in bids if b["responsive"] is False),
            "awaiting_decision": sum(1 for b in bids if b["responsive"] is None),
            "bids_missing_info": bids_missing_info,
            "missing_info_cells": not_stated_cells,
            # None means "not knowable yet", which the UI must render as such rather than 0.
            "scored": scored,
        })
    return out
