# Making the Capability Tab Earn Its Place — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Capability tab produce visible output instead of "not assessed" on every line, and give the three scattered keyword vocabularies one honest home where a user can see what is actually gating their feed.

**Architecture:** Nothing here is a new feature. The spec extractor already works — measured 2026-09-14, it pulled nine correctly typed parameters out of a real Oil India rope line and correctly returned zero for "Bidder shall submit test certificates". It has simply never been run, because it sits behind a button on a screen nobody opens. Phase 1 runs it automatically in the background at ingest and teaches the fit screen to tell "not read yet" apart from "states no specification". Phase 2 exposes the merged keyword vocabulary that the 2026-09-14 discovery fix made real but invisible. Phase 3 moves the keyword editor onto the capability screen and shows per-term reach.

**Tech Stack:** Python 3.12 / FastAPI / pytest via `uv`; Next.js 15 / TypeScript / Vitest via `pnpm`; Supabase PostgREST; one migration (`0040`).

**Measured starting state (2026-09-14, workspace "Usha Martin Limited"):**

| Fact | Value |
|---|---|
| Capability envelopes recorded | 9 (7 carry only a standard reference) |
| Parameters on the bidder side | 9 |
| Tender line items | 98, every one from NIT prose, none from a BOQ row |
| **Parameters on the tender side** | **0** — extraction has never run |
| Schedule-fit verdicts produced, ever | 0 |
| Clarifications generated, ever | 0 |
| Distinct line descriptions (one model call each) | 78 across 5 tenders; 48 on the largest |
| Keyword terms the gate uses | 31 |
| Keyword terms any screen shows | 16 |

**Two constraints that shape every task below.**

*Ingest is synchronous inside the request.* `POST /api/tenders/ingest` runs `_process_ingest` in a threadpool and the user waits for it. Adding 48 model calls there would turn a slow upload into a timeout, so extraction runs as a background task after the response, per `docs/conventions.md` ("OCR/extraction run as background jobs — start with FastAPI BackgroundTasks").

*Absence of parameters is ambiguous today.* A line with no parameters means either "extraction has not run" or "we read it and it states no specification". Those are opposite messages to a user, and no column currently distinguishes them. Migration 0040 adds one rather than letting the screen guess.

---

## Phase 1 — the capability tab starts producing output

### Task 1: Cap the extraction fan-out

**Why first.** `extract_many` has no ceiling. It is currently reached only by a manual click on a schedule the user is looking at, so an unbounded loop has never mattered. Task 2 makes it automatic on every upload, at which point a 400-line BOQ becomes 400 model calls with nobody watching — the cost-blowup shape `docs/known-pitfalls.md` already records for unbounded retries and for the answer miner (`_MAX_MODEL_PAGES`).

**Files:**
- Modify: `services/engine/pipeline/spec_extractor.py` (`extract_many`, lines ~112-120)
- Modify: `services/engine/app/spec_service.py` (`extract_schedule`, lines 83-113)
- Create: `services/engine/tests/test_spec_extract_budget.py`

- [ ] **Step 1: Write the failing test**

```python
"""Extraction is about to become automatic, so its fan-out needs a ceiling.

Until now `extract_many` was reached only by a human clicking "Read specifications" on a
schedule they were looking at, so an unbounded loop was bounded in practice by attention.
Task 2 removes the human. Measured 2026-09-14: one real tender holds 48 distinct line
descriptions, which is fine; a 400-line BOQ is not, and nothing would have said so.
"""

from __future__ import annotations

from app import spec_service


def test_extract_many_stops_at_the_budget(monkeypatch):
    from pipeline import spec_extractor

    seen: list[str] = []
    monkeypatch.setattr(spec_extractor, "extract_parameters",
                        lambda d: seen.append(d) or ())

    out = spec_extractor.extract_many([f"line {i}" for i in range(50)], limit=10)

    assert len(seen) == 10, "the budget is a ceiling on MODEL CALLS, not a slice of the output"
    assert len(out) == 10


def test_extract_many_dedupes_before_spending_the_budget(monkeypatch):
    # A BOQ repeats the same rope at four consignee sites. Deduping first is the difference
    # between spending the budget on four identical strings and on four different ones.
    from pipeline import spec_extractor

    seen: list[str] = []
    monkeypatch.setattr(spec_extractor, "extract_parameters",
                        lambda d: seen.append(d) or ())

    spec_extractor.extract_many(["same"] * 20 + ["a", "b", "c"], limit=3)

    assert seen == ["same", "a", "b"], "dedupe must happen before the cap, not after"


def test_extract_schedule_reports_what_it_skipped(monkeypatch):
    # A silent partial read is the failure this product keeps finding: the number looks fine
    # and the remainder is invisible. The caller must be able to say "48 of 96 read".
    monkeypatch.setattr(spec_service.db, "replace_line_item_parameters",
                        lambda *a, **k: None)
    from pipeline import spec_extractor

    monkeypatch.setattr(spec_extractor, "extract_parameters", lambda d: ())

    items = [{"id": f"i{i}", "description": f"desc {i}"} for i in range(5)]
    result = spec_service.extract_schedule("ws", items, limit=2)

    assert result["distinct"] == 5
    assert result["read"] == 2
    assert result["skipped"] == 3
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd services/engine && uv run pytest tests/test_spec_extract_budget.py -v`
Expected: FAIL — `extract_many() got an unexpected keyword argument 'limit'`.

- [ ] **Step 3: Add the budget to `extract_many`**

In `services/engine/pipeline/spec_extractor.py`, replace `extract_many`:

```python
#: Ceiling on model calls for one schedule. Sized against real data: the largest live tender
#: holds 48 distinct line descriptions, so this clears a genuine schedule with room while
#: refusing to turn a 400-line BOQ into 400 calls nobody authorised. Raise it deliberately,
#: with a measurement, not because a schedule was truncated once.
DEFAULT_EXTRACT_BUDGET = int(os.environ.get("SPEC_EXTRACT_BUDGET", "80"))


def extract_many(
    descriptions: Sequence[str], limit: int | None = None
) -> dict[str, tuple[ParamValue, ...]]:
    """Extract for a batch of DISTINCT descriptions, keyed by description.

    BOQs repeat rows heavily — the same rope at four consignee sites is four lines and one
    description. Deduping before the fan-out is the difference between 40 model calls and 6 on
    a real schedule, and it happens BEFORE the cap so the budget buys distinct work.

    Order is the schedule's own. A truncated read is reported by the caller rather than
    silently returning fewer keys than it was asked about.
    """
    budget = DEFAULT_EXTRACT_BUDGET if limit is None else limit
    unique = list(dict.fromkeys(d.strip() for d in descriptions if d and d.strip()))
    return {d: extract_parameters(d) for d in unique[:budget]}
```

