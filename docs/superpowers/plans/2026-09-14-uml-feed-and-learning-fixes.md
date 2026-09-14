# UML Opportunity Feed & Learning Tab Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the opportunity feed from silently un-ranking cached rows, evaluate every open tender instead of the first 1000, stop multi-item BOQ titles from ranking HIGH on scattered words, feed the Capability tab's vocabulary into the ranking, and put the past-bid uploader where a user looking for "the knowledge base" will find it.

**Architecture:** Four engine changes in `services/engine` (bulk upsert grouping, recompute paging, phrase-proximity matching, capability-vocabulary merge), one web change in `apps/web` (uploader placement + self-refresh), then a deploy + live re-measurement against the "Usha Martin Limited" workspace. Every engine change is a pure-function or db-helper edit with a unit test; nothing new touches a model call or a portal.

**Tech Stack:** Python 3.12 / FastAPI / pytest via `uv` (engine); Next.js 15 / TypeScript / Vitest via `pnpm` (web); Supabase PostgREST.

**Evidence this plan is built on (measured 2026-09-14, workspace `4bcdd285-5957-4c6c-ae47-7671569b1c25`):**

| Fact | Value |
|---|---|
| Open Indian opportunities in corpus | 1,251 (recompute window is 1,000) |
| Match rows with `relevance_band IS NULL` | 3,192 of 6,694 |
| Open in-scope rows unbanded, touched by the latest run | 14 of 22 |
| Open in-scope HIGH by keyword on a plywood/nails BOQ | 1 (title carries "binding wire" and "coir rope" nine tokens apart) |
| `past_bids` / `answers` rows | 0 / 0 (18 docs went through `/api/knowledge/ingest` instead) |

Phase gates follow CLAUDE.md: ≤5 files per phase, typecheck + lint + tests green, human approval before the next phase.

---

## Phase 1 — the feed stops un-ranking itself (engine)

### Task 1: Bulk upsert must not pad a cache-hit row with NULL relevance columns

**Root cause.** `relevance.bands_for` skips any in-scope row whose input hash already matches (nothing to recompute), so that row's dict carries no relevance keys. `db.upsert_opportunity_matches` then pads every row to the union of all keys with `None` — required because PostgREST rejects ragged bulk bodies — and `resolution=merge-duplicates` writes those explicit NULLs over the stored band and hash. Net effect: the run that *reuses* a cached band is the run that erases it.

**Files:**
- Modify: `services/engine/app/db.py:1312-1333` (`upsert_opportunity_matches`)
- Create: `services/engine/tests/test_match_upsert.py`

- [ ] **Step 1: Write the failing tests**

```python
"""A bulk upsert must never turn 'I did not touch this column' into 'set it to NULL'.

`relevance.bands_for` skips rows whose input hash is unchanged, so those rows carry no
relevance keys at all. PostgREST needs every object in one bulk body to share a key set, and
the old fix — pad with None — wrote an explicit NULL over the cached band on every run that
reused it. Measured 2026-09-14: 3,192 of 6,694 match rows in one workspace were band-NULL,
including 14 open wire-rope tenders the latest run had just touched.
"""

from __future__ import annotations

from app import db


def _capture(monkeypatch):
    posted: list[list[dict]] = []

    def fake_rest(method, path, *, params=None, json=None, prefer=None):
        assert method == "POST" and path == "opportunity_matches"
        posted.append(json)
        return []

    monkeypatch.setattr(db, "_rest", fake_rest)
    return posted


def test_a_row_without_relevance_keys_is_not_padded_with_null_bands(monkeypatch):
    posted = _capture(monkeypatch)
    banded = {"opportunity_id": "a", "state": "in_scope",
              "relevance_band": "high", "relevance_input_hash": "h1"}
    cached = {"opportunity_id": "b", "state": "in_scope"}

    db.upsert_opportunity_matches("ws", [banded, cached])

    by_id = {r["opportunity_id"]: r for batch in posted for r in batch}
    assert "relevance_band" not in by_id["b"], "an untouched column must stay untouched"
    assert "relevance_input_hash" not in by_id["b"]
    assert by_id["a"]["relevance_band"] == "high"
    assert by_id["a"]["workspace_id"] == "ws" and by_id["b"]["workspace_id"] == "ws"


def test_every_request_body_has_a_uniform_key_set(monkeypatch):
    # PostgREST answers a ragged bulk body with a bare 400 and no column name.
    posted = _capture(monkeypatch)
    rows = [
        {"opportunity_id": "a", "state": "in_scope", "relevance_band": "low"},
        {"opportunity_id": "b", "state": "excluded", "excluded_by_rule": "r"},
        {"opportunity_id": "c", "state": "in_scope", "relevance_band": "high"},
    ]
    db.upsert_opportunity_matches("ws", rows)
    for batch in posted:
        assert len({frozenset(r) for r in batch}) == 1
    assert sum(len(b) for b in posted) == 3


def test_an_explicit_none_is_still_written(monkeypatch):
    # The keyword fallback deliberately writes relevance_input_hash=None ("not a final
    # answer"). Grouping by key set must keep that explicit null, not strip it.
    posted = _capture(monkeypatch)
    db.upsert_opportunity_matches("ws", [
        {"opportunity_id": "a", "state": "in_scope",
         "relevance_band": "low", "relevance_input_hash": None},
    ])
    assert posted[0][0]["relevance_input_hash"] is None
    assert "relevance_input_hash" in posted[0][0]


def test_empty_input_posts_nothing(monkeypatch):
    posted = _capture(monkeypatch)
    assert db.upsert_opportunity_matches("ws", []) == 0
    assert posted == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd services/engine && uv run pytest tests/test_match_upsert.py -v`
