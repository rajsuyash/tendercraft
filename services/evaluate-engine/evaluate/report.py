"""The evaluation report (F11) — the defensible document.

Every mark is attributed to a named evaluator with their rationale; every figure is
transcluded from stored data. Nothing here is model-authored.
"""

from __future__ import annotations

from . import db, service


def build_report(tender_id: str, authority_id: str) -> dict:
    ev = db.tender(tender_id, authority_id)
    auth = db.authority(authority_id)
    crits = db.criteria(tender_id, authority_id)
    members = {m["user_id"]: m for m in db.members(authority_id)}
    coi = db.coi(tender_id, authority_id)
    scores = db.scores(tender_id, authority_id)
    consensus = {(c["bid_id"], c["criterion_id"]): c for c in db.consensus(tender_id, authority_id)}
    screening = service.screening_matrix(tender_id, authority_id)
    tech = service.technical_state(tender_id, authority_id)
    res = service.result(tender_id, authority_id)

    crit_by_id = {c["id"]: c for c in crits}

    def name(uid):
        m = members.get(uid)
        return (m or {}).get("full_name") or (m or {}).get("email") or "unknown"

    per_bid = []
    for b in tech["bids"]:
        rows = []
        for c in b["criteria"]:
            marks = [{
                "evaluator": name(s["evaluator_id"]),
                "mark": str(s["final_mark"]),
                "rationale": s["rationale"],
                "pre_reveal": str(s["pre_reveal_mark"]),
                "ai_proposed": (str(s["ai_proposed_mark"])
                                if s.get("ai_proposed_mark") is not None else None),
            } for s in scores
                if s["bid_id"] == b["bid_id"] and s["criterion_id"] == c["criterion_id"]]
            con = consensus.get((b["bid_id"], c["criterion_id"]))
            rows.append({
                "criterion": c["criterion"], "max_marks": c["max_marks"],
                "anchor": crit_by_id.get(c["criterion_id"], {}).get("anchor_clause"),
                "individual_marks": marks,
                "consensus": ({"mark": str(con["agreed_mark"]), "note": con["note"],
                               "chair": name(con["chair_id"])} if con else None),
                "committee_mark": c["committee_mark"],
            })
        per_bid.append({
            "bidder_name": b["bidder_name"], "total": b["total"],
            "qualified": b["qualified"], "criteria": rows,
        })

    return {
        "authority": (auth or {}).get("name"),
        "evaluation": {
            "title": ev["title"], "tender_number": ev.get("tender_number"),
            "method": "Two-bid QCBS",
            "technical_weight": ev["technical_weight"],
            "financial_weight": ev["financial_weight"],
            "qualifying_marks": ev["qualifying_marks"],
            "quorum": ev["quorum"],
            "framework_locked_at": ev.get("framework_locked_at"),
            "technical_locked_at": ev.get("technical_locked_at"),
        },
        "committee": [{
            "name": name(m["user_id"]), "role": m["role"],
            "declaration": next(
                ({"has_interest": c["has_interest"], "detail": c["detail"]}
                 for c in coi if c["user_id"] == m["user_id"]), None),
        } for m in members.values() if m["role"] != "auditor"],
        "responsiveness": [{
            "bidder_name": r["bidder_name"], "responsive": r["responsive"],
            "reason": r["responsive_reason"],
        } for r in screening["bids"]],
        "technical": per_bid,
        "result": res,
    }