Add `import os` to that file's imports if it is not already there.

- [ ] **Step 4: Make `extract_schedule` report the remainder**

In `services/engine/app/spec_service.py`, change the signature and the return so a partial read announces itself:

```python
def extract_schedule(
    workspace_id: str, line_items: Sequence[dict], limit: int | None = None
) -> dict[str, int]:
    """Read every distinct description once and store the parameters.

    Returns counts rather than a bare number: a partial read must be able to say so. A silent
    truncation is the failure shape this codebase keeps rediscovering — the total looks
    plausible and the remainder is invisible.

    Import is local so `app.spec_service` stays importable — and the assessment path stays
    runnable — in a deployment where the model client is not configured at all.
    """
    from pipeline.spec_extractor import extract_many

    by_description = extract_many([i.get("description", "") for i in line_items], limit=limit)
    distinct = len({(i.get("description") or "").strip()
                    for i in line_items if (i.get("description") or "").strip()})
    populated = 0
    for item in line_items:
        params = by_description.get((item.get("description") or "").strip(), ())
        if not params:
            continue
        db.replace_line_item_parameters(
            workspace_id, item["id"],
            [
                {
                    "param_key": p.key,
                    "kind": p.kind.value,
                    "unit": p.unit,
                    "num_min": p.num_min,
                    "num_max": p.num_max,
                    "allowed_values": sorted(p.allowed),
                    "raw_text": p.raw_text,
                }
                for p in params
            ],
        )
        populated += 1
    return {
        "distinct": distinct,
        "read": len(by_description),
        "skipped": max(0, distinct - len(by_description)),
        "populated": populated,
    }
```

- [ ] **Step 5: Update the route to the new return shape**

In `services/engine/app/spec_routes.py`, in `extract_schedule`'s `_run()`, replace the two lines that call the service and build the response:

```python
        counts = spec_service.extract_schedule(user.workspace_id, items)
        return {"lines": len(items), **counts,
                **spec_service.assess_schedule(user.workspace_id, tender_id)}
```

- [ ] **Step 6: Run the tests**

Run: `cd services/engine && uv run pytest tests/test_spec_extract_budget.py tests/ -q -k "spec or schedule" && uv run ruff check`
Expected: all pass, ruff clean.

- [ ] **Step 7: Commit**

```bash
git add services/engine/pipeline/spec_extractor.py services/engine/app/spec_service.py services/engine/app/spec_routes.py services/engine/tests/test_spec_extract_budget.py
git commit -m "feat(specs): cap the extraction fan-out and report what it skipped

extract_many had no ceiling, which was bounded in practice by a human clicking
the button. Automatic extraction removes the human, so a 400-line BOQ would be
400 model calls with nobody watching. Budget of 80 distinct descriptions (the
largest live tender holds 48), deduped before the cap, and a partial read now
says so instead of returning a plausible-looking total."
```

### Task 2: Extract automatically after ingest, in the background

**Files:**
- Create: `services/engine/migrations/0040_specs_extracted_at.sql`
- Modify: `services/engine/app/tenders.py` (ingest route ~198-223, `_process_ingest` ~165-172)
- Modify: `services/engine/app/db.py` (add `mark_specs_extracted`)
- Modify: `services/engine/app/spec_routes.py` (manual path stamps it too)
- Create: `services/engine/tests/test_schedule_autoextract.py`

- [ ] **Step 1: Write the migration**

Create `services/engine/migrations/0040_specs_extracted_at.sql`:

```sql
-- When the schedule's specifications were last read out of the line descriptions.
--
-- NULL means "never read", and that is a different sentence from "read, and these lines state
-- no specification" — the two are opposite messages to a bidder and no column distinguished
-- them. Measured 2026-09-14: 98 line items across five tenders, zero extracted parameters, and
-- a screen that said "NOT ASSESSED" 98 times without being able to say which of the two it
-- meant. Deliberately NOT backfilled: every existing row genuinely has never been read, so
-- NULL is the true value and writing a timestamp would manufacture the claim the column exists
-- to make honestly (docs/known-pitfalls.md — backfilling "the obvious value" can assert the
-- exact lie the column was added to detect).
alter table public.tenders
  add column if not exists specs_extracted_at timestamptz;

comment on column public.tenders.specs_extracted_at is
  'When schedule line specifications were last extracted. NULL = never read, which is not the same as read-and-empty.';
```

- [ ] **Step 2: Write the failing tests**

Create `services/engine/tests/test_schedule_autoextract.py`:

```python
"""Extraction must run on its own, and must never be able to break an upload.

Measured 2026-09-14: the extractor works — nine correctly typed parameters out of a real rope
line, zero out of "Bidder shall submit test certificates" — and had produced nothing in
production because it sat behind a button on a screen nobody opened. `docs/known-pitfalls.md`
already records the shape: a feature reachable only by a button is a feature that silently
stops.

It runs in the BACKGROUND, not inside the request. `POST /api/tenders/ingest` awaits
`_process_ingest` in a threadpool, so the user is waiting on it; 48 model calls added there
turns a slow upload into a timeout.
"""

from __future__ import annotations

from app import tenders


def test_ingest_schedules_extraction_as_a_background_task(monkeypatch):
    scheduled: list[tuple] = []

    class FakeBackground:
        def add_task(self, fn, *args, **kwargs):
            scheduled.append((fn, args, kwargs))

    monkeypatch.setattr(tenders, "_process_ingest",
                        lambda ws, docs, name, pursuit: {"tender_id": "t-1"})

    tenders._schedule_extraction(FakeBackground(), "ws-1", "t-1")

    assert len(scheduled) == 1, "extraction must be queued, not run inline"
    assert scheduled[0][1] == ("ws-1", "t-1")


def test_background_extraction_swallows_its_own_failure(monkeypatch, caplog):
    # An upload that succeeded must not be reported as failed because a later, optional read
    # of the schedule fell over. Same reasoning as harvest_quietly on the export path.
    def boom(*a, **k):
        raise RuntimeError("model down")

    monkeypatch.setattr(tenders.db, "get_line_items", boom)
    tenders._extract_quietly("ws-1", "t-1")  # must not raise


def test_background_extraction_stamps_the_tender(monkeypatch):
    stamped: list[tuple] = []
    monkeypatch.setattr(tenders.db, "get_line_items",
                        lambda t, w: [{"id": "l1", "description": "Steel Wire Rope 20mm"}])
    monkeypatch.setattr(tenders.spec_service, "extract_schedule",
                        lambda ws, items, **k: {"distinct": 1, "read": 1, "skipped": 0,
                                                "populated": 1})
    monkeypatch.setattr(tenders.db, "mark_specs_extracted",
                        lambda ws, t: stamped.append((ws, t)))

    tenders._extract_quietly("ws-1", "t-1")

    assert stamped == [("ws-1", "t-1")]


def test_a_tender_with_no_schedule_is_stamped_too(monkeypatch):
    # "Read it, there was nothing there" is a real answer and the screen needs to be able to
    # give it. Leaving the stamp NULL would make an empty schedule permanently indistinguishable
    # from one that was never read.
    stamped: list[tuple] = []
    monkeypatch.setattr(tenders.db, "get_line_items", lambda t, w: [])
    monkeypatch.setattr(tenders.db, "mark_specs_extracted",
                        lambda ws, t: stamped.append((ws, t)))

    tenders._extract_quietly("ws-1", "t-1")

    assert stamped == [("ws-1", "t-1")]
```