Expected: `test_a_row_without_relevance_keys_is_not_padded_with_null_bands` FAILS on `"relevance_band" not in by_id["b"]`; the other three pass (they pin current behaviour that must survive).

- [ ] **Step 3: Replace the padding with grouping by key set**

Replace the whole function body in `services/engine/app/db.py`:

```python
def upsert_opportunity_matches(workspace_id: str, rows: list[dict]) -> int:
    """Bulk upsert, one request per distinct key set.

    PostgREST rejects a bulk body whose objects have differing keys with a bare `400`. The
    payload here is legitimately ragged: `relevance.bands_for` skips rows whose input hash is
    unchanged, so those rows carry no relevance keys at all. The previous answer — pad every
    row to the union with None — wrote an explicit NULL over the cached band and hash under
    `merge-duplicates`, so the run that REUSED a band was the run that erased it. Measured
    2026-09-14: 3,192 of 6,694 rows in one workspace band-NULL, 14 of them open wire-rope
    tenders the latest run had just touched.

    Grouping keeps each request uniform without inventing a value for a column the caller
    never mentioned. A key the caller set to None is still sent as None — the keyword
    fallback writes `relevance_input_hash: None` on purpose and must keep doing so.
    """
    if not rows:
        return 0
    groups: dict[frozenset[str], list[dict]] = {}
    for r in rows:
        groups.setdefault(frozenset(r), []).append(r)
    for group in groups.values():
        _rest(
            "POST",
            "opportunity_matches",
            params={"on_conflict": "workspace_id,opportunity_id"},
            json=[{**r, "workspace_id": workspace_id} for r in group],
            prefer="resolution=merge-duplicates,return=minimal",
        )
    return len(rows)
```

- [ ] **Step 4: Run the new tests and the existing recompute tests**

Run: `cd services/engine && uv run pytest tests/test_match_upsert.py tests/test_discovery_markets.py tests/test_discovery_rules.py -v`
Expected: all PASS. (`test_discovery_markets.py` stubs `upsert_opportunity_matches` entirely, so it is unaffected; run it anyway to prove that.)

- [ ] **Step 5: Add the end-to-end guard in the recompute**

Append to `services/engine/tests/test_discovery_markets.py`:

```python
# ---------- a cached band must survive the next run ----------

def test_a_hash_matched_row_leaves_recompute_without_relevance_keys(monkeypatch):
    """The row `bands_for` skips must reach the upsert with NO relevance keys — not with
    None in them. Task 1's upsert grouping only helps if the recompute honours that."""
    from app.discovery import ingest as ing
    from app.discovery import relevance

    captured: dict = {}
    statement, keywords = "Manufacturer of steel wire rope", ["wire rope"]
    opp = {"id": "o-1", "market": "IN", "title": "Steel Wire Rope 16mm", "category_codes": []}

    monkeypatch.setattr(ing, "_capability", lambda ws: (statement, keywords))
    monkeypatch.setattr(ing, "_rules_for", lambda ws, kw: [])
    monkeypatch.setattr(ing, "_profile_turnover_inr", lambda ws: None)
    monkeypatch.setattr(ing.db, "get_workspace_market", lambda ws: "IN")
    monkeypatch.setattr(ing.db, "get_workspace_markets", lambda ws: ["IN"])
    monkeypatch.setattr(ing, "_enrich_documents", lambda items, budget: 0)
    monkeypatch.setattr(ing.db, "get_opportunities",
                        lambda **kw: [opp] if kw.get("offset", 0) == 0 else [])
    monkeypatch.setattr(
        ing.db, "get_relevance_hashes",
        lambda ws: {"o-1": relevance.input_hash(statement, keywords, opp, "en")},
    )

    def fake_upsert(ws, rows):
        captured["rows"] = rows
        return len(rows)

    monkeypatch.setattr(ing.db, "upsert_opportunity_matches", fake_upsert)

    ing.recompute_matches("ws-1", doc_budget=0)

    row = captured["rows"][0]
    assert row["state"] == "in_scope"
    assert "relevance_band" not in row
    assert "relevance_input_hash" not in row
```

Run: `cd services/engine && uv run pytest tests/test_discovery_markets.py -k hash_matched -v`
Expected: PASS (the recompute already omits the keys; this pins it so nobody reintroduces padding upstream).

- [ ] **Step 6: Commit**

```bash
git add services/engine/app/db.py services/engine/tests/test_match_upsert.py services/engine/tests/test_discovery_markets.py
git commit -m "fix(discovery): a cache-hit row no longer has its relevance band nulled by the bulk upsert

bands_for skips rows whose input hash is unchanged, so they carry no relevance keys.
upsert_opportunity_matches padded them to the union key set with None and
merge-duplicates wrote that NULL over the cached band. Group by key set instead.
3,192 of 6,694 rows in the UML workspace were band-NULL from this."
```

### Task 2: Recompute pages to exhaustion instead of stopping at 1000

**Root cause.** `db.get_opportunities(limit=RECOMPUTE_WINDOW, open_only=True)` returns the 1,000 soonest-closing open rows. India holds 1,251 open. The remainder is never gated or ranked; the code logs a warning and returns `window_saturated: True`, which nothing reads. The model budget lives in `bands_for` (40 rows/run) and the document budget in `_enrich_documents`, so paging the *gate* costs nothing extra.

