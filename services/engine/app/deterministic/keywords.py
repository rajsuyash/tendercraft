"""Breaking long-tail capability keywords into terms a tender title might actually contain.

Pure, model-free, and deliberately so. Keywords feed `keyword_match_required`, which is the one
rule that can HIDE tenders — so anything that writes them sits close to G-9's line. This module
only ever proposes; nothing here saves, and the caller must put a human between a proposal and
the profile. `pipeline/keywords.py` does the same job better with a model and a website, and
falls back to this when the model is unavailable.

Why the mechanical version exists at all: the failure it repairs is mechanical. A live workspace
entered

    "expertise in elevator / crane / oil indutry/ mines / general engineering"

as ONE keyword. Matching is per whole term, so it matched nothing, the opt-in gate hid all 335
swept tenders, and the feed read as empty. No model is needed to see that this is a list of five
things with a filler prefix — and a repair that needs a model is a repair that is unavailable
exactly when the model is.

What it does NOT do: fix spelling ("oil indutry"), infer products the vendor never mentioned, or
rank. Those need the model, and the caller labels which suggestions came from where so a vendor
can tell what we read from what we guessed.
"""

from __future__ import annotations

import re

#: Split on anything a person uses to mean "and also". Comma, slash, semicolon, newline,
#: ampersand, and the word "and" surrounded by spaces.
_SEPARATORS = re.compile(r"[,/;\n&]|\band\b", re.IGNORECASE)

#: Lead-ins that describe the vendor's relationship to a thing rather than the thing. Stripped
#: from the FRONT only: "expertise in elevator" is about elevators, but "elevator expertise"
#: is too, and chopping the tail of a two-word term loses the noun.
_LEAD_INS = re.compile(
    r"^(?:"
    r"expertise\s+in|experience\s+in|specialis(?:ed|ing)\s+in|specializ(?:ed|ing)\s+in|"
    r"provision\s+of|supply\s+of|manufactur(?:e|ing)\s+of|design\s+of|"
    r"we\s+(?:do|make|supply|provide)|our\s+"
    r")\s*",
    re.IGNORECASE,
)

#: Words that describe commerce rather than a product. On their own they match half a national
#: portal — "services" appears in most GeM category codes — so they are never emitted alone.
#: They may still appear INSIDE a kept phrase ("annual maintenance contract").
_GENERIC = frozenset({
    "expertise", "experience", "manufacturing", "manufacture", "supply", "supplies",
    "services", "service", "provision", "solutions", "solution", "general", "works",
    "work", "products", "product", "systems", "system", "equipment", "material",
    "materials", "items", "goods", "various", "misc", "miscellaneous", "other", "others",
    "industry", "industries", "sector", "company", "limited", "ltd", "pvt", "private",
})

#: Grammar. Never a keyword, never part of one we emit.
_STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "of", "for", "in", "on", "at", "to", "with", "by",
    "from", "as", "is", "are", "we", "our", "us", "its", "their", "all", "any", "&",
})

#: Below this a token is an abbreviation or noise ("of", "hp"). GeM category codes are short,
#: but those arrive as codes rather than as prose a vendor typed.
_MIN_TOKEN = 3

#: A term of more than this many words is a description, not a keyword — it is what we are
#: breaking down, never something we emit.
_MAX_WORDS = 3


def _tokens(text: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", text.lower()) if t]


def _is_content(token: str) -> bool:
    return (
        len(token) >= _MIN_TOKEN
        and token not in _STOPWORDS
        and token not in _GENERIC
        and not token.isdigit()
    )


def split_long_tail(terms: list[str] | None) -> list[str]:
    """→ short candidate keywords, in a stable order, deduplicated, never empty-string.

    Order is: the term itself when it is already short enough, then adjacent content pairs,
    then single content words. Pairs before singles because "wire rope" is a far better keyword
    than "rope", and a caller that truncates should lose the weakest first.
    """
    out: list[str] = []

    def add(term: str) -> None:
        term = term.strip()
        if term and term not in out:
            out.append(term)

    for raw in terms or []:
        for fragment in _SEPARATORS.split(raw or ""):
            fragment = _LEAD_INS.sub("", (fragment or "").strip().lower()).strip()
            if not fragment:
                continue

            words = [w for w in _tokens(fragment)]
            content = [w for w in words if _is_content(w)]
            if not content:
                # Nothing but filler — "general engineering" keeps "engineering", but a
                # fragment of pure stopwords contributes nothing rather than an empty term.
                continue

            # Already keyword-shaped: keep it verbatim, because the vendor's own phrasing
            # ("wire rope", "structured cabling") is usually better than anything we derive.
            if len(words) <= _MAX_WORDS and all(_is_content(w) or w in _STOPWORDS for w in words):
                add(" ".join(words))

            # strict=False on purpose: the offset slice is SHORTER by one, which is the point
            # of pairing adjacent words. strict=True would raise on every multi-word term.
            for first, second in zip(content, content[1:], strict=False):
                add(f"{first} {second}")
            for word in content:
                add(word)

    return out