- [ ] **Step 3: Run to verify they fail**

Run: `cd services/engine && uv run pytest tests/test_schedule_autoextract.py -v`
Expected: FAIL with `AttributeError: module 'app.tenders' has no attribute '_schedule_extraction'`.

- [ ] **Step 4: Add the db helper**

In `services/engine/app/db.py`, beside the other tender writers:

```python
def mark_specs_extracted(workspace_id: str, tender_id: str) -> None:
    """Stamp when this tender's schedule specifications were last read.

    Written even when the read found nothing: "read, and these lines state no specification"
    is a real answer, and leaving the stamp NULL would make it permanently indistinguishable
    from "never read" — which is the whole reason the column exists.
    """
    _rest(
        "PATCH", "tenders",
        params={"id": f"eq.{tender_id}", "workspace_id": f"eq.{workspace_id}"},
        json={"specs_extracted_at": datetime.now(UTC).isoformat()},
        prefer="return=minimal",
    )
```

(`datetime`/`UTC` are already imported in `db.py`; confirm with `grep -n "^from datetime" services/engine/app/db.py` and add if missing.)

- [ ] **Step 5: Add the background hooks to `tenders.py`**

In `services/engine/app/tenders.py`, add after the imports (`spec_service` is already imported):

```python
def _extract_quietly(workspace_id: str, tender_id: str) -> None:
    """Read the schedule's specifications. A failure here never reaches the uploader.

    The upload has already succeeded and been reported by the time this runs. Losing an
    optional read of the schedule must not turn that into an error the user cannot act on —
    same reasoning as `learning.harvest_quietly` on the export path.
    """
    try:
        items = db.get_line_items(tender_id, workspace_id)
        if items:
            counts = spec_service.extract_schedule(workspace_id, items)
            log.info("schedule specs read for tender %s: %s", tender_id, counts)
        db.mark_specs_extracted(workspace_id, tender_id)
    except Exception:  # noqa: BLE001 — deliberate: never fail an upload that already returned
        log.exception("background spec extraction failed for tender %s", tender_id)


def _schedule_extraction(background, workspace_id: str, tender_id: str) -> None:
    """Queue the read for after the response.

    NOT inline: `ingest_tender` awaits `_process_ingest` in a threadpool, so the uploader is
    waiting on it, and a real schedule is up to 48 model calls. Extraction is the one part of
    ingest nobody is watching the clock on.
    """
    background.add_task(_extract_quietly, workspace_id, tender_id)
```

- [ ] **Step 6: Wire it into the route**

In `services/engine/app/tenders.py`, change the route signature and its return:

```python
@router.post("/api/tenders/ingest")
async def ingest_tender(
    user: CurrentUser, background: BackgroundTasks,
    file: Annotated[list[UploadFile], File()], title: str = "",
    pursuit_id: str = "",
) -> dict:
```

and replace the final `return ok(await run_in_threadpool(...))` with:

```python
    # Parsing + extraction + inserts are blocking; keep the event loop free.
    result = await run_in_threadpool(
        _process_ingest, user.workspace_id, documents, name, pursuit_id,
    )
    # The schedule's specifications are read AFTER the response. The upload is the product;
    # this is an optional enrichment that costs model calls and must never delay or fail it.
    _schedule_extraction(background, user.workspace_id, result["tender_id"])
    return ok(result)
```

Add `BackgroundTasks` to the `fastapi` import at the top of the file.

- [ ] **Step 7: Stamp on the manual path too**

In `services/engine/app/spec_routes.py`, inside `extract_schedule`'s `_run()`, after the `counts = ...` line:

```python
        db.mark_specs_extracted(user.workspace_id, tender_id)
```

Ensure `db` is imported in that module (`grep -n "^from . import" services/engine/app/spec_routes.py`).

- [ ] **Step 8: Run the tests**

Run: `cd services/engine && uv run pytest -q && uv run ruff check`
Expected: all pass, ruff clean.

- [ ] **Step 9: Apply the migration, then commit**

Migrations go before code (`docs/deploy.md`). Apply `0040` with `tools/apply-migration.sh`, then:

```bash
git add services/engine/migrations/0040_specs_extracted_at.sql services/engine/app/tenders.py services/engine/app/db.py services/engine/app/spec_routes.py services/engine/tests/test_schedule_autoextract.py
git commit -m "feat(specs): read schedule specifications automatically, in the background

The extractor works — nine typed parameters out of a real rope line, zero out of
a certificates clause — and had produced nothing in production because it sat
behind a button nobody pressed. It now runs after ingest as a BackgroundTask,
never inline: the uploader is already waiting on a threadpool and a real
schedule is up to 48 model calls.

0040 adds tenders.specs_extracted_at. NULL means never read, which is a
different sentence from read-and-empty, and no column said which."
```

### Task 3: The fit screen stops calling prose criteria "not assessed"

**Why.** All 98 live line items came from NIT prose; none has a BOQ row anchor. So the set includes "Past Performance 30%" and "Compliance of BoQ specification", which no manufacturing envelope can ever answer. Once extraction has run, a line that yielded zero parameters is deterministically not a product line — and lumping those in with genuine unknowns buries whatever real verdicts appear.

**Files:**
- Modify: `services/engine/app/spec_service.py` (`assess_schedule` ~167-215, `_summarise` ~317-328)
- Modify: `services/engine/app/db.py` (`get_tender` must return the new column — verify with `select=*`)
- Modify: `apps/web/components/ScheduleFit.tsx`
- Create: `services/engine/tests/test_schedule_summary.py`

- [ ] **Step 1: Write the failing tests**

Create `services/engine/tests/test_schedule_summary.py`:

