"""How a vendor's capability phrase is matched against a tender.

Written against a measured production failure, and the numbers below are measurements rather
than illustrations. A live workspace had six capability keywords and the opt-in gate switched
on. Of 581 open tenders the gate kept **7**. The vendor manufactures steel wire rope; the
corpus held ~90 rope, crane, mine and lift tenders. Recall was 0.08 and nothing reported a
problem, because a gate that excludes everything looks exactly like a strict gate working.

The cause was that a multi-word keyword was matched as a literal substring: the keyword
"steel wire rope manufacturing" cannot occur inside "Steel Wire Rope Sling 50mm", so the
vendor's single most important term matched almost nothing. A user-authored rule that
silently matches nothing is still the silent-miss failure (ET-7) — the rule is named and
visible, but its emptiness is not.

After the change, measured on the same 581 tenders with the same six keywords:
kept 97, precision 0.91, recall 0.98.
"""

from __future__ import annotations

from app.deterministic.discovery import Rule, evaluate_gate, keyword_relevance

# The vendor's real keywords, verbatim — including the typo, which is load-bearing evidence
# for the dead-keyword test at the bottom.
KEYWORDS = ["steel wire rope manufacturing", "expertise in elevator", "crane",
            "oil indutry", "mines", "general engineering"]


def tender(title: str, categories: list[str] | None = None, authority: str = "Indian Railways"):
    return {"title": title, "category_codes": categories or [], "authority": authority}


def kept(title: str, categories: list[str] | None = None) -> bool:
    """True when the opt-in keyword gate would let this tender into the feed."""
    return keyword_relevance(tender(title, categories), KEYWORDS).band != "low"


class TestTheCapabilityPhraseThatMatchedNothing:
    """Each of these is a real title from the live corpus that the substring rule excluded."""

    def test_a_rope_sling_reaches_a_rope_manufacturer(self):
        assert kept("Mechanically Crimping Steel Wire Rope Sling With End Eye Loops 50mm")

    def test_a_title_missing_one_of_the_phrase_words_still_matches(self):
        # "steel" is absent. Requiring every word of the phrase kept recall at 0.37; allowing
        # one miss took it to 0.98. A buyer does not repeat the vendor's own wording.
        assert kept("Safety Wire Rope Assembly. For Ir Fiat Bogie.")

    def test_the_product_written_as_one_word(self):
        # Indian portals run product words together. "wire" must be able to open "wirerope".
        assert kept("Category: Timber Shore Soft Wood , Wirerope Steel Galvanished 20mm")

    def test_a_phrase_spanning_title_and_category(self):
        assert kept("Supply as per attached list", ["Steel Wire Rope 10 Mm"])


class TestItStillRefusesTheThingsItAlwaysRefused:
    """Widening a gate is the safe direction under ET-7, but not at any price: these are the
    'wire' tenders a rope manufacturer must not be shown."""

    def test_fencing_wire_is_not_a_wire_rope(self):
        assert not kept("PCC Pole, Barbed Wire 26 Kg per Bundle, Aggregate, Cement, Sand")

    def test_welding_consumable_is_not_a_wire_rope(self):
        assert not kept("Solid Mig/mag Welding Filler Wire 1.2mm Dia Class VII")

    def test_network_cabling_is_not_a_wire_rope(self):
        assert not kept("Connector RJ 45, Cable D-Link Cat-6 Outdoor, LAN Tester, Crimping Tools")

    def test_a_single_shared_word_never_carries_a_two_word_phrase(self):
        # "general engineering" must not fire on "general" alone, or the phrase degrades into
        # its most common word. This is why the floor is two, not all-but-one.
        assert not kept("General Purpose Cleaning Contract for Office Premises")

    def test_a_suffix_never_matches_at_four_letters(self):
        # The classic false positive the one-direction compound rule exists to prevent:
        # "rope" must not find "Europe".
        assert not kept("Study Tour to Europe for Departmental Officers")


class TestTheGateItself:
    """`keyword_match_required` fires — i.e. EXCLUDES — only when the band is low."""

    RULE = Rule(name="Only my capability keywords", kind="keyword_match_required",
                enabled=True, spec={"keywords": KEYWORDS})

    def test_a_relevant_tender_is_in_scope(self):
        result = evaluate_gate(tender("Steel Wire Rope For Hoisting In EOT Cranes"), [self.RULE])
        assert result.in_scope is True
        assert result.excluded_by_rule is None

    def test_an_irrelevant_tender_is_excluded_and_names_the_rule(self):
        result = evaluate_gate(tender("Supply of Desktop Computers and Monitors"), [self.RULE])
        assert result.in_scope is False
        assert result.excluded_by_rule == "Only my capability keywords"

    def test_an_empty_keyword_list_is_still_inert(self):
        # Unchanged behaviour, restated because widening the matcher must not weaken this: a
        # vendor who enables the gate before filling in a profile keeps their whole feed.
        empty = Rule(name="gate", kind="keyword_match_required",
                     enabled=True, spec={"keywords": []})
        assert evaluate_gate(tender("Anything at all"), [empty]).in_scope is True


class TestADeadKeywordIsInvisible:
    """Not a bug in the matcher — a finding the matcher makes visible, and the reason a
    per-keyword reach figure belongs in the UI.

    "oil indutry" is a typo in the vendor's own profile. It matched 0 of 581 open tenders
    before this change and matches 0 after it, and nothing anywhere says so. A keyword that
    can never fire looks identical to a keyword whose segment happens to be quiet this week.
    """

    def test_a_misspelt_keyword_matches_its_own_subject(self):
        assert keyword_relevance(tender("Supply of Crude Oil Industry Pipeline Fittings"),
                                 ["oil indutry"]).band == "low"

    def test_the_corrected_spelling_would_have_matched(self):
        assert keyword_relevance(tender("Supply of Crude Oil Industry Pipeline Fittings"),
                                 ["oil industry"]).band != "low"


