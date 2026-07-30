"""GeM bid document → the eligibility facts, deterministically.

**Why there is no model in this file.** A GeM bid document is not a scanned RFP. It is generated
by `wkhtmltopdf` from a form, so it has a real text layer and a stable bilingual template in
which every eligibility field is a labelled table row. That makes the whole C-FR7 subset —
turnover threshold, EMD, estimated value, MSE/startup relaxations — a *parse*, not an
extraction. Sending it to a model would add cost, latency, a confidence score we would then have
to threshold, and a failure mode (invention) that a regex does not have. PRD §7 puts
"eligibility-subset extraction from an NIT" in the AI column; for this source it belongs in the
deterministic one, and `docs/discovery/source-gem.md` finding 5 records why.

The free-text ATC clauses lower in the document are a different matter and stay with the model
in a later phase. This file reads the table.

**Extraction mechanics.** `pypdf`'s default `extract_text()` is unusable here: it emits the
label and its value as separate lines, so `Minimum Average Annual Turnover` arrives with no
number attached. `extraction_mode="layout"` preserves the column geometry and keeps each label
on the same line as its value, which is the entire reason this parser can be deterministic.
(`pdftotext -layout` also works but would put a poppler system binary in the container for no
extra capability.)

Two properties of the extracted text shape everything below:

1. **The Devanagari half of each bilingual label is mangled** into junk ASCII by the font
   encoding ("बड सं या" → "C"). It is never matched on; every anchor is the English label,
   which always follows a `/`.
2. **Values sometimes abut the label with no whitespace** (`/Bid to RA enabledYes`), so a
   column-split on runs of spaces loses them. Splitting on the label string itself is what
   handles both spaced and abutted forms.
"""

from __future__ import annotations

import io
import re
from typing import Any

from pypdf import PdfReader

from .fetch import GuardedFetcher

# Indian numbering, as GeM writes it. A Lakh/Crore mix-up on a turnover gate is a 100x error
# that reads as a plausible number, so the multipliers live here as one table and the parser
# refuses anything it does not recognise rather than defaulting to units.
_UNIT_MULTIPLIERS = {
    "lakh": 100_000,
    "lakhs": 100_000,
    "lac": 100_000,
    "lacs": 100_000,
    "crore": 10_000_000,
    "crores": 10_000_000,
    "cr": 10_000_000,
}

_NUMBER = r"(\d[\d,]*(?:\.\d+)?)"


def _clean(line: str) -> str:
    """Blank out the mangled Devanagari, keeping the ASCII skeleton *in place*.

    Replaced with spaces rather than deleted: deleting them shifts every column left by a
    different amount per line, which destroys the one property this parser depends on — that a
    value's continuation lines are indented into the value column. Measured cost of getting this
    wrong: `Item Category` came back starting mid-sentence at "testing & Maintaining…", having
    silently dropped its first line.
    """
    return re.sub(r"[^\x20-\x7e]", " ", line).rstrip()


# A new labelled row, e.g. "/Bid End Date/Time". Used to know where a wrapped value cell ends.
_LABEL_MARKER = re.compile(r"/[A-Z]")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _cell_above(lines: list[str], label: str) -> str | None:
    """The wrapped value block sitting immediately ABOVE a label line.

    GeM vertically centres a label against a tall value cell, so a multi-line value starts on
    lines *preceding* its own label. `Document required from seller` is the case that matters:
    its actionable content ("Experience Criteria, Bidder Turnover, Certificate") is entirely
    above the label, and reading the label line alone returns GeM's boilerplate exemption note
    instead — authoritative-looking and wrong.
    """
    for i, line in enumerate(lines):
        index = line.find(label)
        if index < 0:
            continue
        block: list[str] = []
        for previous in reversed(lines[:i]):
            # Continuation lines are indented into the value column and carry no label of
            # their own. Anything else ends the cell.
            if not previous.strip() or _indent(previous) <= index or _LABEL_MARKER.search(previous):
                break
            block.append(previous.strip())
        return " ".join(reversed(block)) or None
    return None


def extract_layout_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(
        (page.extract_text(extraction_mode="layout") or "") for page in reader.pages
    )