```python
"""A line that states no specification is not an unassessed product line.

Every live line item comes from NIT prose rather than a BOQ row, so the schedule legitimately
contains "Past Performance 30 %" and "Compliance of BoQ specification". A manufacturing
envelope cannot answer those, and counting them as unknown buries the real verdicts.

The distinction is only available AFTER extraction has run — before that, zero parameters means
"not read yet". `specs_extracted_at` is what separates the two, which is why the summary takes
it rather than inferring it from the rows.
"""

from __future__ import annotations

from app.spec_service import _summarise


def _line(state: str, parameters_read: int) -> dict:
    return {"catalogue_state": state, "parameters_read": parameters_read}


def test_before_extraction_nothing_is_called_a_non_product_line():
    lines = [_line("unknown", 0), _line("unknown", 0)]
    s = _summarise(lines, extracted=False)
    assert s["not_a_product_line"] == 0
    assert s["unknown"] == 2
    assert s["awaiting_read"] == 2


def test_after_extraction_a_line_with_no_parameters_is_not_a_product_line():
    lines = [_line("unknown", 0), _line("creatable", 3)]
    s = _summarise(lines, extracted=True)
    assert s["not_a_product_line"] == 1
    assert s["awaiting_read"] == 0
    # It must leave the unknown bucket, or the two are still conflated on screen.
    assert s["unknown"] == 0
    assert s["creatable"] == 1


def test_the_buckets_always_add_up_to_the_total():
    # One function computes every counter, so a screen can never show a number nothing
    # explains (docs/known-pitfalls.md: four counters describing one object will disagree).
    lines = [_line("published", 2), _line("creatable", 1),
             _line("not_creatable", 4), _line("unknown", 2), _line("unknown", 0)]
    s = _summarise(lines, extracted=True)
    assert (s["published"] + s["creatable"] + s["not_creatable"]
            + s["unknown"] + s["not_a_product_line"]) == s["total"] == 5
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd services/engine && uv run pytest tests/test_schedule_summary.py -v`
Expected: FAIL — `_summarise() got an unexpected keyword argument 'extracted'`.

- [ ] **Step 3: Rewrite `_summarise`**

In `services/engine/app/spec_service.py`:

```python
def _summarise(lines: Sequence[dict], *, extracted: bool) -> dict[str, int]:
    """One function computes the counts, so a screen can never show a number nothing explains
    (docs/known-pitfalls.md: four counters describing one object will disagree).

    `extracted` is passed in, never inferred from the rows. Zero parameters on every line means
    "never read" before extraction and "these lines state no specification" after it — opposite
    messages, and guessing between them from the data alone is exactly the inference this
    codebase forbids recording as a measurement.
    """
    states = [line["catalogue_state"] for line in lines]
    # A line that was read and yielded nothing is prose, not an unanswered product line.
    prose = (
        sum(1 for line in lines
            if line["parameters_read"] == 0
            and line["catalogue_state"] == CatalogueState.UNKNOWN.value)
        if extracted else 0
    )
    return {
        "total": len(lines),
        "published": states.count(CatalogueState.PUBLISHED.value),
        "creatable": states.count(CatalogueState.CREATABLE.value),
        "not_creatable": states.count(CatalogueState.NOT_CREATABLE.value),
        "unknown": states.count(CatalogueState.UNKNOWN.value) - prose,
        "not_a_product_line": prose,
        "awaiting_read": 0 if extracted else len(lines),
    }
```

- [ ] **Step 4: Pass the flag through `assess_schedule`**

In `assess_schedule`, read the tender and hand the flag down. Replace the `return` block:

```python
    tender = db.get_tender(tender_id, workspace_id) or {}
    extracted = bool(tender.get("specs_extracted_at"))

    return {
        "lines": lines,
        "summary": _summarise(lines, extracted=extracted),
        # Said once, here, so no screen has to invent the wording. We never read GeM to obtain
        # or verify a catalogue (G-1/G-8) — "published" is the bidder's own record.
        "catalogue_source": "recorded_by_you",
        "has_capability": bool(envelopes or catalogues),
        # NULL until the schedule has been read once. The screen must be able to say "not read
        # yet" rather than implying a verdict it has not computed.
        "specs_extracted_at": tender.get("specs_extracted_at"),
    }
```

- [ ] **Step 5: Run the engine suite**

Run: `cd services/engine && uv run pytest -q && uv run ruff check`
Expected: all pass. Any other caller of `_summarise` must be updated — `grep -rn "_summarise(" services/engine/app/`.

- [ ] **Step 6: Teach the screen the difference**

In `apps/web/components/ScheduleFit.tsx`, extend the `Schedule` type with `specs_extracted_at: string | null` and `summary.not_a_product_line: number` / `summary.awaiting_read: number`, then add this banner directly above the lines table:

```tsx
{/* Three different sentences, and the screen used to have one. "Not assessed" was shown for
    a line nobody had read, a line with no specification in it, and a line whose parameters
    no envelope covers — which made a working feature look broken. */}
{schedule.specs_extracted_at === null ? (
  <div
    data-specs-unread
    className="mb-4 rounded-card border border-hairline bg-surface-alt p-card text-sm text-muted"
  >
    The specifications in these lines have not been read yet. This happens automatically
    shortly after upload; use <span className="font-medium">Read specifications</span> to run
    it now.
  </div>
) : summary.not_a_product_line > 0 ? (
  <div
    data-prose-lines
    className="mb-4 rounded-card border border-hairline bg-surface-alt p-card text-sm text-muted"
  >
    {summary.not_a_product_line} of {summary.total} lines state no product specification —
    they are requirements like past performance or document submission. They are listed
    below and are not counted as gaps in your capability.
  </div>
) : null}
```

- [ ] **Step 7: Verify the web layer**

Run: `cd apps/web && pnpm typecheck && pnpm lint && pnpm test`
Expected: all exit 0.

- [ ] **Step 8: Commit**

```bash
git add services/engine/app/spec_service.py services/engine/tests/test_schedule_summary.py apps/web/components/ScheduleFit.tsx
git commit -m "fix(specs): tell 'not read yet' apart from 'states no specification'

Every live line item comes from NIT prose, so the schedule legitimately holds
'Past Performance 30 %'. Counting those as unassessed product lines buries the
real verdicts and made a working comparator look broken. The distinction only
exists after extraction has run, so the flag is passed in rather than guessed
from rows that look identical in both cases."
```

**Phase 1 gate:** `uv run pytest` green, `uv run ruff check` clean, `pnpm typecheck/lint/test` clean, `/verify` on `/tenders/:id/schedule`. Then upload one real UML tender and paste the resulting summary — this is the phase's actual deliverable: verdicts where there were none. Wait for approval.