# The second live workspace's keywords (Usha Martin Limited, 2026-09-14). Product phrases,
# not capability prose — which is exactly the case where "all but one word, anywhere" is
# too loose: every rope phrase collapses to "wire" and "rope" somewhere in the title.
UML = ["wire rope", "steel wire rope", "galvanized wire rope", "ungalvanized wire rope",
       "wire rope sling", "stranded steel wire", "MIG welding wire"]


def band(title: str, categories: list[str] | None = None) -> str:
    return keyword_relevance(tender(title, categories), UML).band


class TestAPhraseMustHoldTogether:
    """Live HIGH rows from 2026-09-14 that were not wire-rope tenders, and their neighbours
    that are."""

    def test_wire_in_one_line_item_and_rope_in_another_is_not_a_wire_rope(self):
        # A BRO plywood/nails BOQ. "binding wire" and "coir rope" are nine tokens apart and
        # belong to different items; five rope keywords fired and the row ranked HIGH.
        # "stranded steel wire" may still hit "Mild Steel Binding Wire" (two of three words,
        # head noun present) — that is one honest partial match, and one keyword in the
        # title is MEDIUM. What must not happen is any ROPE phrase firing.
        title = ("Category: Moisture Resistant Or Wbr Grade Plywood , Woodenscantling Size "
                 "6 Inch X 4 Inch , Nails 2 Inch , Wooden Planks Size 12 Inch X 1.6 Inch , "
                 "binding Wire Isi 16-20 Mild Steel Binding Wire , Heavy Dutyshuttering "
                 "Tape , Jute Brown Coir Rope")
        m = keyword_relevance(tender(title), UML)
        assert m.band != "high"
        assert not any("rope" in t for t in m.matched_terms), m.matched_terms

    def test_a_wire_rope_line_inside_a_multi_item_bid_still_matches(self):
        # Same shape of title, but "Rope Wire, 6mm, Glvnzd Stl" IS a wire-rope item.
        title = ("Category: Cable, 1.1 Kv, 6c, Copper, Pvc, 2.5mm2 Armoured , Pull Cord "
                 "Switch , Rope Wire,6mm, Glvnzd Stl 6 X 19 Flexible , Pilot Relay 12 V Dc")
        assert band(title) != "low"

    def test_a_size_token_between_the_words_is_tolerated(self):
        assert band("Wire 6mm Rope Galvanised For Crane") != "low"

    def test_steel_and_wire_adjacent_without_rope_do_not_carry_a_rope_phrase(self):
        # "mild steel binding wire" hits two of "steel wire rope"'s three words, adjacently.
        # The phrase names a rope; without its head noun it has not matched. ("stranded
        # steel wire" legitimately may — its head noun IS wire.)
        m = keyword_relevance(tender("Mild Steel Binding Wire 18 Swg 25 Kg Coil"), UML)
        assert "steel wire rope" not in m.matched_terms
        assert "galvanized wire rope" not in m.matched_terms
        assert "wire rope" not in m.matched_terms

    def test_the_head_noun_may_arrive_run_together(self):
        # "wirerope" carries "rope" as a suffix behind another word of the same phrase.
        assert band("Wirerope Steel Galvanised 20mm") != "low"

    def test_a_suffix_alone_is_still_not_the_head_noun(self):
        assert band("Study Tour To Europe For Steel Officers") == "low"

    def test_an_exact_category_string_still_matches(self):
        assert band("Supply as per attached list", ["Steel Wire Rope 10 Mm"]) == "high"


class TestAStandardNumberIsTheOnlyReachableTerm:
    """A live tender that no product phrase can reach, and the reason the Capability tab's
    standards belong in the ranking vocabulary.

    "Safety Wire Cable For Mounting Retention Tank ... 7x7 ... Is : 2266 - 2002, Grade 1770"
    is a wire rope: 7x7 is a rope construction, 1770 a rope tensile grade, and IS 2266 one of
    UML's own registered GeM categories. The word "rope" does not occur in the title at all,
    so every rope phrase misses it by construction — measured against _PHRASE_SLACK of 2, 3,
    4, 6 and 10, it bands low every time. Loosening the phrase rule cannot reach it; only the
    standard number can, and that arrives from `product_specs.standard_ref` via
    `ingest._capability`.
    """

    TITLE = ("Safety Wire Cable For Mounting Retention Tank Size Dia8mm - 7x7 Length 3000mm "
             "As Per Din3055 Stainless Steel Or Is : 2266 - 2002, Grade 1770, Material "
             "Aisi304 As Per Specn. Is : 2266 - 2002, Grade 1770, Material Aisi304")

    def test_the_profile_phrases_alone_cannot_reach_it(self):
        assert keyword_relevance(tender(self.TITLE), UML).band == "low"

    def test_the_standard_number_reaches_it(self):
        m = keyword_relevance(tender(self.TITLE), [*UML, "IS 2266"])
        assert m.band != "low"
        assert "is 2266" in m.matched_terms

    def test_a_different_standard_number_does_not(self):
        # The bolt BOQ that cites IS 208-1996 must not answer to IS 2266.
        bolts = "ALDROP BOLT ALUM 300MM ROD DIA 16MM IS 208-1996, GI WIREMESH 0.40MM DIA WIRE"
        assert keyword_relevance(tender(bolts), [*UML, "IS 2266"]).band == "low"