**Files:**
- Modify: `services/engine/app/db.py:1173-1211` (`get_opportunities`)
- Modify: `services/engine/app/discovery/ingest.py:294-404` (`recompute_matches`)
- Modify: `services/engine/tests/test_discovery_markets.py:320-390` (the two window tests)

- [ ] **Step 1: Rewrite the two window tests to demand exhaustion**

Replace `test_a_full_window_is_reported_as_saturated` and `test_a_partial_window_is_not_saturated` in `services/engine/tests/test_discovery_markets.py` with:

```python
# ---------- the recompute must evaluate every open row, not the first page ----------
#
# `recompute_matches` used to read ONE window of open opportunities and report
# `window_saturated` when it filled. Nothing read that flag. Measured 2026-09-14: India held
# 1,251 open against a 1,000 window, so ~250 open tenders were never gated or ranked, and
# 22 open wire-rope tenders sat in the feed unbanded. Paging the gate is free — the model
# budget lives in `bands_for` and the document budget in `_enrich_documents`.

def _stub_recompute(monkeypatch, ing, corpus: list[dict]):
    monkeypatch.setattr(ing, "_capability", lambda ws: ("", []))
    monkeypatch.setattr(ing, "_rules_for", lambda ws, kw: [])
    monkeypatch.setattr(ing, "_profile_turnover_inr", lambda ws: None)
    monkeypatch.setattr(ing.db, "get_workspace_market", lambda ws: "IN")
    monkeypatch.setattr(ing.db, "get_workspace_markets", lambda ws: ["IN"])
    monkeypatch.setattr(ing.db, "upsert_opportunity_matches", lambda ws, rows: len(rows))
    monkeypatch.setattr(ing, "_enrich_documents", lambda items, budget: 0)
    monkeypatch.setattr(ing, "evaluate_gate",
                        lambda o, r: type("G", (), {"in_scope": False,
                                                    "excluded_by_rule": "test"})())
    calls: list[dict] = []

    def fake_get(*, limit, markets, open_only, offset=0):
        calls.append({"limit": limit, "offset": offset, "open_only": open_only})
        return corpus[offset:offset + limit]

    monkeypatch.setattr(ing.db, "get_opportunities", fake_get)
    return calls


def test_a_corpus_larger_than_one_page_is_evaluated_in_full(monkeypatch):
    from app.discovery import ingest as ing

    corpus = [{"id": f"o-{i}", "market": "IN"} for i in range(ing.RECOMPUTE_WINDOW + 251)]
    calls = _stub_recompute(monkeypatch, ing, corpus)

    result = ing.recompute_matches("ws-1")

    assert result["evaluated"] == len(corpus)
    assert result["pages"] == 2
    assert [c["offset"] for c in calls] == [0, ing.RECOMPUTE_WINDOW]
    assert all(c["open_only"] for c in calls)


def test_a_corpus_that_exactly_fills_a_page_reads_one_more_empty_page(monkeypatch):
    # The loop stops on a SHORT page. An exactly-full page is not proof of the end.
    from app.discovery import ingest as ing

    corpus = [{"id": f"o-{i}", "market": "IN"} for i in range(ing.RECOMPUTE_WINDOW)]
    calls = _stub_recompute(monkeypatch, ing, corpus)

    result = ing.recompute_matches("ws-1")

    assert result["evaluated"] == ing.RECOMPUTE_WINDOW
    assert len(calls) == 2 and calls[1]["offset"] == ing.RECOMPUTE_WINDOW


def test_a_small_corpus_is_one_page(monkeypatch):
    from app.discovery import ingest as ing

    calls = _stub_recompute(monkeypatch, ing, [{"id": "o-1", "market": "IN"}])
    result = ing.recompute_matches("ws-1")
    assert result["evaluated"] == 1 and result["pages"] == 1 and len(calls) == 1
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd services/engine && uv run pytest tests/test_discovery_markets.py -k "page" -v`
Expected: FAIL with `TypeError: fake_get() got an unexpected keyword argument` or `KeyError: 'pages'`.

- [ ] **Step 3: Add `offset` and a stable tiebreak to `get_opportunities`**

In `services/engine/app/db.py`, change the signature and the params:

```python
def get_opportunities(
    limit: int = 500, markets: list[str] | None = None, open_only: bool = False,
    offset: int = 0,
) -> list[dict]:
```

and, keeping the docstring, replace the body's first line:

```python
    # `id` as a tiebreak: many rows share a closing timestamp, and a page boundary that falls
    # inside a tie would hand the same row to two pages and skip another (known-pitfalls,
    # "a keyset cursor on a non-unique column").
    params = {
        "select": "*", "order": "closing_at.asc,id.asc",
        "limit": str(limit), "offset": str(offset),
    }
```

- [ ] **Step 4: Page in `recompute_matches`**

In `services/engine/app/discovery/ingest.py`, replace the block from `opportunities = db.get_opportunities(` through the `if window_saturated:` warning (lines ~322-340) with:

```python
    # Every open row, one page at a time. The gate is pure Python and the model budget lives
    # in `relevance.bands_for` (DEFAULT_BUDGET per run), so paging the gate costs nothing;
    # NOT paging it left ~250 open Indian tenders unevaluated on 2026-09-14 while a warning
    # nobody read said so. Offset paging on a live table can hand one row to two pages if a
    # sweep inserts mid-run; the upsert is idempotent, so the cost is a duplicate evaluation.
    # ponytail: offset paging, keyset on (closing_at, id) if the corpus reaches ~20k open rows
    opportunities: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = db.get_opportunities(
            limit=RECOMPUTE_WINDOW, markets=watched, open_only=True, offset=offset,
        )
        opportunities.extend(page)
        if len(page) < RECOMPUTE_WINDOW:
            break
        offset += RECOMPUTE_WINDOW
    pages = offset // RECOMPUTE_WINDOW + 1
```

and replace the two result keys at the bottom of the function:

```python
        "documents_fetched": 0,
        "pages": pages,
        "page_size": RECOMPUTE_WINDOW,
    }
```

Also delete the now-dead comment block above `RECOMPUTE_WINDOW = ...` (line ~54) that says the recompute "reports `window_saturated`", and reword the constant's comment to: `#: Page size for the recompute's read of the open corpus. Not a cap: the loop pages to exhaustion.`

- [ ] **Step 5: Run the whole engine suite**

Run: `cd services/engine && uv run pytest -q && uv run ruff check`
Expected: all pass, `ruff` clean. If `grep -rn window_saturated services/engine tests apps` returns anything other than this plan, fix that reference.

- [ ] **Step 6: Commit**

```bash
git add services/engine/app/db.py services/engine/app/discovery/ingest.py services/engine/tests/test_discovery_markets.py
git commit -m "fix(discovery): recompute pages the open corpus to exhaustion

India holds 1,251 open opportunities against a 1,000-row window; the remainder was
never gated or ranked and a warning nobody read said so. Page on
(closing_at, id); the model and document budgets are unchanged."
```

**Phase 1 gate:** `uv run pytest` green, `uv run ruff check` clean. Post the evidence block and wait for approval before Phase 2.

---

## Phase 2 — the feed ranks on the right words (engine)

### Task 3: A multi-word keyword must hold together in the title

**Root cause.** `_term_hits` reduces "galvanized wire rope" to content words and accepts all-but-one hitting anywhere in the *union* of title, authority and category tokens. A BOQ title listing plywood, nails, "Mild Steel Binding Wire" and "Jute Brown Coir Rope" satisfies five of UML's keywords at once, and two matched keywords is the HIGH threshold. Fix: the hitting words must sit inside a short window of the same token sequence, and the phrase's head noun (its last content word) must be one of them.

**Files:**
- Modify: `services/engine/app/deterministic/discovery.py:214-336` (`_tokens`, `_term_hits`, `keyword_relevance`; add `_sequence`, `_phrase_hits`, `_head_hits`)
- Modify: `services/engine/tests/test_keyword_matching.py`

- [ ] **Step 1: Write the failing tests**

Append to `services/engine/tests/test_keyword_matching.py`:

```python
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
```

- [ ] **Step 2: Run to verify the right ones fail**

Run: `cd services/engine && uv run pytest tests/test_keyword_matching.py -v`
Expected: `test_wire_in_one_line_item_and_rope_in_another_is_not_a_wire_rope` FAILS (band is "high" and rope phrases are in `matched_terms`) and `test_steel_and_wire_adjacent_without_rope_do_not_carry_a_rope_phrase` FAILS (`"steel wire rope"` is matched); everything else passes, including every pre-existing test.

- [ ] **Step 3: Implement proximity + head-noun matching**

In `services/engine/app/deterministic/discovery.py`, add after `_tokens`:

```python
def _sequence(text: str) -> list[str]:
    """Words in order. `_tokens` is the set; the phrase rule needs positions."""
    return _WORD.findall(text.lower())


#: A phrase's hitting words must sit within (phrase length + this) tokens of each other in
#: ONE field sequence. Two, so a size or grade token may sit between them ("Wire 6mm Rope").
#: Without it "galvanized wire rope" matched a plywood-and-nails BOQ whose title carried
#: "binding wire" in one line item and "coir rope" in another (live HIGH, 2026-09-14).
_PHRASE_SLACK = 2


def _head_hits(words: list[str], window: set[str]) -> bool:
    """The phrase's last content word — the thing being bought — must be present.

    "steel wire rope" names a rope; "Mild Steel Binding Wire" hits two of its three words
    and is not one. A run-together token counts ("wirerope"), but only when what precedes
    the suffix is another word of the same phrase — "Europe" never qualifies.
    """
    head = words[-1]
    if _word_hits(head, window):
        return True
    others = words[:-1]
    return any(
        len(tok) > len(head) and tok.endswith(head)
        and any(_word_hits(o, {tok[: -len(head)]}) for o in others)
        for tok in window
    )


def _phrase_hits(words: list[str], seq: list[str]) -> bool:
    need = _words_required(len(words))
    span = len(words) + _PHRASE_SLACK
    for start in range(len(seq)):
        window = set(seq[start:start + span])
        if not _head_hits(words, window):
            continue
        # The head counts once, whether it hit directly or as a suffix.
        rest = sum(1 for w in words[:-1] if _word_hits(w, window))
        if rest + 1 >= need:
            return True
    return False