---

## Phase 2 — the keyword vocabulary becomes visible

### Task 4: One endpoint that says what is actually gating the feed

**The gap this closes.** Since 2026-09-14 the gate runs on 31 terms: 16 typed on `/profile`, 7 GeM category names, 8 standard references from the capability envelopes. Every screen still shows 16. The feed's own help text points at the keyword box to explain an exclusion that box no longer fully controls.

Reach per term is bundled in because a dead term and a quiet market look identical, and `tests/test_keyword_matching.py` already argues the case: a typo in this workspace's keywords matched 0 of 581 tenders and nothing said so. Adding derived terms nobody typed makes that worse unless reach ships with it.

**Files:**
- Modify: `services/engine/app/discovery/ingest.py` (extract `capability_terms`)
- Modify: `services/engine/app/spec_routes.py` (new endpoint)
- Create: `services/engine/tests/test_capability_vocabulary.py`

- [ ] **Step 1: Write the failing tests**

Create `services/engine/tests/test_capability_vocabulary.py`:

```python
"""What is gating the feed, and where each term came from.

The gate uses terms from three screens. Only one of them has an input box, so a user looking
at their keywords sees a subset of what is actually excluding tenders — and a term they never
typed can now exclude nothing or everything with no way to tell which.
"""

from __future__ import annotations

from app.discovery.ingest import capability_terms


def test_every_term_names_its_source(monkeypatch):
    from app.discovery import ingest as ing

    monkeypatch.setattr(ing.db, "get_profile_context", lambda ws: {"legal_identity": {
        "capability_statement": "We make rope.",
        "capability_keywords": ["wire rope"],
    }})
    monkeypatch.setattr(ing.db, "list_workspace_categories", lambda ws, *, active_only: [
        {"gem_name": "Wire Rope Sling", "active": True},
    ])
    monkeypatch.setattr(ing.db, "get_capability_specs", lambda ws: [
        {"label": "Wire Rope (ONGC)", "standard_ref": "IS 4521 / API Spec 9A"},
    ])

    terms = capability_terms("ws-1")

    assert [(t.term, t.source) for t in terms] == [
        ("wire rope", "typed"),
        ("Wire Rope Sling", "category"),
        ("IS 4521", "standard"),
        ("API Spec 9A", "standard"),
    ]
    assert terms[2].origin == "Wire Rope (ONGC)", "a derived term must name the row it came from"


def test_a_duplicate_keeps_the_first_spelling_and_its_source(monkeypatch):
    # The typed box wins: it is the one the user can edit, so attributing a shared term to a
    # read-only row would send them to a field they cannot change.
    from app.discovery import ingest as ing

    monkeypatch.setattr(ing.db, "get_profile_context", lambda ws: {"legal_identity": {
        "capability_keywords": ["Steel Wire Rope"]}})
    monkeypatch.setattr(ing.db, "list_workspace_categories", lambda ws, *, active_only: [
        {"gem_name": "steel wire rope", "active": True}])
    monkeypatch.setattr(ing.db, "get_capability_specs", lambda ws: [])

    terms = capability_terms("ws-1")
    assert len(terms) == 1
    assert terms[0].term == "Steel Wire Rope" and terms[0].source == "typed"


def test_the_gate_and_the_display_use_the_same_list(monkeypatch):
    """`_capability` must be built FROM `capability_terms`, not alongside it.

    Two functions deriving one vocabulary is the drift this codebase has been bitten by twice
    (the rule spec against the profile; the engine's scope against RLS). If they can disagree,
    the screen explaining an exclusion will eventually explain the wrong one.
    """
    from app.discovery import ingest as ing

    monkeypatch.setattr(ing.db, "get_profile_context", lambda ws: {"legal_identity": {
        "capability_statement": "s", "capability_keywords": ["a", "b"]}})
    monkeypatch.setattr(ing.db, "list_workspace_categories", lambda ws, *, active_only: [
        {"gem_name": "c", "active": True}])
    monkeypatch.setattr(ing.db, "get_capability_specs", lambda ws: [
        {"label": "L", "standard_ref": "IS 1"}])

    statement, keywords = ing._capability("ws-1")
    assert statement == "s"
    assert keywords == [t.term for t in capability_terms("ws-1")]
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd services/engine && uv run pytest tests/test_capability_vocabulary.py -v`
Expected: FAIL — `ImportError: cannot import name 'capability_terms'`.

- [ ] **Step 3: Extract `capability_terms` and rebuild `_capability` on it**

In `services/engine/app/discovery/ingest.py`, add `from dataclasses import dataclass` to the imports, then replace `_dedupe` and `_capability` with:

```python
@dataclass(frozen=True)
class Term:
    """One keyword the feed gate runs on, and where the user can go to change it."""

    term: str
    #: 'typed' (the profile's keyword box) | 'category' (a GeM category) | 'standard' (an envelope)
    source: str
    #: For a derived term, the row it came from, so a screen can name it. "" when typed.
    origin: str = ""


def capability_terms(workspace_id: str) -> list[Term]:
    """Every term gating and ranking this workspace's feed, attributed to its source.

    Three screens each hold a vocabulary and only one of them has an input box, so a user
    looking at their keywords sees a subset of what is actually excluding tenders. This is the
    one list; `_capability` is built from it so the gate and the explanation cannot drift —
    two derivations of one rule is a defect shape this codebase has already paid for twice.

    A standard's number is the most precise keyword a manufacturer has: a buyer writes
    "Conforming To IS 2762", and one live tender was reachable by nothing else because its
    title never uses the word "rope". Split on "/" and "," — "IS 4521 / API Spec 9A" is two.

    The typed spelling wins a duplicate, because that is the field the user can edit.
    """
    identity = db.get_profile_context(workspace_id).get("legal_identity") or {}
    found: list[Term] = [
        Term(t, "typed") for t in (identity.get("capability_keywords") or [])
    ]
    found += [
        Term(row["gem_name"], "category")
        for row in db.list_workspace_categories(workspace_id, active_only=True)
        if row.get("gem_name")
    ]
    for spec in db.get_capability_specs(workspace_id):
        found += [
            Term(part.strip(), "standard", spec.get("label") or "")
            for part in re.split(r"[/,;]", spec.get("standard_ref") or "")
            if part.strip()
        ]

    seen: set[str] = set()
    out: list[Term] = []
    for t in found:
        key = " ".join(t.term.split()).lower()
        if key and key not in seen:
            seen.add(key)
            out.append(Term(t.term.strip(), t.source, t.origin))
    return out


def _capability(workspace_id: str) -> tuple[str, list[str]]:
    """The vendor's own words, and every term they bid on. Both drive the relevance band."""
    identity = db.get_profile_context(workspace_id).get("legal_identity") or {}
    return (
        identity.get("capability_statement") or "",
        [t.term for t in capability_terms(workspace_id)],
    )
```

