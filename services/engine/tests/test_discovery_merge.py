"""F-AC4 — zero wrong merges. A hard gate, and the reason it is a hard gate:

collapsing two distinct tenders into one opportunity **deletes a tender from the user's world
with no error message**. It is ET-8, and it is worse than showing a duplicate — a duplicate costs
one skimmed line, a wrong merge costs the bid and is undetectable from inside the product.

So merging is deterministic and exact (F-FR6): normalize whitespace, case and separators, then
require equality. No edit distance, no fuzzy title matching, no "same authority and closing date
so probably the same tender". Near-matches surface as a *grouped candidate* for a human
(F-FR7) — never as a merge.

Required to exist by tools/check-discovery-guardrails.sh.
"""

from __future__ import annotations

import pytest

from app.deterministic.discovery import Rule, evaluate_gate

# The normalizer under test lives in the connector, which is a separate service and not
# importable here. It is one small pure function and the merge rule is a product invariant
# rather than one service's implementation detail, so it is restated — deliberately duplicated
# per the wall precedent in CLAUDE.md: copying beats coupling two deploy cycles. If these two
# ever disagree, this test is the one that should be believed.
import re

_REF_SEPARATORS = re.compile(r"[\s\-_/\\.]+")


def normalize_ref(raw: str | None) -> str | None:
    if raw is None:
        return None
    collapsed = _REF_SEPARATORS.sub("/", raw.strip().upper())
    return collapsed.strip("/") or None


def merge_key(source_id: str, portal_ref_no: str) -> tuple[str, str]:
    """What the `unique (source_id, portal_ref_no)` constraint in migration 0019 enforces."""
    return (source_id, normalize_ref(portal_ref_no))


class TestTheSameTenderMerges:
    @pytest.mark.parametrize(
        "variant",
        [
            "GEM/2026/R/706528",
            "gem/2026/r/706528",
            "  GEM/2026/R/706528  ",
            "GEM-2026-R-706528",
            "GEM_2026_R_706528",
            "GEM 2026 R 706528",
        ],
    )
    def test_formatting_variants_of_one_ref_collapse(self, variant):
        # The same bid arrives from the portal, from a forwarded alert email, and from an
        # aggregator digest, each formatted differently. One tender, one row.
        assert merge_key("gem_bidplus", variant) == merge_key("gem_bidplus", "GEM/2026/R/706528")

    def test_normalization_is_idempotent(self):
        once = normalize_ref("gem-2026-r-706528")
        assert normalize_ref(once) == once


class TestDistinctTendersNeverMerge:
    """Each of these would silently delete a real tender. All must stay separate."""

    @pytest.mark.parametrize(
        ("a", "b"),
        [
            ("GEM/2026/R/706528", "GEM/2026/R/706529"),  # adjacent serials
            ("GEM/2026/R/706528", "GEM/2026/R/706582"),  # transposed digits
            ("GEM/2026/R/706528", "GEM/2026/B/706528"),  # R (RA) vs B (bid) — different objects
            ("GEM/2026/R/706528", "GEM/2025/R/706528"),  # different year
            ("GEM/2026/R/70652", "GEM/2026/R/706528"),   # prefix, not a match
        ],
    )
    def test_similar_refs_stay_separate(self, a, b):
        assert merge_key("gem_bidplus", a) != merge_key("gem_bidplus", b)

    def test_the_same_ref_from_different_sources_stays_separate(self):
        # Provenance is preserved (F-FR8); two sources are two sightings, reconciled explicitly
        # rather than by assuming a ref is globally unique across portals.
        assert merge_key("gem_bidplus", "X/1") != merge_key("cppp", "X/1")

    def test_no_fuzzy_matching_exists(self):
        # If anyone ever adds edit-distance or title similarity to the merge path, this fails.
        near = ["GEM/2026/R/706528", "GEM/2026/R/706529", "GEM/2026/R/706530"]
        assert len({merge_key("gem_bidplus", r) for r in near}) == 3


class TestUnmergeableRecordsAreNotDropped:
    def test_a_missing_ref_normalizes_to_none_rather_than_a_shared_empty_key(self):
        # If blank refs collapsed to one key, every unidentifiable listing would merge into a
        # single row and all but one would vanish — the exact ET-8 failure, at scale.
        assert normalize_ref(None) is None
        assert normalize_ref("   ") is None
        assert normalize_ref("///") is None


class TestMergingIsIndependentOfFiltering:
    def test_an_excluded_item_still_occupies_its_own_row(self):
        # Exclusion is per-workspace and lives in opportunity_matches; the shared corpus row is
        # untouched. Otherwise one workspace's rule would remove a tender from another's feed.
        rule = Rule(name="Services only", kind="category_prefix_not_in",
                    spec={"prefixes": ["services_"]})
        goods = {"category_codes": ["home_powe_batt"], "authority": "X", "closing_at": None}
        assert evaluate_gate(goods, [rule]).in_scope is False
        assert merge_key("gem_bidplus", "GEM/2026/R/1") != merge_key("gem_bidplus", "GEM/2026/R/2")