```

Change `_term_hits` to take the sequence for phrases:

```python
def _term_hits(
    term: str, tokens: set[str], *, seq: list[str] | None = None, code: bool = False
) -> bool:
    """One keyword against one haystack.

    (keep the existing docstring paragraphs about inflection and the 7-of-581 measurement)

    A multi-word keyword is matched against `seq` — the haystack IN ORDER — so its words must
    occur near each other and its head noun must be among them. Matching a phrase against a
    token SET was the defect this replaces: measured on the UML workspace, "steel wire rope"
    fired on a plywood BOQ because "wire" and "rope" both appeared somewhere in 40 tokens.
    """
    if " " in term:
        words = content_words(term)
        if not words:
            return False
        return _phrase_hits(words, seq if seq is not None else sorted(tokens))
    if code:
        if term in tokens:
            return True
        return any(
            len(tok) >= _MIN_CODE_STEM and term.startswith(tok) for tok in tokens
        )
    return _word_hits(term, tokens)
```

In `keyword_relevance`, build sequences and pass them:

```python
    title = (record.get("title") or "").lower()
    categories = " ".join(_category_codes(record)).lower()
    authority = (record.get("authority") or "").lower()

    title_tokens, category_tokens = _tokens(title), _tokens(categories)
    authority_tokens = _tokens(authority)
    text_tokens = title_tokens | authority_tokens | category_tokens
    # One ordered sequence so a phrase may still span the title/category boundary (a
    # multi-item bid names the product in the category and the size in the title), while
    # words from two different line items can no longer combine.
    text_seq = _sequence(title) + _sequence(authority) + _sequence(categories)
    category_seq = _sequence(categories)

    matched = tuple(
        sorted(
            {
                t
                for t in terms
                if _term_hits(t, text_tokens, seq=text_seq)
                or _term_hits(t, category_tokens, seq=category_seq, code=True)
            }
        )
    )
    if not matched:
        return KeywordMatch(band="low", matched_terms=(), language=language)

    in_category = any(
        _term_hits(t, category_tokens, seq=category_seq, code=True) for t in matched
    )
    in_title = any(_term_hits(t, title_tokens, seq=_sequence(title)) for t in matched)
```

(The rest of `keyword_relevance` — the high/medium/low decision — is unchanged.)

- [ ] **Step 4: Run the keyword suite and everything that imports the matcher**

Run: `cd services/engine && uv run pytest tests/test_keyword_matching.py tests/test_discovery_rules.py tests/test_deterministic_edges.py tests/test_cron.py -v`
Expected: all PASS. If `test_the_product_written_as_one_word` fails, `_head_hits`'s suffix branch is wrong — "wirerope" must satisfy head "rope" because "wire" is a phrase word.

- [ ] **Step 5: Replay the change against the live open rows before shipping**

The unit tests prove the two named titles. They do not prove the change has no false NEGATIVES on the other 1,142 open rows (known-pitfalls: "replay the historic corpus before shipping a tightened filter"). Write and run this once, from the scratchpad, read-only:

```python
# scratchpad/replay_keywords.py — read-only replay, prints every band that would change
import httpx, sys
sys.path.insert(0, "services/engine")
from app.deterministic.discovery import keyword_relevance
env = {}
for line in open(".env"):
    if "=" in line and not line.startswith("#"):
        k, v = line.strip().split("=", 1); env[k] = v.strip().strip('"')
KEY = env.get("SUPABASE_SERVICE_JWT") or env["SUPABASE_SERVICE_ROLE_KEY"]
c = httpx.Client(base_url=env["NEXT_PUBLIC_SUPABASE_URL"] + "/rest/v1",
                 headers={"apikey": KEY, "Authorization": f"Bearer {KEY}"}, timeout=120)
WID = "4bcdd285-5957-4c6c-ae47-7671569b1c25"
kw = c.get(f"/vendor_profiles?select=capability_keywords&workspace_id=eq.{WID}").json()[0]["capability_keywords"]
rows = c.get(f"/opportunity_matches?select=relevance_band,relevance_source,opportunities!inner(id,title,category_codes,authority,closing_at)"
             f"&workspace_id=eq.{WID}&opportunities.closing_at=gt.2026-09-14T00:00:00Z&limit=2000").json()
flips = []
for r in rows:
    o = r["opportunities"]
    new = keyword_relevance(o, kw).band
    if r["relevance_source"] == "keyword" and r["relevance_band"] != new:
        flips.append((r["relevance_band"], new, o["title"][:90]))
print(f"{len(rows)} open rows, {len(flips)} keyword bands change")
for old, new, title in sorted(flips): print(f"  {old:6} -> {new:6} | {title}")
```

Run: `cd "<repo root>" && services/engine/.venv/bin/python scratchpad/replay_keywords.py`
Expected: the plywood BOQ appears as `high -> medium` (only "stranded steel wire" survives, on "Mild Steel Binding Wire"). Read every `high -> low`, `high -> medium` and `medium -> low` line; each must be a title that is not a wire-rope purchase. If any genuine rope tender flips to low, stop and widen `_PHRASE_SLACK` by one, re-run, and record the number in the commit message. Paste the output into the phase evidence.

- [ ] **Step 6: Commit**

```bash
git add services/engine/app/deterministic/discovery.py services/engine/tests/test_keyword_matching.py
git commit -m "fix(discovery): a multi-word keyword must hold together and name its head noun