- [ ] **Step 4: Add the endpoint**

In `services/engine/app/spec_routes.py`:

```python
@router.get("/api/capability/vocabulary")
async def capability_vocabulary(user: CurrentUser) -> dict:
    """The terms gating the feed, with where each came from and how far each reaches.

    Reach is deterministic — `keyword_relevance` over the open corpus, no model — and it is
    here because a dead term and a quiet market look identical. A typo in this workspace's
    keywords once matched 0 of 581 tenders with nothing anywhere saying so, and derived terms
    nobody typed make that worse rather than better.
    """
    def work() -> dict:
        from .deterministic.discovery import keyword_relevance
        from .discovery.ingest import capability_terms

        terms = capability_terms(user.workspace_id)
        markets = db.get_workspace_markets(user.workspace_id)
        corpus = db.get_opportunities(limit=1000, markets=markets, open_only=True)
        rules = db.get_discovery_rules(user.workspace_id)
        gate_on = any(r["name"] == CAPABILITY_RULE_NAME and r.get("enabled") for r in rules)
        return {
            "terms": [
                {
                    "term": t.term,
                    "source": t.source,
                    "origin": t.origin,
                    # How many open tenders THIS TERM ALONE would keep. A zero here is the
                    # finding: the term can never contribute to a decision.
                    "reach": sum(
                        1 for o in corpus if keyword_relevance(o, [t.term]).band != "low"
                    ),
                }
                for t in terms
            ],
            "corpus_open": len(corpus),
            "gate_enabled": gate_on,
        }

    return ok(await run_in_threadpool(work))
```

Add `from .discovery.ingest import CAPABILITY_RULE_NAME` to that module's imports.

- [ ] **Step 5: Run the suite**

Run: `cd services/engine && uv run pytest -q && uv run ruff check`
Expected: all pass. The existing `test_capability_merges_profile_keywords_categories_and_standards` must still pass unchanged — `_capability`'s contract has not moved.

- [ ] **Step 6: Commit**

```bash
git add services/engine/app/discovery/ingest.py services/engine/app/spec_routes.py services/engine/tests/test_capability_vocabulary.py
git commit -m "feat(capability): one attributed vocabulary, with per-term reach

The gate runs on 31 terms; every screen shows 16. capability_terms() is now the
single derivation and _capability is built from it, so the gate and the
explanation cannot drift. Reach ships with it because a dead term and a quiet
market look identical, and derived terms nobody typed make that worse."
```

---

## Phase 3 — the keyword editor moves to where the vocabulary lives

### Task 5: Move "What you bid on" onto the capability screen

**The reasoning, so it survives review.** The tables stay separate: `vendor_profiles` answers "are we eligible to bid" (turnover, certificates, experience) and `product_specs` answers "can we make this" — different shapes, different cadence, different consumers. What moves is the keyword editor, because the other two-thirds of its vocabulary already lives on the capability screen. `PUT /api/profile` takes partial writes by design ("a form can send just the section it edited"), so no endpoint changes.

**Files:**
- Create: `apps/web/components/BidVocabulary.tsx`
- Modify: `apps/web/app/(app)/capability/page.tsx`
- Modify: `apps/web/components/CapabilityEditor.tsx` (render the new section at the top)
- Modify: `apps/web/components/ProfileForm.tsx` (remove the section, leave a pointer)
- Create: `apps/web/components/BidVocabulary.test.ts`

- [ ] **Step 1: Write the failing unit test**

Create `apps/web/components/BidVocabulary.test.ts`:

```ts
import { describe, expect, test } from "vitest";
import { groupBySource, type VocabTerm } from "./BidVocabulary";

const terms: VocabTerm[] = [
  { term: "wire rope", source: "typed", origin: "", reach: 61 },
  { term: "oil indutry", source: "typed", origin: "", reach: 0 },
  { term: "IS 2266", source: "standard", origin: "Wire Rope (ONGC)", reach: 1 },
  { term: "Wire Rope Sling", source: "category", origin: "", reach: 4 },
];

describe("the bid vocabulary", () => {
  test("typed terms are editable and derived ones are not", () => {
    const g = groupBySource(terms);
    expect(g.typed.map((t) => t.term)).toEqual(["wire rope", "oil indutry"]);
    expect(g.derived.map((t) => t.term)).toEqual(["IS 2266", "Wire Rope Sling"]);
  });

  test("a term reaching nothing is surfaced, whatever its source", () => {
    // The whole reason reach is on this screen: a dead term and a quiet market look
    // identical. A typo matched 0 of 581 tenders here once and nothing said so.
    expect(groupBySource(terms).dead.map((t) => t.term)).toEqual(["oil indutry"]);
  });

  test("an empty vocabulary reports no dead terms rather than throwing", () => {
    const g = groupBySource([]);
    expect(g.typed).toEqual([]);
    expect(g.derived).toEqual([]);
    expect(g.dead).toEqual([]);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd apps/web && pnpm test BidVocabulary`
Expected: FAIL — cannot resolve `./BidVocabulary`.

- [ ] **Step 3: Build the component**

Create `apps/web/components/BidVocabulary.tsx`:

```tsx
"use client";

/**
 * What this workspace bids on — the terms that rank the feed and, when the narrow feed is on,
 * the terms that exclude from it.
 *
 * It lives here rather than on the profile because two of its three sources already do: the
 * GeM category names and the envelopes' standard references. The profile answers "are we
 * eligible" — turnover, certificates, experience. This screen answers "what can we make and
 * what do we bid on", and the keyword box is the second half of that sentence.
 *
 * **Derived terms are shown, never silently merged.** The gate has run on the merged list
 * since 2026-09-14 while every screen showed only the typed third, so an excluded tender could
 * be explained by a term the user had never seen and could not find. They are read-only here
 * because their editable home is the row they came from.
 *
 * **Reach is the honest column.** A term matching nothing looks exactly like a term whose
 * segment is quiet this week, and one typo in this workspace's own keywords matched 0 of 581
 * open tenders with nothing anywhere saying so.
 */

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

export type VocabTerm = {
  term: string;
  source: "typed" | "category" | "standard";
  origin: string;
  reach: number;
};

export function groupBySource(terms: VocabTerm[]) {
  return {
    typed: terms.filter((t) => t.source === "typed"),
    derived: terms.filter((t) => t.source !== "typed"),
    dead: terms.filter((t) => t.reach === 0),
  };
}

const SOURCE_LABEL: Record<VocabTerm["source"], string> = {
  typed: "typed here",
  category: "GeM category",
  standard: "standard on",
};

export function BidVocabulary({
  terms,
  keywordsRaw,
  statement,
  corpusOpen,
  gateEnabled,
}: {
  terms: VocabTerm[];
  keywordsRaw: string;
  statement: string;
  corpusOpen: number;
  gateEnabled: boolean;
}) {
  const router = useRouter();
  const [raw, setRaw] = useState(keywordsRaw);
  const [text, setText] = useState(statement);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const { derived, dead } = groupBySource(terms);

  async function save() {
    setBusy(true);
    setError(null);
    const res = await fetch("/api/profile", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      // Partial write: PUT /api/profile is omitted-means-unchanged, so this touches nothing
      // else on the vendor profile.
      body: JSON.stringify({
        capability_statement: text,
        capability_keywords_raw: raw,
      }),
    });
    setBusy(false);
    if (!res.ok) {
      setError("Could not save. Nothing was changed.");
      return;
    }
    startTransition(() => router.refresh());
  }

  const working = busy || pending;

  return (
    <section
      data-bid-vocabulary
      className="mb-6 rounded-card border border-border bg-surface p-card"
    >
      <h2 className="mb-1 font-heading text-base font-medium text-ink">What you bid on</h2>
      <p className="mb-3 max-w-3xl text-xs text-muted">
        These terms rank your opportunity feed.{" "}
        {gateEnabled
          ? "The narrow feed is on, so a tender matching none of them is excluded."
          : "Nothing is hidden because of them unless you switch on the narrow feed yourself."}{" "}
        Reach is how many of the {corpusOpen} open tenders each term would keep on its own.
      </p>

      <label className="block text-xs font-medium text-ink">Capability and expertise</label>
      <textarea
        data-field-capability
        rows={3}
        value={text}
        onChange={(e) => setText(e.target.value)}
        className="mt-1 w-full rounded-control border border-hairline px-3 py-2 text-sm"
      />

      <label className="mt-3 block text-xs font-medium text-ink">
        Keywords you bid on (comma separated)
      </label>
      <input
        data-field-capability-keywords
        value={raw}
        onChange={(e) => setRaw(e.target.value)}
        className="mt-1 w-full rounded-control border border-hairline px-3 py-2 text-sm"
      />

      <button
        type="button"
        onClick={() => void save()}
        disabled={working}
        className="mt-3 rounded-control bg-primary px-3 py-1.5 text-sm font-medium text-on-primary disabled:opacity-50"
      >
        {working ? "Saving…" : "Save"}
      </button>
      {error && <p className="mt-2 text-sm text-danger">{error}</p>}

      {derived.length > 0 && (
        <div data-derived-terms className="mt-4 border-t border-hairline pt-3">
          <p className="text-xs font-medium text-ink">
            Also gating your feed, from what you recorded elsewhere on this page
          </p>
          <p className="mb-2 text-xs text-muted">
            Read-only here — change them where they are recorded.
          </p>
          <ul className="flex flex-wrap gap-1.5">
            {derived.map((t) => (
              <li
                key={t.term}
                className="rounded-full bg-surface-alt px-2 py-0.5 text-xs text-muted"
                title={`${SOURCE_LABEL[t.source]}${t.origin ? ` ${t.origin}` : ""} · reaches ${t.reach}`}
              >
                {t.term}{" "}
                <span className="tabular-nums opacity-70">{t.reach}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {dead.length > 0 && (
        <p data-dead-terms className="mt-3 text-xs text-warning">
          These match none of the {corpusOpen} open tenders, so they cannot affect anything:{" "}
          <span className="font-medium">{dead.map((t) => `“${t.term}”`).join(", ")}</span>
        </p>
      )}
    </section>
  );
}
```

- [ ] **Step 4: Run the unit test**

Run: `cd apps/web && pnpm test BidVocabulary`
Expected: PASS.

- [ ] **Step 5: Wire it into the capability page**

In `apps/web/app/(app)/capability/page.tsx`, add the two extra reads to the existing `Promise.all` (they are independent, and serial awaits are the documented latency trap — Step 8 adds `getLocale()` to the same call):

```tsx
  const [specsRes, registryRes, vocabRes, profileRes] = await Promise.all([
    engineFetch("/api/product-specs"),
    engineFetch("/api/spec-parameters"),
    engineFetch("/api/capability/vocabulary"),
    engineFetch("/api/profile"),
  ]);
```

then parse them beside the existing two and pass them into `CapabilityEditor`:

```tsx
  const vocabBody = vocabRes.ok ? await vocabRes.json().catch(() => null) : null;
  const profileBody = profileRes.ok ? await profileRes.json().catch(() => null) : null;
  const identity = profileBody?.ok ? (profileBody.data.legal_identity ?? {}) : {};
```

```tsx
    <CapabilityEditor
      specs={(specsBody?.ok ? specsBody.data.specs : []) as ProductSpec[]}
      registry={registryBody.data.parameters as ParamDef[]}
      vocabulary={vocabBody?.ok ? vocabBody.data : null}
      keywordsRaw={(identity.capability_keywords ?? []).join(", ")}
      statement={identity.capability_statement ?? ""}
    />
```

- [ ] **Step 6: Render it at the top of the editor**

In `apps/web/components/CapabilityEditor.tsx`, add the import beside the existing ones:

```tsx
import { BidVocabulary, type VocabTerm } from "./BidVocabulary";
```

add the exported type for what the page passes down:

```tsx
export type Vocabulary = {
  terms: VocabTerm[];
  corpus_open: number;
  gate_enabled: boolean;
};
```

extend the component's props (keep every existing prop):

```tsx
export function CapabilityEditor({
  specs,
  registry,
  vocabulary,
  keywordsRaw,
  statement,
}: {
  specs: ProductSpec[];
  registry: ParamDef[];
  vocabulary: Vocabulary | null;
  keywordsRaw: string;
  statement: string;
}) {
```

and render it as the first child inside `<main>`, immediately after the opening tag and before the existing header. The guard matters: the vocabulary is a separate engine read, and a failed read must leave the envelopes editable rather than blanking the page.

```tsx
      {vocabulary && (
        <BidVocabulary
          terms={vocabulary.terms}
          keywordsRaw={keywordsRaw}
          statement={statement}
          corpusOpen={vocabulary.corpus_open}
          gateEnabled={vocabulary.gate_enabled}
        />
      )}
```

- [ ] **Step 7: Remove the section from the profile and point at its new home**

