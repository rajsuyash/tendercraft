"""What ROLE an extracted requirement plays in the bid — and therefore which ones may vote.

`criterion_category` already says what subject a requirement belongs to (eligibility,
technical, financial, terms). It does not say what the bidder is supposed to DO about it,
and the bid/no-bid verdict needs exactly that. Today every mandatory criterion votes, so a
clause describing an inspection that happens months after award is scored as a condition of
entry.

Measured on the live Oil India wire-rope bid (GEM/2026/B/7876746), 2026-09-15. Eighteen
criteria are mandatory and therefore vote:

    4  post-award duties      "full quantity proof load test ... witnessed by BHEL safety
                               engineer during pre despatch inspection"
    4  quoting instructions   "Bidders to quote Rate / No. as defined above"
    4  forms and declarations "Make in india certificate as per format enclosed";
                               a local-content template still carrying "_______"
    3  rules about bidding    agent vs manufacturer, no double participation
    2  duties for a reseller  "In case of trader/agent, valid authorization certificate..."
    1  acceptance             "Acceptance to GEM GTC"
    0  eligibility gates

The tender states no turnover threshold, no experience requirement and no certification
requirement — it is a catalogue bid, and nothing in it disqualifies this bidder. The product
said NO-BID. That is what this module exists to stop.

THE ASYMMETRY, and it runs the opposite way to intuition. Every rule below can only ever
move a requirement OUT of `GATE`; the fallthrough is `OBLIGATION`, never `GATE`. A
requirement wrongly called an obligation still appears on the checklist, still appears in the
compliance matrix, and a human can promote it in one click. A requirement wrongly called a
gate can produce a false NO-BID — and nobody audits the bids they were told to skip, so that
error is invisible by construction. `spec_match.py` is built on the same trade for the same
reason.

Deterministic, no model call, and the ceiling is named: a gate phrased without any of the
nouns below is classified `OBLIGATION` and silently stops voting. The mitigation is
`kind_override`, and the measurement that would justify a model pass over the residue is the
override rate — if the median override count per tender exceeds two, the rules are too blunt.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from .drafting import template_placeholders
from .types import RequirementKind

# --- form -----------------------------------------------------------------------------------
#
# A template to fill in and attach. `template_placeholders` already detects the blank markers
# (`____`, `[Insert …]`, `<<…>>`, `{{…}}`) and is tested; it was written to stop an unfilled
# template reaching the library, and the same signal identifies a form here.
_FORM = re.compile(
    r"\b(?:as per (?:the )?(?:format|proforma|pro forma|annexure|appendix)"
    r"\s+(?:enclosed|attached|given|below|at)"
    r"|in the (?:prescribed |enclosed |attached )?(?:format|proforma|pro forma)"
    r"|(?:above|below|enclosed|attached) format"
    r"|on (?:the )?letterhead"
    r"|duly (?:filled|filled up|filled in)(?:[, ]+(?:and )?(?:sealed|signed|stamped))*"
    r")\b",
    re.I,
)

# --- instruction ----------------------------------------------------------------------------
#
# How to prepare or submit the bid. These are addressed to the bidder as a reader, not as a
# party: following them is how you bid at all, so they can neither pass nor fail.
_INSTRUCTION = re.compile(
    r"\b(?:bidders?\s+(?:to\s+)?(?:note|quote|are advised|may note|shall note|should note)"
    r"|instructions? to bidders?"
    r"|acceptance to\s+(?:gem\s+)?g\.?t\.?c"
    r"|as per\s+(?:gem\s+)?(?:general terms and conditions|g\.?t\.?c)"
    r"|(?:bid|tender)\s+(?:submission|opening)\s+(?:date|time|end)"
    r"|last date (?:and time )?for (?:submission|bid)"
    r"|pre-?bid (?:meeting|conference|querie?s?)"
    r"|corrigend(?:um|a)"
    r"|upload(?:ed)?\s+(?:on|to|through|in)\s+the\s+portal"
    r"|quote\s+(?:the\s+)?rate"
    r"|unit of measurement"
    r")\b",
    re.I,
)

# --- obligation -----------------------------------------------------------------------------
#
# A duty that binds AFTER award. Two independent signals, either sufficient.
#
# The temporal one is what would have caught the live defect: "load test ... during pre
# despatch inspection" names a moment that cannot exist before a contract does.
_OBLIGATION_WHEN = re.compile(
    r"\b(?:(?:after|upon|post[- ]?)\s*award"
    r"|during\s+(?:execution|the contract|manufacture|manufacturing"
    r"|pre-?despatch|pre-?dispatch|inspection)"
    r"|pre-?despatch inspection|pre-?dispatch inspection|\bPDI\b"
    r"|(?:at the time of|before|prior to)\s+(?:delivery|despatch|dispatch|inspection|supply)"
    r"|on receipt of (?:the )?(?:purchase )?order"
    r"|within\s+\d+\s+(?:days?|weeks?|months?)\s+(?:of|from|after)\s+"
    r"(?:the\s+)?(?:award|order|delivery|supply|despatch|dispatch|receipt)"
    r"|warranty|guarantee period|defect liability|liquidated damages"
    r"|payment (?:shall|will) be made"
    r"|inspection (?:shall|will) be (?:carried out|conducted|witnessed)"
    r"|will be witnessed|shall be witnessed"
    r"|in advance\b"
    r")",
    re.I,
)

# The duty's object is the GOODS rather than the bidder — a test or certification performed on
# what is supplied, which by definition happens after there is something to supply.
_OBLIGATION_OBJECT = re.compile(
    r"\b(?:each|every|the|all)\s+(?:items?|coils?|ropes?|drums?|lots?|consignments?|batch(?:es)?|"
    r"units?|slings?)\b",
    re.I,
)
_TEST_VERB = re.compile(
    r"\b(?:load\s*test|proof\s*load|test(?:ed|ing)?|inspect(?:ed|ion)?|certif(?:y|ied|icate))\b",
    re.I,
)

# --- gate -----------------------------------------------------------------------------------
#
# A pre-bid condition the bidder either meets or does not. The nouns are the ones an Indian
# tender's eligibility section actually uses; `category == 'eligibility'` is a strong prior
# because the extractor already made that judgement with the page in front of it.
_GATE_NOUN = re.compile(
    r"\b(?:(?:average )?annual turnover|turnover|net ?worth|working capital|solvency"
    r"|similar (?:nature of )?works?|experience of having|years? of (?:past )?experience"
    r"|successfully (?:completed|executed)"
    r"|ISO\s*\d{4}|BIS|IS\s*\d{3,5}|API\s*(?:spec|monogram)"
    r"|valid\s+\w*\s*(?:certificate|licence|license|registration|accreditation)"
    # `authori[sz]\w*` rather than a bare stem: the alternation is wrapped in a trailing `\b`,
    # so a stem ending mid-word ("authoris" inside "authorisation") can never match.
    r"|OEM|manufacturer'?s? authori[sz]\w*|\bMAF\b"
    r"|blacklist|debarr?ed|black-?listed"
    r"|\bEMD\b|earnest money|bid security"
    r"|\bMSE\b|MSME|udyam|DPIIT|start-?up"
    r"|\bPAN\b|\bGST\b|\bGSTIN\b|\bCIN\b"
    r"|registered (?:with|under|as)"
    r")\b",
    re.I,
)


def classify_kind(
    verbatim_text: str, category: str = "", requirement_level: str = ""
) -> RequirementKind:
    """What role this requirement plays. Pure, and never returns GATE by default.

    Precedence is first-match-wins and the order is load-bearing: a blank declaration form
    ("…local content of _______ %") also contains the word "content" and could be read as a
    spec, and a quoting instruction ("rates inclusive of taxes and duties") contains a
    financial noun. The most specific structural signal wins, and eligibility nouns are
    consulted last, so a form that happens to mention turnover is still a form.
    """
    text = verbatim_text or ""

    # 1. FORM — a template with blanks, or prose naming one. The blank markers are the
    #    strongest signal in the corpus: nothing else in a tender contains a run of
    #    underscores where a human writes.
    if template_placeholders(text) or _FORM.search(text):
        return RequirementKind.FORM

    # 2. INSTRUCTION — addressed to the bidder as a reader. Neither passes nor fails.
    if _INSTRUCTION.search(text):
        return RequirementKind.INSTRUCTION

    # 3. OBLIGATION — a duty that binds after award.
    if _OBLIGATION_WHEN.search(text):
        return RequirementKind.OBLIGATION
    if _OBLIGATION_OBJECT.search(text) and _TEST_VERB.search(text):
        return RequirementKind.OBLIGATION

    # 4. GATE — survived everything above AND names something checkable about the bidder.
    if _GATE_NOUN.search(text):
        return RequirementKind.GATE
    if category == "eligibility" and requirement_level == "mandatory":
        # The extractor read this page and called it eligibility. Trust it where the text
        # carries no noun we recognise, because the alternative is dropping a real gate on
        # the strength of a vocabulary list.
        return RequirementKind.GATE

    # 5. Unrecognised. OBLIGATION, never GATE — see the asymmetry in the module docstring.
    return RequirementKind.OBLIGATION


def effective_kind(row: Mapping) -> RequirementKind:
    """A criterion's kind, honouring a human's override.

    Computed at READ time rather than stored, so improving a rule reclassifies every existing
    tender on deploy instead of needing a data migration. The override is the only part that
    cannot be recomputed, which is why it is the only part with a column.
    """
    override = row.get("kind_override")
    if override:
        return RequirementKind(override)
    return classify_kind(
        row.get("verbatim_text") or "",
        str(row.get("category") or ""),
        str(row.get("requirement_level") or ""),
    )