'galvanized wire rope' matched a plywood-and-nails BOQ because 'binding wire' and
'coir rope' both appeared somewhere in the title. Phrase words must now sit within
len+2 tokens of each other in one field sequence, and the last content word must be
among them. Replayed on <N> open rows: <M> keyword bands change, all read."
```

### Task 4: The feed's vocabulary includes the Capability tab and the GeM categories

**Root cause.** `_capability` reads only `vendor_profiles.capability_statement` + `capability_keywords`. The Capability tab (`product_specs.standard_ref`: "IS 2762", "IS 1855"…) and the price screen's `workspace_categories.gem_name` ("Steel Wire Rope", "Wire Rope Sling"…) are never read by ranking or by the keyword gate. Merge them in at recompute. `input_hash` already includes keywords, so affected rows re-band on the next runs within the existing 40-row model budget; `_rules_for` already refreshes the gate's spec from whatever `_capability` returns.

**Files:**
- Modify: `services/engine/app/discovery/ingest.py:266-272` (`_capability`)
- Modify: `services/engine/tests/test_discovery_markets.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `services/engine/tests/test_discovery_markets.py`:

```python
# ---------- the ranking vocabulary is everything the workspace recorded ----------

def test_capability_merges_profile_keywords_categories_and_standards(monkeypatch):
    """Three screens each hold a vocabulary; until now only /profile's reached the feed."""
    from app.discovery import ingest as ing

    monkeypatch.setattr(ing.db, "get_profile_context", lambda ws: {"legal_identity": {
        "capability_statement": "We make rope.",
        "capability_keywords": ["wire rope", "Steel Wire Rope"],
    }})
    monkeypatch.setattr(ing.db, "list_workspace_categories", lambda ws, *, active_only: [
        {"gem_name": "Steel Wire Rope", "active": True},   # duplicate of a profile term
        {"gem_name": "Wire Rope Sling", "active": True},
    ])
    monkeypatch.setattr(ing.db, "get_capability_specs", lambda ws: [
        {"standard_ref": "IS 4521 / API Spec 9A"},
        {"standard_ref": "IS 2762"},
        {"standard_ref": None},
    ])

    statement, keywords = ing._capability("ws-1")

    assert statement == "We make rope."
    assert keywords == ["wire rope", "Steel Wire Rope", "Wire Rope Sling",
                        "IS 4521", "API Spec 9A", "IS 2762"]


def test_capability_only_reads_active_categories(monkeypatch):
    from app.discovery import ingest as ing

    seen = {}
    monkeypatch.setattr(ing.db, "get_profile_context", lambda ws: {"legal_identity": {}})
    monkeypatch.setattr(ing.db, "get_capability_specs", lambda ws: [])

    def cats(ws, *, active_only):
        seen["active_only"] = active_only
        return []

    monkeypatch.setattr(ing.db, "list_workspace_categories", cats)
    assert ing._capability("ws-1") == ("", [])
    assert seen["active_only"] is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd services/engine && uv run pytest tests/test_discovery_markets.py -k capability_ -v`
Expected: FAIL — `keywords == ["wire rope", "Steel Wire Rope"]`.

- [ ] **Step 3: Implement the merge**

In `services/engine/app/discovery/ingest.py`, add `import re` to the stdlib imports if absent, and replace `_capability`:

```python
def _dedupe(terms: list[str]) -> list[str]:
    """First spelling wins; comparison is case-insensitive and whitespace-trimmed."""
    seen: set[str] = set()
    out: list[str] = []
    for t in terms:
        key = " ".join(t.split()).lower()
        if key and key not in seen:
            seen.add(key)
            out.append(t.strip())
    return out


def _capability(workspace_id: str) -> tuple[str, list[str]]:
    """The vendor's own words, and every term they bid on. Both drive the relevance band.

    Three screens each hold a vocabulary, and until 2026-09-14 only /profile's reached the
    feed: the Capability tab's standards ("IS 2762") and the price screen's GeM category
    names ("Wire Rope Sling") were read by their own screens and by nothing else. A
    standard's number is the most precise keyword a manufacturer has — a buyer writes
    "Conforming To IS 2762" — so it goes in as its own phrase, split on "/" and "," because
    "IS 4521 / API Spec 9A" is two standards.

    Order matters twice: `_dedupe` keeps the first spelling, and `input_hash` sorts, so the
    same vocabulary in any order is the same cache key.
    """
    identity = db.get_profile_context(workspace_id).get("legal_identity") or {}
    keywords = list(identity.get("capability_keywords") or [])
    keywords += [
        row["gem_name"]
        for row in db.list_workspace_categories(workspace_id, active_only=True)
        if row.get("gem_name")
    ]
    for spec in db.get_capability_specs(workspace_id):
        keywords += [
            part for part in re.split(r"[/,;]", spec.get("standard_ref") or "")
            if part.strip()
        ]
    return identity.get("capability_statement") or "", _dedupe(keywords)
```

- [ ] **Step 4: Run the suite**

Run: `cd services/engine && uv run pytest -q && uv run ruff check`
Expected: all pass. Note the earlier recompute tests stub `_capability` itself, so they are unaffected.

- [ ] **Step 5: Commit**

```bash
git add services/engine/app/discovery/ingest.py services/engine/tests/test_discovery_markets.py
git commit -m "feat(discovery): rank on the Capability tab's standards and the GeM category names too

_capability read only /profile. product_specs.standard_ref and
workspace_categories.gem_name now join the keyword list, deduped, so the gate
and the band see everything the workspace recorded. Rows re-band within the
existing per-run model budget because the hash includes keywords."
```

**Phase 2 gate:** `uv run pytest` green, `uv run ruff check` clean, replay output pasted. Wait for approval.

---

## Phase 3 — the past-bid uploader is findable (web)

### Task 5: Put "Upload a submitted bid" beside "Add to knowledge base"