In `apps/web/components/ProfileForm.tsx`, delete the whole `<section>` whose heading is `t("What you bid on")` (it spans the capability textarea, the keyword input, the `KeywordSuggestions` mount and the `unlikelyKeywords` warning), and replace it with:

```tsx
{/* Moved to /capability, where the other two thirds of the vocabulary already live: the
    GeM category names and the envelopes' standard references. This page answers "are we
    eligible to bid"; that one answers "what can we make and bid on". */}
<section className="rounded-card border border-hairline bg-surface-alt p-card">
  <h2 className="mb-1 font-heading text-base font-medium text-ink">{t("What you bid on")}</h2>
  <p className="text-xs text-muted">
    {t("Your capability statement and the keywords that rank your feed now live with your product capability.")}{" "}
    <a href="/capability" className="font-medium text-primary">
      {t("Open capability")}
    </a>
  </p>
</section>
```

Then remove any imports left unused (`KeywordSuggestions`, `splitKeywords`, `unlikelyKeywords`) — `pnpm lint` will name them. Keep `splitKeywords`/`unlikelyKeywords` exported from their module: `ProfileForm.test.ts` tests them directly, and those tests must not be deleted.

- [ ] **Step 8: Move the suggestions affordance**

`KeywordSuggestions` writes into the keyword input, so it has to follow it. Its own guardrail is unchanged and must stay: it proposes, a human saves, so no model authors a term that gates a feed (G-9).

In `apps/web/components/BidVocabulary.tsx`, add the import:

```tsx
import { KeywordSuggestions } from "./KeywordSuggestions";
```

add `websiteUrl` and `locale` to the props (the page already has both on the profile identity):

```tsx
  websiteUrl,
  locale,
}: {
  terms: VocabTerm[];
  keywordsRaw: string;
  statement: string;
  corpusOpen: number;
  gateEnabled: boolean;
  websiteUrl: string;
  locale: Locale;
}) {
```

add the append helper beside the other state:

```tsx
  // Terms land in the field the user is editing and are saved by the ordinary Save below.
  // That gap is the guardrail, not the click count: keywords feed the one rule that HIDES
  // tenders, so a model writing them straight through would be model-driven exclusion (G-9)
  // by a longer route.
  function append(fresh: string[]) {
    const have = raw.trim();
    setRaw(have ? `${have}, ${fresh.join(", ")}` : fresh.join(", "));
  }
```

and render it directly under the keyword input, above the Save button:

```tsx
      <KeywordSuggestions
        websiteUrl={websiteUrl}
        currentKeywords={raw}
        locale={locale}
        onAccept={(kw) => append([kw])}
        onAcceptMany={append}
      />
```

Import `type Locale` from `@/lib/i18n`. Then thread both through `CapabilityEditor` exactly as `keywordsRaw` is threaded in Steps 5 and 6 — add `websiteUrl: string` and `locale: Locale` to its props and pass them straight down to `BidVocabulary`.

The page supplies them. In `apps/web/app/(app)/capability/page.tsx` add to the imports:

```tsx
import { getLocale } from "@/lib/locale";
import type { Locale } from "@/lib/i18n";
```

and resolve the locale alongside the four engine reads — it reads cookies, so it is awaited, and putting it in the same `Promise.all` keeps it off the critical path:

```tsx
  const [specsRes, registryRes, vocabRes, profileRes, locale] = await Promise.all([
    engineFetch("/api/product-specs"),
    engineFetch("/api/spec-parameters"),
    engineFetch("/api/capability/vocabulary"),
    engineFetch("/api/profile"),
    getLocale(),
  ]);
```

then pass `websiteUrl={identity.website_url ?? ""}` and `locale={locale}` to `CapabilityEditor` beside the props added in Step 5.

- [ ] **Step 9: Verify the web layer**

Run: `cd apps/web && pnpm typecheck && pnpm lint && pnpm test`
Expected: all exit 0, including the existing `ProfileForm.test.ts`.

- [ ] **Step 10: Browser verification**

Run `/verify` on `/capability` and `/profile` as FIX-1. Assert: `[data-bid-vocabulary]` renders on `/capability` with the keyword input and `[data-derived-terms]` listing terms the user did not type; `/profile` no longer renders `[data-field-capability-keywords]` and does render the pointer link to `/capability`; saving a keyword on `/capability` persists across a reload; zero console errors; zero unexpected 4xx/5xx. Attach screenshots.

- [ ] **Step 11: Commit**

```bash
git add apps/web/components/BidVocabulary.tsx apps/web/components/BidVocabulary.test.ts apps/web/components/CapabilityEditor.tsx apps/web/components/ProfileForm.tsx "apps/web/app/(app)/capability/page.tsx"
git commit -m "feat(capability): the keyword editor moves to where its vocabulary lives

Two of the three sources already lived on /capability. The profile answers 'are
we eligible'; this screen answers 'what can we make and bid on'. Tables are
unchanged — PUT /api/profile already takes partial writes.

Derived terms are now shown rather than silently merged: the gate has run on 31
terms since 2026-09-14 while every screen showed 16, so an exclusion could be
explained by a term the user had never seen. Reach ships alongside, because a
dead term and a quiet market look identical."
```

**Phase 3 gate:** typecheck/lint/test green, `/verify` evidence attached. Then deploy (`tools/deploy-uml-feed-fixes.sh` is the pattern; a fresh script is not needed) and confirm on the live UML workspace that `/capability` shows 31 terms with sources, and that the reach column marks any term matching nothing.

---

## Out of scope, deliberately

- **Merging `product_specs` into `vendor_profiles`.** Different cardinality (N rows with typed parameters versus one row of eligibility facts), different consumers (the spec comparator versus the eligibility comparators), different update cadence. The confusion is two screens both called "capability", and moving the keyword editor fixes that without a migration.
- **Deriving keywords entirely, with no input box.** A standard number and a GeM category name are narrow strings; "wire rope" is doing most of the work and is neither. A bidder also legitimately pursues things they have not recorded an envelope for, and full derivation would silently drop that.
- **Inverting capability data entry** — showing the parameters real tenders ask for and collecting ranges against them. It is the right next step and it is unbuildable until Phase 1 has run extraction on real tenders, because until then nobody knows which parameters matter. Revisit with the Phase 1 evidence in hand.
- **Wiring spec-fit into the readiness hub, the lock gate or the export gate.** A comparator that can block a submission before it has been seen on twenty real tenders is how a product starts refusing to work — the same reasoning that kept the shredder out of the export gate.
- **A pre-filter that skips "obviously non-product" lines before spending a model call.** Tempting, and it would be a heuristic that silently drops a real product line. The budget in Task 1 bounds the cost without guessing.