def parse_amount(raw: str | None) -> int | None:
    """"5 Lakh (s)" → 500000 · "3.93 (in lakhs)" → 393000 · "5458313.82" → 5458313

    Returns None — never a guess — when the string carries no number, or carries a unit word
    this function does not know. An unrecognised unit that silently fell through to "rupees"
    would under-state a threshold by 100x and hand a bidder a Likely-eligible they do not have
    (ET-1). Rounded to whole rupees: paise never decide an eligibility comparison.
    """
    if not raw:
        return None
    text = raw.strip().lower()
    match = re.search(_NUMBER, text)
    if not match:
        return None
    value = float(match.group(1).replace(",", ""))

    # Any alphabetic token after the number is treated as a unit claim and must be understood.
    for token in re.findall(r"[a-z]+", text[match.end() :]):
        if token in _UNIT_MULTIPLIERS:
            return int(round(value * _UNIT_MULTIPLIERS[token]))
        if token in ("in", "s", "value", "inr", "rs", "rupees", "only", "and", "of", "taxes"):
            continue  # noise words GeM wraps units in: "(in lakhs)", "Lakh (s)"
        return None  # an unknown unit word — refuse rather than assume rupees
    return int(round(value))


def _value_after(line: str, label: str) -> str | None:
    """Everything on `line` after `label`. Handles both spaced and abutted values."""
    index = line.find(label)
    if index < 0:
        return None
    return line[index + len(label) :].strip() or None


# A section heading is a labelled line carrying NO value of its own: "/EMD Detail".
#
# The `(?! )` guard on runs of whitespace is what separates a heading from a labelled row whose
# value happens to be a bare word. Without it, "/Required          No" matches — every character
# is a letter or a space — so `_section` treats it as the start of a new section and returns the
# EMD section as empty, reporting `emd_required: None` on a bid that plainly says No.
#
# That bug was live and invisible: in real documents the mangled Devanagari leaves residue
# BEFORE the slash ("P    /Required   No"), so `^/` failed to match and the line was correctly
# treated as a row. It only surfaced against a synthetic line-set with no residue — which is a
# fair description of why the synthetic tests exist at all.
_HEADING = re.compile(r"^/[A-Za-z][A-Za-z()%/]*(?: [A-Za-z()%/]+)*$")


def _section(lines: list[str], heading: str) -> list[str]:
    """The lines belonging to one section — from its heading to the next heading.

    Bounded on purpose. `/Required` appears twice in a GeM bid document, once under
    `/EMD Detail` and once under `/ePBG Detail`, with identical text. An unbounded scan from the
    EMD heading finds the *ePBG* row whenever the EMD section has no `/Required` of its own —
    which is exactly what high-value bids look like (they carry `/EMD Amount` instead). Both
    values are commonly "No", so the bug stays invisible until the one bid where they differ,
    and then it tells a bidder no deposit is needed on a tender wanting crores.
    """
    out: list[str] = []
    started = False
    for line in lines:
        stripped = line.strip()
        if not started:
            if stripped == heading.strip():
                started = True
            continue
        if _HEADING.match(stripped) and stripped != heading.strip():
            break
        out.append(line)
    return out


def _find(lines: list[str], label: str) -> str | None:
    """First value for `label` anywhere in `lines`."""
    for line in lines:
        value = _value_after(line, label)
        if value:
            return value
    return None


def parse_bid_document(pdf_bytes: bytes) -> dict[str, Any]:
    """The C-FR7 eligibility subset, as facts. Pure over the PDF bytes."""
    return parse_lines([_clean(line) for line in extract_layout_text(pdf_bytes).splitlines()])