**Root cause.** `/library` shows one prominent uploader (`KnowledgeUpload` → `library_documents`, the citation corpus) and hides the other (`PastBidUpload` → `POST /api/past-bids`, the only path that mines `answers`) at the bottom under the document table. UML uploaded 18 documents through the first and zero through the second, and the Learning tab reads only the second.

**Files:**
- Modify: `apps/web/components/PastBidUpload.tsx:1-60` (self-refresh)
- Modify: `apps/web/components/PastBids.tsx:58-75` (drop the now-redundant callback, add anchor id)
- Modify: `apps/web/app/(app)/library/page.tsx:70-75` (side-by-side uploaders)
- Modify: `apps/web/components/LearningMeter.tsx:118-121` (deep link)

- [ ] **Step 1: Make `PastBidUpload` refresh the page itself**

In `apps/web/components/PastBidUpload.tsx`, add the import at the top of the imports block:

```ts
import { useRouter } from "next/navigation";
```

inside the component, after `const [note, setNote] = useState<string | null>(null);`:

```ts
  const router = useRouter();
```

and after the `onUploaded?.({ ... })` line at the end of `upload`:

```ts
    // A server-rendered page shows the new bid only after a refresh. Owned here so every
    // placement gets it, rather than each caller remembering to pass a callback.
    router.refresh();
```

- [ ] **Step 2: Simplify `PastBids`**

In `apps/web/components/PastBids.tsx`, change `<PastBidUpload onUploaded={() => router.refresh()} />` to `<PastBidUpload />`, and give the section an anchor: `<section id="past-bids" data-past-bids className=...>`. If `router` is now unused in that file, remove the `useRouter` import and the `const router = useRouter();` line (typecheck/lint will say).

- [ ] **Step 3: Render both uploaders side by side on `/library`**

In `apps/web/app/(app)/library/page.tsx`, add the import:

```ts
import { PastBidUpload } from "@/components/PastBidUpload";
```

and replace

```tsx
      <div className="mb-6">
        <KnowledgeUpload />
      </div>
```

with

```tsx
      {/* Two corpora, two uploaders, deliberately next to each other. A design partner put
          18 certificates and undertakings through the left one and nothing through the
          right one, then opened the Learning tab and found zeros: evidence documents are
          cited, never mined, and only a submitted bid feeds the answer library. */}
      <div className="mb-6 grid gap-4 lg:grid-cols-[3fr_2fr]">
        <KnowledgeUpload />
        <div
          data-past-bid-entry
          className="rounded-card border border-border bg-surface p-card"
        >
          <h2 className="mb-1 font-heading text-sm font-semibold text-ink">
            Add a submitted bid
          </h2>
          <p className="mb-3 text-xs text-muted">
            A bid you already submitted is mined into reusable answers — that is what the
            Learning tab measures. Documents on the left are evidence for citations and are
            never mined.
          </p>
          <PastBidUpload compact label="Upload a submitted bid" />
        </div>
      </div>
```

- [ ] **Step 4: Point the Learning tab's empty state at the right widget**

In `apps/web/components/LearningMeter.tsx`, change `href="/library"` in the `data-reuse-not-started` section to `href="/library#past-bids"` and its text to `Upload a submitted bid →`.

- [ ] **Step 5: Typecheck, lint, unit tests**

Run: `cd apps/web && pnpm typecheck && pnpm lint && pnpm test`
Expected: all exit 0. `PastBidUpload.test.ts` tests `buildPastBidForm` only and is unaffected by the router import.

- [ ] **Step 6: Browser verification**

Run `/verify` on `/library` and `/knowledge` as FIX-1. Assert on `/library`: `[data-kb-upload]` and `[data-past-bid-entry]` both render above the documents table; zero console errors; zero unexpected 4xx/5xx. Assert on `/knowledge` with an empty library: `[data-reuse-not-started] a[href="/library#past-bids"]` exists. Attach the screenshot path.

- [ ] **Step 7: Commit**

```bash
git add apps/web/components/PastBidUpload.tsx apps/web/components/PastBids.tsx "apps/web/app/(app)/library/page.tsx" apps/web/components/LearningMeter.tsx
git commit -m "fix(library): put the past-bid uploader beside the knowledge-base uploader

Only POST /api/past-bids mines answers, and the Learning tab reads only answers.
The widget sat under the document table; a design partner uploaded 18 evidence
documents and no bids, then saw zeros. PastBidUpload now refreshes itself so
any placement works."
```

**Phase 3 gate:** typecheck/lint/test green, `/verify` evidence attached. Wait for approval.

---

## Phase 4 — deploy, re-measure, record

### Task 6: Deploy the engine and prove the numbers moved

**Files:** none in the repo (operations). Follow `docs/deploy.md` for the engine Cloud Run deploy; use `--update-env-vars`, never `--set-env-vars` (known-pitfalls, "Deployment configuration").

- [ ] **Step 1: Deploy the engine image** per `docs/deploy.md`, then confirm `/health` answers and the revision serving traffic is the new one.

- [ ] **Step 2: Trigger two recomputes for the UML workspace.** Sign in as a UML workspace member (or the FIX-1 user switched into that workspace) and click Refresh on `/opportunities` twice, ten minutes apart, or wait for two runs of the `tendercraft-sweep` scheduler. Two, because a row that was model-scored in run N is what run N+1 used to wipe: the second run is the one that proves the fix.

- [ ] **Step 3: Re-run the measurement** (read-only; same query the review used):

