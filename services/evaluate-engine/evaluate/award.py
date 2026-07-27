"""Award and regret letters with debrief summaries (F27), behind the disclosure gate (F28).

Order of operations, and it is the whole design:

    result → per-recipient payload → DISCLOSURE FILTER → letter

The filter runs before the letter is assembled, so a forbidden field is never in the material
the letter is built from. Redacting afterwards would mean the competitor's data was in the
buffer and we removed what we remembered to remove.

Every figure is transcluded from stored evaluation data. Nothing here is model-authored, and
there is deliberately no model call in this module at all: a letter to a firm that just lost a
public contract is read by their lawyer, and "the model phrased it that way" is not a defence.
The prose is a template over disclosed fields.
"""

from __future__ import annotations

from . import db, service
from .deterministic.disclosure import (
    DisclosureError,
    Outcome,
    assert_disclosable,
    contains_forbidden,
    filter_for_recipient,
    outcome_for,
)
from .envelope import ApiError


def _fmt_inr(value) -> str:
    """Indian grouping: ₹1,20,00,000 is 2-2-3, not 3-3-3. Getting this wrong in a letter to a
    bidder is the kind of error that gets quoted back at you."""
    if value in (None, ""):
        return "—"
    s = str(int(float(value)))
    if len(s) <= 3:
        return f"₹{s}"
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return "₹" + ",".join(parts + [tail])


def _payload_for(bid_row: dict, res: dict, ev: dict, auth: dict, crits: list[dict],
                 screening_row: dict | None, winner: dict | None, bid_count: int) -> dict:
    """Everything we COULD tell this recipient. The filter decides what we actually do."""
    return {
        "tender_title": ev["title"],
        "tender_number": ev.get("tender_number"),
        "authority_name": (auth or {}).get("name"),
        "bidder_name": bid_row["bidder_name"],
        "own_rank": bid_row["rank"],
        "own_technical_score": bid_row["technical_score"],
        "own_combined_score": bid_row["combined_score"],
        "own_responsiveness": {
            "responsive": (screening_row or {}).get("responsive"),
            "reason": (screening_row or {}).get("responsive_reason"),
        },
        "published_criteria": [{"text": c["text"], "max_marks": c.get("max_marks")}
                               for c in crits if c["kind"] == "technical"],
        "technical_weight": ev["technical_weight"],
        "financial_weight": ev["financial_weight"],
        "qualifying_marks": ev["qualifying_marks"],
        "winner_name": (winner or {}).get("bidder_name"),
        "accepted_price_inr": (winner or {}).get("amount_inr"),
        "total_bids_received": bid_count,
        # Deliberately included so the filter has to refuse them, and the refusal is visible in
        # the audit trail. If these ever stop being refused, something changed that shouldn't.
        "other_bids": [{"bidder_name": r["bidder_name"], "combined_score": r["combined_score"]}
                       for r in res["rows"] if r["bid_id"] != bid_row["bid_id"]],
        "other_prices": {r["bidder_name"]: r.get("amount_inr") for r in res["rows"]
                         if r["bid_id"] != bid_row["bid_id"]},
    }


def _letter_body(fields: dict, outcome: Outcome) -> str:
    """A template over disclosed fields. No model call — see the module docstring."""
    name = fields.get("bidder_name", "Sir/Madam")
    title = fields.get("tender_title", "the tender")
    number = fields.get("tender_number")
    ref = f" ({number})" if number else ""
    lines: list[str] = []

    if outcome is Outcome.AWARD:
        lines += [
            f"Dear {name},",
            "",
            f"Following evaluation of the bids received for {title}{ref}, your bid has been "
            f"placed first and is accepted at {_fmt_inr(fields.get('accepted_price_inr'))}.",
        ]
    else:
        lines += [
            f"Dear {name},",
            "",
            f"Following evaluation of the bids received for {title}{ref}, we write to inform "
            f"you that your bid has not been selected.",
        ]

    resp = fields.get("own_responsiveness") or {}
    if resp.get("responsive") is False:
        reason = resp.get("reason") or "it did not meet a mandatory requirement"
        lines += ["", f"Your bid was not taken forward to technical evaluation because {reason}."]
    else:
        rank = fields.get("own_rank")
        total = fields.get("total_bids_received")
        if rank and total:
            lines += ["", f"Your bid was ranked {rank} of {total} bids received."]
        if fields.get("own_technical_score") is not None:
            lines += [
                f"Your technical score was {fields['own_technical_score']} against a "
                f"qualifying mark of {fields.get('qualifying_marks')}.",
            ]
        if fields.get("own_combined_score") is not None:
            lines += [
                f"Your combined score, weighted {fields.get('technical_weight')} technical to "
                f"{fields.get('financial_weight')} financial, was {fields['own_combined_score']}.",
            ]

    if outcome is Outcome.REGRET and fields.get("winner_name"):
        lines += [
            "",
            f"The contract has been awarded to {fields['winner_name']} at "
            f"{_fmt_inr(fields.get('accepted_price_inr'))}.",
        ]

    lines += [
        "",
        "Bids were evaluated solely against the criteria published in the bid document. "
        "We thank you for participating and look forward to your interest in future tenders.",
        "",
        "Yours faithfully,",
        fields.get("authority_name") or "",
    ]
    return "\n".join(lines)


def build_letters(tender_id: str, authority_id: str) -> dict:
    """One letter per bidder, each filtered independently for its own recipient."""
    ev = db.tender(tender_id, authority_id)
    if not ev:
        raise ApiError(404, "TENDER_NOT_FOUND", "tender not found in your authority")

    res = service.result(tender_id, authority_id)
    try:
        assert_disclosable(ranking_final=not res["has_unresolved_tie"],
                           tender_state=ev.get("state") or "active")
    except DisclosureError as exc:
        raise ApiError(409, "RESULT_NOT_FINAL", str(exc)) from exc

    auth = db.authority(authority_id)
    crits = db.criteria(tender_id, authority_id)
    screening = {r["bid_id"]: r for r in service.screening_matrix(
        tender_id, authority_id)["bids"]}
    winner = next((r for r in res["rows"]
                   if r["rank"] == 1 and r["technically_qualified"]), None)

    letters = []
    for row in res["rows"]:
        outcome = outcome_for(row["rank"], row["technically_qualified"])
        payload = _payload_for(row, res, ev, auth, crits, screening.get(row["bid_id"]),
                               winner, len(res["rows"]))

        # THE GATE. Everything after this line sees only what this recipient may see.
        disclosed = filter_for_recipient(payload)
        body = _letter_body(disclosed.fields, outcome)

        # Belt and braces: assert on the produced text, not on our intentions (F28-AC2).
        others = [r["bidder_name"] for r in res["rows"] if r["bid_id"] != row["bid_id"]
                  and r["bidder_name"] != disclosed.fields.get("winner_name")]
        leaked = contains_forbidden(body, others)
        if leaked:
            raise ApiError(500, "DISCLOSURE_BLOCKED",
                           f"generated letter names other bidders: {', '.join(leaked)}")

        letters.append({
            "bid_id": row["bid_id"],
            "bidder_name": row["bidder_name"],
            "outcome": str(outcome),
            "body": body,
            "refused_fields": list(disclosed.refused),
        })

    return {
        "tender_title": ev["title"],
        "tender_number": ev.get("tender_number"),
        "winner": (winner or {}).get("bidder_name"),
        "letters": letters,
    }