def parse_lines(lines: list[str]) -> dict[str, Any]:
    """Every field decision, over already-extracted and cleaned lines.

    Split out from `parse_bid_document` so the whole parser is testable without a GeM PDF. That
    matters more here than it usually would: the real documents cannot be committed (public repo,
    GeM reproduction clause), so a suite that could only be exercised through real bytes would
    have no regression coverage in CI at all. Synthetic line-sets in the tests describe the
    template shapes; the real documents then only need to confirm invariants.
    """
    turnover_raw = _find(lines, "/Minimum Average Annual Turnover of the")
    value_raw = _find(lines, "/ Estimated Bid Value in INR (Inclusive of all")
    # GeM emits this label with and without the leading space depending on the template.
    if value_raw is None:
        value_raw = _find(lines, "/Estimated Bid Value in INR (Inclusive of all")

    # EMD and ePBG have TWO shapes and only one appears per bid:
    #   low value  → "/Required   No"
    #   high value → "/EMD Amount   31200000"  /  "/ePBG Percentage(%)   5.00"  (no Required row)
    # Reading only the first shape reported `None` on a bid demanding a ₹3.12 crore deposit —
    # an "unknown" that hid the single largest number a bidder needs to find up front.
    emd_section = _section(lines, "/EMD Detail")
    epbg_section = _section(lines, "/ePBG Detail")
    emd_amount = parse_amount(_find(emd_section, "/EMD Amount"))
    epbg_percentage = _find(epbg_section, "/ePBG Percentage(%)")

    return {
        # ── the two numbers a deterministic comparator reads ──
        "min_avg_annual_turnover_inr": parse_amount(turnover_raw),
        "min_avg_annual_turnover_raw": turnover_raw,
        "estimated_value_inr": parse_amount(value_raw),
        "estimated_value_raw": value_raw,
        # ── money the bidder must find up front ──
        # An amount present means it is required, whatever the Required row says or omits.
        "emd_required": True if emd_amount else _yes_no(_find(emd_section, "/Required")),
        "emd_amount_inr": emd_amount,
        "epbg_required": (
            True if epbg_percentage else _yes_no(_find(epbg_section, "/Required"))
        ),
        "epbg_percentage": epbg_percentage,
        # ── experience, the other half of the C-FR7 subset ──
        "past_experience_required_raw": _find(
            lines, "/Years of Past Experience Required for"
        ),
        # ── relaxations that can flip an ineligible verdict ──
        "mse_turnover_relaxation": _find(lines, "/ MSE"),
        "startup_turnover_relaxation": _find(lines, "/ Startup") or _find(lines, "/Startup"),
        "mse_purchase_preference": _yes_no(_find(lines, "/MSE Purchase Preference")),
        "mii_compliance": _yes_no(_find(lines, "/MII Compliance")),
        # ── what the buyer will ask for ──
        # Read from the block ABOVE the label; see _cell_above. The label line itself holds
        # GeM's standing exemption boilerplate, which is identical on every bid and useless.
        "documents_required_from_seller": _cell_above(lines, "/Document required"),
        # ── identity and timing, for cross-checking the listing record ──
        "bid_number": _find(lines, "/Bid Number:") or _find(lines, "/Bid Number"),
        "bid_end": _find(lines, "/Bid End Date/Time"),
        "bid_opening": _find(lines, "/Bid Opening"),
        "offer_validity": _find(lines, "/Bid Offer"),
        "ministry": _find(lines, "/Ministry/State Name"),
        "department": _find(lines, "/Department Name"),
        "organisation": _find(lines, "/Organisation Name"),
        "office": _find(lines, "/Office Name"),
        # Item/Similar Category are deliberately NOT parsed here. They are tall wrapped cells,
        # and the listing record already carries the complete category list in
        # `bd_category_name` — a half-parsed copy that starts mid-sentence is strictly worse
        # than not having the field, because downstream screens would render it as the title.
        "contract_period": _find(lines, "/Contract Period"),
        "bid_type": _find(lines, "/Type of Bid"),
        "evaluation_method": _find(lines, "/Evaluation Method"),
    }


def _yes_no(raw: str | None) -> bool | None:
    """Tri-state on purpose. A missing field is None, not False — "we did not find out whether
    an EMD is required" and "no EMD is required" are different facts, and collapsing them
    tells a bidder they need no bank guarantee when we simply failed to read the row."""
    if raw is None:
        return None
    head = raw.strip().split()[0].strip(".,").lower() if raw.strip() else ""
    if head == "yes":
        return True
    if head == "no":
        return False
    return None


def fetch_bid_document(fetcher: GuardedFetcher, parent_bid_id: str | int) -> bytes:
    """GET /showbidDocument/<parent_bid_id>.

    The PARENT id, never the item id: the item id returns HTTP 200 carrying a *different* bid's
    document, so passing the wrong one yields confident eligibility facts about the wrong
    tender (docs/discovery/known-pitfalls.md).

    Robots-permitted and needs no cookie — measured, source-gem.md finding 4.
    """
    response = fetcher.get(f"/showbidDocument/{parent_bid_id}")
    body = response.content
    if not body.startswith(b"%PDF"):
        # An HTML error page rendered as a PDF filename. Refuse rather than hand pypdf junk and
        # report "no eligibility fields found", which would look like a template change.
        raise ValueError(
            f"/showbidDocument/{parent_bid_id} did not return a PDF "
            f"(first bytes {body[:16]!r}, content-type {response.headers.get('content-type')!r})"
        )
    return body


def eligibility_for(fetcher: GuardedFetcher, parent_bid_id: str | int) -> dict[str, Any]:
    return parse_bid_document(fetch_bid_document(fetcher, parent_bid_id))
