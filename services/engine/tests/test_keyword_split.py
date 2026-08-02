"""Breaking long-tail keywords into terms a tender title might contain.

Written against a live incident: a workspace entered
"expertise in elevator / crane / oil indutry/ mines / general engineering" as ONE keyword,
switched on the opt-in gate, and all 335 swept tenders were hidden. Matching is per whole term.
"""

from __future__ import annotations

from app.deterministic.keywords import split_long_tail


class TestTheLiveFailure:
    def test_the_exact_string_that_emptied_a_feed(self):
        got = split_long_tail(
            ["expertise in elevator / crane / oil indutry/ mines / general engineering"]
        )
        # The filler lead-in is stripped and each slash-separated thing becomes its own term.
        assert "elevator" in got
        assert "crane" in got
        assert "mines" in got
        assert "engineering" in got
        # And nothing longer than a keyword survives.
        assert all(len(k.split()) <= 3 for k in got), got

    def test_a_four_word_term_yields_the_pair_that_matters(self):
        got = split_long_tail(["steel wire rope manufacturing"])
        # "wire rope" is the term a GeM title actually contains; it must be offered, and offered
        # before the weaker single words so a caller that truncates keeps the good one.
        assert "wire rope" in got
        assert got.index("wire rope") < got.index("rope")
        # "manufacturing" is commerce vocabulary and never stands alone.
        assert "manufacturing" not in got


class TestWhatItRefusesToEmit:
    def test_commerce_words_never_stand_alone(self):
        # Each of these matches a large fraction of a national portal by itself.
        assert split_long_tail(["supply of various miscellaneous goods"]) == []
        assert split_long_tail(["general services"]) == []

    def test_pure_filler_produces_nothing_rather_than_an_empty_term(self):
        assert split_long_tail(["of the and"]) == []
        assert split_long_tail([""]) == []
        assert split_long_tail(["   "]) == []
        assert split_long_tail(["///,,,"]) == []

    def test_none_and_empty_input(self):
        assert split_long_tail(None) == []
        assert split_long_tail([]) == []

    def test_short_tokens_and_bare_numbers_are_dropped(self):
        # "hp" is an abbreviation, "20" is a quantity; neither identifies a product.
        assert split_long_tail(["hp 20"]) == []


class TestWhatItPreserves:
    def test_a_good_two_word_term_survives_verbatim(self):
        # The vendor's own phrasing beats anything derived from it.
        got = split_long_tail(["wire rope"])
        assert got[0] == "wire rope"

    def test_a_single_word_keyword_is_returned_unchanged(self):
        assert split_long_tail(["cctv"]) == ["cctv"]

    def test_separators_are_all_honoured(self):
        got = split_long_tail(["cctv, surveillance; networking\nrope & cable and hoist"])
        for term in ("cctv", "surveillance", "networking", "rope", "cable", "hoist"):
            assert term in got, f"{term} missing from {got}"

    def test_output_is_deduplicated_and_order_is_stable(self):
        got = split_long_tail(["wire rope", "wire rope", "rope wire"])
        assert len(got) == len(set(got))
        assert got == split_long_tail(["wire rope", "wire rope", "rope wire"])

    def test_case_is_normalised(self):
        assert split_long_tail(["Wire ROPE"]) == ["wire rope", "wire", "rope"]


def test_the_model_component_is_importable_the_way_the_route_imports_it():
    """`app` and `pipeline` are SIBLING top-level packages.

    The route first used `from ..pipeline import keywords`, which reaches beyond the top-level
    package and raises ImportError. The endpoint caught it as "model unavailable" and served the
    deterministic split — so the feature shipped switched off, worked in every test, and said so
    only in a log line. `app/discovery/` gets away with `...pipeline` because it is one level
    deeper; nothing generalises that to `app/`.
    """
    import importlib

    mod = importlib.import_module("pipeline.keywords")
    assert callable(mod.suggest)

    # And the route module must not have reverted to the relative form.
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "app" / "analyze_routes.py").read_text()
    assert "from ..pipeline import" not in src, (
        "relative import from app/ to pipeline/ raises at runtime and degrades silently"
    )