```python
# scratchpad/measure.py
import httpx
from collections import Counter
env = {}
for line in open(".env"):
    if "=" in line and not line.startswith("#"):
        k, v = line.strip().split("=", 1); env[k] = v.strip().strip('"')
KEY = env.get("SUPABASE_SERVICE_JWT") or env["SUPABASE_SERVICE_ROLE_KEY"]
c = httpx.Client(base_url=env["NEXT_PUBLIC_SUPABASE_URL"] + "/rest/v1",
                 headers={"apikey": KEY, "Authorization": f"Bearer {KEY}", "Prefer": "count=exact"}, timeout=120)
WID = "4bcdd285-5957-4c6c-ae47-7671569b1c25"
def count(filter_): return c.get(f"/opportunity_matches?select=id&workspace_id=eq.{WID}&{filter_}&limit=1").headers["content-range"].split("/")[1]
print("band NULL, all rows      :", count("relevance_band=is.null"))
rows = c.get(f"/opportunity_matches?select=relevance_band,relevance_source,opportunities!inner(title,closing_at)&workspace_id=eq.{WID}&state=eq.in_scope&opportunities.closing_at=gt.2026-09-14T00:00:00Z&limit=2000").json()
print("open in-scope rows       :", len(rows))
print("open in-scope unbanded   :", sum(1 for r in rows if r["relevance_band"] is None))
print("open in-scope by band    :", Counter(r["relevance_band"] for r in rows))
print("plywood BOQ band         :", [r["relevance_band"] for r in rows if "Wbr Grade Plywood" in r["opportunities"]["title"]])
```

Expected after two runs:

| Metric | Before | Expected |
|---|---|---|
| open in-scope unbanded | 22 | 0 |
| plywood BOQ band | high | medium at most, never high (one honest partial match on "stranded steel wire") |
| open in-scope rows | 114 | ≥ 114 (the ~250 previously unevaluated rows are now gated; the ones matching the merged vocabulary join the feed) |
| `evaluated` in the refresh response | 1000 | ≥ 1251 |

If "open in-scope unbanded" is not 0 after the second run, the wipe has a second path: read the Cloud Run log for that run's `bands_for` line before touching code.

- [ ] **Step 4: Record the pitfalls.** Append to `docs/known-pitfalls.md` under a new heading `## A cache hit that erases the cache (found 2026-09-14)`:

```markdown
- **A bulk upsert that pads every row to the union key set turns "I did not touch this
  column" into "set it to NULL".** `bands_for` skipped hash-matched rows (correct), the
  upsert padded them with `None` so PostgREST would accept one body (necessary), and
  `merge-duplicates` wrote the NULL over the cached band (the bug). 48% of one workspace's
  match rows were unbanded and the feed showed open wire-rope tenders with no rank. The
  run that REUSED the cache was the run that destroyed it, so the more often the recompute
  ran the worse it got. Group by key set; never invent a value for a column the caller did
  not mention.
- **A saturation warning nobody reads is a silent miss with extra steps.** The 1,000-row
  recompute window logged "SATURATED" on every run for a week. Page to exhaustion when the
  paged work is free (the gate); keep the budget where the cost is (the model call).
- **"All but one word, anywhere in the title" is a substring match on a long enough
  title.** A 40-token multi-item BOQ contains "wire" and "rope" for reasons that have
  nothing to do with wire rope. Phrase words must be near each other and the head noun must
  be present.
- **Three screens can each hold a vocabulary and only one of them feed the ranking.** The
  Capability tab's standards and the price screen's GeM category names were recorded by a
  customer and read by nothing else. When a screen asks the user for terms, grep for every
  consumer before calling it "aligned".
```

And in `docs/feedback/usha-martin.md`, under *What is actually built*, add one dated line: `**2026-09-14:** the feed now ranks on the Capability tab's standards and the GeM category names as well as the profile keywords; the past-bid uploader sits beside the knowledge-base uploader, because UML's 18 uploads were all evidence documents and the Learning tab reads only mined bids.`

- [ ] **Step 5: Commit the docs**

```bash
git add docs/known-pitfalls.md docs/feedback/usha-martin.md
git commit -m "docs(pitfalls): a cache hit that erases the cache, and three vocabularies that never met"
```

- [ ] **Step 6: The data step only UML can do.** Ask UML for two or three actually submitted bids (technical bid PDF/DOCX, not the certificates) and upload them through "Upload a submitted bid" with the outcome set. The Learning tab shows answers immediately; the rewrite trend needs 10 human-edited sections and will say "unknown" until then — that is the screen being honest, not a bug.

---

## Out of scope, on purpose

- **Accessory tenders ranking HIGH by keyword** (Wire Rope Grease, Pin For Wire Rope, Electric Wire Rope Hoist, Tirfor). They genuinely contain "wire rope"; telling them apart is the model's job, and it already does when a row reaches the 40-row model budget. Raising that budget is a spend decision, not a bug.
- **Reading `product_specs` parameters (diameter, construction) on the feed.** Only IS 1855 has any; 7 of 9 envelopes carry a standard reference and nothing else. Ask UML to fill the envelopes first; the schedule-fit screen is where that pays off.
- **The duplicate "USHA MARTIN INDIA" workspace** (`c18f4b6f…`). No delete-workspace endpoint exists and `audit_events` is append-only; confirm with UML which one they use and leave the other.
- **Auto-routing a `past_proposal`-classified knowledge-base upload into the miner.** Tempting, one line, and wrong: the classifier is a model guess and the miner writes reusable answers. The user chooses the corpus.
