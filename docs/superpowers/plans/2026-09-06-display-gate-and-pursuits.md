# Pursuit Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make "Pursue this opportunity" a real object, so discovery, tender documents, proposals and outcomes are one chain instead of four disconnected ones. Phase 1 first corrects a docstring whose overreach nearly caused a much worse change.

**Architecture:** Phase 1 is documentation only — it narrows `registry.display_reviewed`'s stated scope to the surface it was actually built to gate, so no future reader "fixes" the apparent inconsistency by cutting the opportunity feed. **No behaviour changes and no rows stop being shown.** Phase 2 adds a `pursuits` table whose only job is identity: it links a shared-corpus `opportunities` row to a workspace-private `tenders` row, carries the portal reference and deadline across that boundary, and gives every later analytic a stable key. Documents are still uploaded by the human — the pursuit removes the re-keying, not the download.

**Tech Stack:** Python 3.12 / FastAPI / pytest (engine) · Supabase Postgres + RLS · Next.js 15 / TypeScript / Vitest (web)

---

## Phase 1 was wrong in its first draft. Read this before touching `registry.py`.

The first version of this plan proposed enforcing `registry.display_reviewed` on the feed read path, which would have removed BidAssist rows — IREPS, Telangana, Andhra Pradesh, Haryana, SAIL, Coal India, Rajasthan, CPPP — from UML's feed. Roughly 57% of the sampled Indian corpus. **Do not do this.** It was rejected by the decision owner, and the git history says it was never a defect to begin with:

| Date | Commit | What happened |
|---|---|---|
| 2026-08-29 | `f737145` | BidAssist notices enabled on the feed — "the G-8 question was ruled on" |
| 2026-09-03 | `53a000b` | `display_reviewed` introduced — "the price history reads both award sources, and **ships gated**" |

The field was created **five days after** notices shipped, in a commit about the price screen, to gate the price screen. It does gate the price screen. Notices did not slip past it; it did not exist yet and was not written for them.

The external review that surfaced this read the field's docstring — "never blend into anything a customer sees" — as a universal rule and inferred that `refresh_corpus` was in violation. The *mechanical* claim is true and verifiable: exactly one call site checks the field, `refresh_licensed_awards` at `discovery/ingest.py:671`. The *interpretation* is false. **Verifying the mechanism is not verifying the intent**, and only the intent decided whether this was a bug.

What actually exists is a docstring claiming more scope than the field has. That is a real trap — the next reader will draw the same conclusion — and Phase 1 closes it with a comment change, not a filter.

**The unread partner agreement is still an open risk.** It is `usha-martin.md` assumption 10, it predates both commits, and it is a commercial task: someone reads the contract. It is not on this plan, because no code change resolves it and cutting coverage does not substitute for reading it.

---

## File Structure

**Phase 1 — narrow the docstring (no behaviour change)**

| File | Change | Responsibility |
|---|---|---|
| `services/engine/app/discovery/registry.py` | Modify comments only | State which surface `display_reviewed` gates, and which decision governs notices. |
| `services/engine/app/discovery/ingest.py` | Modify comment only | The award guard names its own scope so it does not read as a universal rule. |
| `docs/feedback/usha-martin.md` | Modify | Record why the feed is not gated, so the question is settled in writing rather than re-derived. |

**Phase 2 — pursuits**

| File | Change | Responsibility |
|---|---|---|
| `services/engine/migrations/0039_pursuits.sql` | Create | The `pursuits` table, its RLS policy and its state enum. |
| `services/engine/app/db.py` | Modify (add three functions) | Pursuit reads/writes. |
| `services/engine/app/opportunities_routes.py` | Modify | `POST /api/opportunities/{id}/pursue`. |
| `services/engine/app/tenders.py` | Modify (`_process_ingest`, `ingest_tender`) | Accepts `pursuit_id`, links the created tender, backfills the reference. |
| `apps/web/components/OpportunityFeed.tsx` | Modify | The Pursue action. |
| `apps/web/app/(app)/tenders/upload/page.tsx` | Modify | Pursuit context banner + document links. |
| `services/engine/tests/test_pursuits.py` | Create | Pursuit creation, idempotency, cross-workspace refusal. |
| `services/engine/tests/isolation/test_pursuit_isolation.py` | Create | RLS proof against the ephemeral stack. |

---
# PHASE 1 — Say what the field gates, change nothing it does

Three comment edits and one doc entry. **No function signature changes, no query changes, no rows stop being displayed.** If a step in this phase makes a test fail, you have done more than the phase asks.

### Task 1: Narrow `display_reviewed` to the surface it gates

**Files:**
- Modify: `services/engine/app/discovery/registry.py` — the `display_reviewed` field comment (~line 27)

- [ ] **Step 1: Replace the field comment**

The current comment says "A blank date means acquire if you like, but never blend into anything a customer sees." That sentence describes a rule the code does not implement and, per the git history above, was never meant to. Replace it:

```python
    #: When someone confirmed this source's AWARD data may be shown to a customer, and by whom.
    #:
    #: SCOPE — read this before adding a caller. This gates the PRICE HISTORY surface and
    #: nothing else. It is enforced in exactly one place, `ingest.refresh_licensed_awards`,
    #: and that is not an oversight to be tidied up:
    #:
    #:   2026-08-29  f737145  BidAssist NOTICES enabled on the opportunity feed (G-8 ruled on)
    #:   2026-09-03  53a000b  this field created, to ship the price screen gated
    #:
    #: The field postdates the notice decision by five days and was written for prices. An
    #: earlier review read this comment as a universal rule, concluded the feed was in
    #: violation, and proposed filtering un-reviewed sources out of it — which would have
    #: removed roughly 57% of the Indian corpus (IREPS, Telangana, AP, Haryana, SAIL, Coal
    #: India, Rajasthan, CPPP) from a live customer's feed to fix a bug that did not exist.
    #: Rejected by the decision owner, 2026-09-06.
    #:
    #: Why awards and notices legitimately differ: a notice is a public procurement fact that
    #: the issuing portal publishes for bidders to act on, and the feed shows facts and deep
    #: links (`efdc512` also removed the vendor's name from that screen). An award ladder with
    #: named sellers and their prices is the commercially valuable part of a licensed feed and
    #: the part a licence is most likely to restrict. Different exposure, different gate.
    #:
    #: The partner agreement is still unread (docs/feedback/usha-martin.md, assumption 10).
    #: That is a commercial task and no code change substitutes for it. If reading it says the
    #: notice feed must also be gated, that is a product decision with a named owner and a
    #: visible-count requirement (S14-D2) — not a filter somebody adds while tidying.
    display_reviewed: str = ""
```

- [ ] **Step 2: Verify nothing behavioural changed**

```bash
cd services/engine && git diff --stat && uv run pytest tests/test_award_sources.py tests/test_discovery_markets.py -v
```
Expected: the diff touches comment lines only; both suites pass unchanged.

- [ ] **Step 3: Commit**

```bash
git add services/engine/app/discovery/registry.py
git commit -m "docs(discovery): display_reviewed gates prices, and says so"
```

---

### Task 2: Make the award guard name its own scope

**Files:**
- Modify: `services/engine/app/discovery/ingest.py` — the guard comment in `refresh_licensed_awards` (~line 671)

- [ ] **Step 1: Replace the guard comment**

The current comment argues that the gate belongs at acquisition rather than at the screen — correct for awards, and the sentence a reader generalises into "so it should apply to the feed too". Bound it:

```python
    if not source.display_reviewed.strip():
        # Acquisition is cleared; showing AWARD DATA to a customer is not. This is the price
        # screen's gate and only the price screen's. It stops here rather than at the screen
        # because a corpus that already holds award rows is one `postgrest_filter` away from
        # displaying them, and the gate would then depend on every future read path
        # remembering it exists.
        #
        # This reasoning does NOT extend to the opportunity feed, and the argument above is
        # exactly the shape that makes it look like it should. Notices ship under a separate,
        # earlier decision (f737145) and the feed is not gated on this field. See the SCOPE
        # note on `Source.display_reviewed` before changing either.
```

- [ ] **Step 2: Verify**

```bash
cd services/engine && uv run pytest tests/test_award_sources.py -v && uv run ruff check app/
```
Expected: PASS, ruff clean, comment-only diff.

- [ ] **Step 3: Commit**

```bash
git add services/engine/app/discovery/ingest.py
git commit -m "docs(discovery): the award gate bounds its own reasoning"
```

---

### Task 3: Settle it in the customer file

**Files:**
- Modify: `docs/feedback/usha-martin.md` — the BidAssist section

- [ ] **Step 1: Append the decision**

Add under the existing BidAssist notes:

```markdown
**Ruled 2026-09-06 — the feed is NOT gated on `display_reviewed`, and this is deliberate.**
An architectural review flagged that only `refresh_licensed_awards` checks the field and read
that as the notice feed escaping a gate. It is not: the field was created 2026-09-03 (`53a000b`)
to ship the price screen gated, five days AFTER notices went live (`f737145`). Gating the feed
on it would have cut roughly 57% of the Indian corpus from UML's screen — IREPS, Telangana, AP,
Haryana, SAIL, Coal India, Rajasthan, CPPP — to close a gap that was an artefact of reading one
docstring too broadly. Rejected by the decision owner. `registry.py` now states the field's
scope so the same conclusion is not reached again.

**Assumption 10 is unchanged and is still the riskiest open item on this page.** Nobody has read
the partner agreement. Cutting coverage was never a substitute for reading it, and the two
should not be conflated again: one is a commercial task with a named owner, the other was a
proposed product regression.
```

- [ ] **Step 2: Commit**

```bash
git add docs/feedback/usha-martin.md
git commit -m "docs(uml): record why the opportunity feed is not licence-gated"
```

---

# PHASE 2 — The pursuit workflow

### Task 4: The pursuits table

**Files:**
- Create: `services/engine/migrations/0039_pursuits.sql`

- [ ] **Step 1: Write the migration**

```sql
-- Pursuits — the identity that survives the discovery/tender boundary.
--
-- `opportunities` is a SHARED corpus row: one per (source_id, portal_ref_no), visible to every
-- workspace whose market and rules reach it. `tenders` is workspace-private and carries the
-- bid. Nothing joined them, so a client who found a tender in the feed downloaded the package
-- from the portal, uploaded it back, and re-typed the reference, the deadline and the
-- authority — on every pursuit. This table is that join.
--
-- WHY A TABLE AND NOT A COLUMN ON `tenders`. A nullable `opportunity_id` on `tenders` would be
-- the smaller diff and the wrong shape: the pursuit begins BEFORE the tender exists (the user
-- clicks Pursue, then uploads, possibly days later, possibly never), and a lifecycle whose
-- first state cannot be represented is a lifecycle that gets reconstructed from guesses later.
--
-- WHY NOT ON `opportunities`. That row is shared. Writing "workspace 7 is pursuing this" onto
-- it puts tenant-private intent into a corpus every other tenant reads. The wall (F13) is about
-- the two products, but the same reasoning governs the two scopes.
--
-- `on delete restrict` on opportunity_id: a pursued opportunity must not be able to vanish from
-- under a live bid during a corpus rebuild.

do $$ begin
  create type public.pursuit_state as enum (
    'pursuing',   -- claimed from the feed; documents may not be uploaded yet
    'ingested',   -- a tender row exists and is linked
    'submitted',  -- the bidder says they submitted. WE never read the portal (G-1)
    'abandoned'   -- decided not to bid; kept, because why-we-did-not-bid is data
  );
exception when duplicate_object then null; end $$;

create table if not exists public.pursuits (
  id             uuid primary key default gen_random_uuid(),
  workspace_id   uuid not null references public.workspaces(id)    on delete cascade,
  opportunity_id uuid not null references public.opportunities(id) on delete restrict,
  -- Null until the package is uploaded. `set null` rather than cascade: deleting a tender must
  -- not erase the record that this opportunity was pursued and what came of it.
  tender_id      uuid          references public.tenders(id)       on delete set null,

  state          public.pursuit_state not null default 'pursuing',
  -- Bare uuids, matching 0027/0029/0038: no FK into auth, which the ephemeral CI stack rebuilds
  -- from these migrations alone.
  owner          uuid,
  created_by     uuid,

  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  submitted_at   timestamptz,

  constraint pursuits_ingested_has_a_tender
    check (state not in ('ingested', 'submitted') or tender_id is not null),
  constraint pursuits_submitted_has_a_time
    check (state <> 'submitted' or submitted_at is not null),

  -- workspace_id INSIDE the key. The engine writes with the service role and bypasses RLS, so a
  -- conflict target omitting the scope column can reassign another workspace's row (0027).
  -- This is also what makes POST /pursue idempotent: a double-click is one pursuit.
  unique (workspace_id, opportunity_id)
);

create index if not exists pursuits_workspace_idx on public.pursuits(workspace_id, state);
create index if not exists pursuits_tender_idx    on public.pursuits(workspace_id, tender_id);

create or replace function public.pursuits_touch()
returns trigger language plpgsql as $$
begin
  new.updated_at := now();
  return new;
end $$;

drop trigger if exists pursuits_touch_trigger on public.pursuits;
create trigger pursuits_touch_trigger
  before update on public.pursuits
  for each row execute function public.pursuits_touch();

alter table public.pursuits enable row level security;

drop policy if exists pursuits_workspace_all on public.pursuits;
create policy pursuits_workspace_all on public.pursuits for all
  using (workspace_id = public.current_workspace_id())
  with check (workspace_id = public.current_workspace_id());

comment on table public.pursuits is
  'The identity linking a shared-corpus opportunity to a workspace-private tender. Created when '
  'a user claims an opportunity from the feed, linked when the package is ingested, and the key '
  'every discovery-to-outcome analytic joins on.';
```

- [ ] **Step 2: Verify it replays onto an empty database**

Run: `cd services/engine && supabase start && ./tools/local-db.sh`
Expected: migrations 0001→0039 apply clean. `local-db.sh` refuses any non-localhost `DB_URL` — do not override that.

- [ ] **Step 3: Commit**

```bash
git add services/engine/migrations/0039_pursuits.sql
git commit -m "feat(pursuits): the missing identity between a found tender and a bid"
```

---

### Task 5: Pursuit reads and writes

**Files:**
- Modify: `services/engine/app/db.py`
- Test: `services/engine/tests/test_pursuits.py`

- [ ] **Step 1: Write the failing test**

Create `services/engine/tests/test_pursuits.py`:

```python
"""Pursuit persistence. The scope column is in every key and every filter — the engine writes
with the service role, which bypasses RLS, so ownership is enforced in code here."""

from app import db


def test_create_pursuit_scopes_the_conflict_target(monkeypatch):
    captured: dict = {}

    def _fake_rest(method, table, params=None, json=None, headers=None):
        captured.update({"method": method, "table": table,
                         "params": params or {}, "json": json})
        return [{"id": "p-1", "workspace_id": "ws-1", "opportunity_id": "o-1",
                 "tender_id": None, "state": "pursuing"}]

    monkeypatch.setattr(db, "_rest", _fake_rest)
    row = db.create_pursuit("ws-1", "o-1", "user-1")
    assert row["id"] == "p-1"
    assert captured["params"]["on_conflict"] == "workspace_id,opportunity_id"
    assert captured["json"]["workspace_id"] == "ws-1"


def test_link_tender_filters_on_workspace(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        db, "_rest",
        lambda m, t, params=None, json=None, headers=None: (
            captured.update({"params": params or {}, "json": json}) or [{"id": "p-1"}]
        ),
    )
    db.link_pursuit_tender("ws-1", "p-1", "t-9")
    assert captured["params"]["workspace_id"] == "eq.ws-1"
    assert captured["params"]["id"] == "eq.p-1"
    assert captured["json"]["tender_id"] == "t-9"
    assert captured["json"]["state"] == "ingested"


def test_get_pursuit_is_workspace_scoped(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        db, "_rest",
        lambda m, t, params=None, json=None, headers=None: (
            captured.update({"params": params or {}}) or []
        ),
    )
    assert db.get_pursuit("ws-1", "p-1") is None
    assert captured["params"]["workspace_id"] == "eq.ws-1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/engine && uv run pytest tests/test_pursuits.py -v`
Expected: FAIL — `AttributeError: module 'app.db' has no attribute 'create_pursuit'`

- [ ] **Step 3: Write minimal implementation**

Add to `services/engine/app/db.py`:

```python
# ---------- pursuits (0039) ----------
def create_pursuit(workspace_id: str, opportunity_id: str, user_id: str) -> dict:
    """Claim an opportunity. Idempotent: the unique key makes a double-click one pursuit.

    `on_conflict` carries workspace_id because the engine writes with the service role and
    bypasses RLS — a conflict target omitting the scope column can reassign another
    workspace's row (0027).
    """
    rows = _rest(
        "POST", "pursuits",
        params={"on_conflict": "workspace_id,opportunity_id"},
        json={"workspace_id": workspace_id, "opportunity_id": opportunity_id,
              "created_by": user_id, "owner": user_id},
        headers={"Prefer": "resolution=merge-duplicates,return=representation"},
    ) or []
    return rows[0] if rows else {}


def get_pursuit(workspace_id: str, pursuit_id: str) -> dict | None:
    rows = _rest(
        "GET", "pursuits",
        params={"workspace_id": f"eq.{workspace_id}", "id": f"eq.{pursuit_id}",
                "select": "*,opportunities(*)"},
    ) or []
    return rows[0] if rows else None


def link_pursuit_tender(workspace_id: str, pursuit_id: str, tender_id: str) -> dict | None:
    """Attach the ingested tender. Workspace-filtered so a foreign id cannot be bound."""
    rows = _rest(
        "PATCH", "pursuits",
        params={"workspace_id": f"eq.{workspace_id}", "id": f"eq.{pursuit_id}"},
        json={"tender_id": tender_id, "state": "ingested"},
        headers={"Prefer": "return=representation"},
    ) or []
    return rows[0] if rows else None
```

- [ ] **Step 4: Run tests**

Run: `cd services/engine && uv run pytest tests/test_pursuits.py -v`
Expected: PASS, 3 passed

- [ ] **Step 5: Commit**

```bash
git add services/engine/app/db.py services/engine/tests/test_pursuits.py
git commit -m "feat(pursuits): persistence, scoped in every key and filter"
```

---

### Task 6: The pursue endpoint

**Files:**
- Modify: `services/engine/app/opportunities_routes.py`
- Test: `services/engine/tests/test_pursuits.py`

- [ ] **Step 1: Write the failing test**

Append to `services/engine/tests/test_pursuits.py`:

```python
import pytest
from app.errors import ApiError
from app import opportunities_routes as routes


class _User:
    workspace_id = "ws-1"
    user_id = "user-1"


@pytest.mark.asyncio
async def test_pursue_refuses_an_opportunity_this_workspace_cannot_see(monkeypatch):
    """The feed is scoped; the endpoint must be too, or a guessed id bypasses the gate."""
    monkeypatch.setattr(routes.db, "get_match", lambda ws, oid: None)
    with pytest.raises(ApiError) as e:
        await routes.pursue("o-unknown", _User())
    assert e.value.status == 404
    assert e.value.code == "OPPORTUNITY_NOT_IN_FEED"


@pytest.mark.asyncio
async def test_pursue_is_idempotent(monkeypatch):
    monkeypatch.setattr(routes.db, "get_match", lambda ws, oid: {"opportunity_id": oid})
    monkeypatch.setattr(
        routes.db, "create_pursuit",
        lambda ws, oid, uid: {"id": "p-1", "opportunity_id": oid, "state": "pursuing"},
    )
    first = await routes.pursue("o-1", _User())
    second = await routes.pursue("o-1", _User())
    assert first["data"]["id"] == second["data"]["id"] == "p-1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/engine && uv run pytest tests/test_pursuits.py -v`
Expected: FAIL — `AttributeError: module 'app.opportunities_routes' has no attribute 'pursue'`

- [ ] **Step 3: Write minimal implementation**

Add to `services/engine/app/opportunities_routes.py`, after `patch_match`:

```python
@router.post("/api/opportunities/{opportunity_id}/pursue")
async def pursue(opportunity_id: str, user: CurrentUser) -> dict:
    """Claim an opportunity from the feed and open a pursuit.

    Membership is not enough: the opportunity must be in THIS workspace's feed. `opportunities`
    is a shared corpus, so an id is guessable and a bare workspace check would let a caller
    pursue a row the licence gate or their own rules keep off their screen.

    We do not fetch the tender documents here. The bidder downloads them from the portal and
    uploads the package; this endpoint carries the reference, deadline and authority across so
    none of it is re-typed, and gives everything downstream one key to join on.
    """
    if db.get_match(user.workspace_id, opportunity_id) is None:
        raise ApiError(404, "OPPORTUNITY_NOT_IN_FEED",
                       "that opportunity is not in this workspace's feed")
    return ok(db.create_pursuit(user.workspace_id, opportunity_id, user.user_id))
```

If `db.get_match` does not exist, add it beside `get_feed` in `db.py`:

```python
def get_match(workspace_id: str, opportunity_id: str) -> dict | None:
    """One feed row, under the same display and market scope the feed itself uses."""
    rows = _rest(
        "GET", "opportunity_matches",
        params={"workspace_id": f"eq.{workspace_id}",
                "opportunity_id": f"eq.{opportunity_id}",
                **_market_scope(get_workspace_markets(workspace_id))},
    ) or []
    return rows[0] if rows else None
```

- [ ] **Step 4: Run tests**

Run: `cd services/engine && uv run pytest tests/test_pursuits.py -v && uv run ruff check app/`
Expected: PASS, ruff clean

- [ ] **Step 5: Commit**

```bash
git add services/engine/app/opportunities_routes.py services/engine/app/db.py services/engine/tests/test_pursuits.py
git commit -m "feat(pursuits): POST /api/opportunities/{id}/pursue, scoped to the caller's own feed"
```

---

### Task 7: Ingest links the pursuit and inherits the reference

**Files:**
- Modify: `services/engine/app/tenders.py` — `_process_ingest` (line 97) and `ingest_tender` (line 158)
- Test: `services/engine/tests/test_pursuits.py`

- [ ] **Step 1: Write the failing test**

Append to `services/engine/tests/test_pursuits.py`:

```python
def test_ingest_backfills_the_reference_from_the_pursuit(monkeypatch):
    """The portal published the number. A document that omits it should not lose it."""
    from app import tenders

    monkeypatch.setattr(tenders.db, "create_tender",
                        lambda ws, title: {"id": "t-1"})
    captured: dict = {}
    monkeypatch.setattr(tenders.db, "set_tender_meta",
                        lambda tid, ws, num, auth: captured.update(
                            {"num": num, "auth": auth}))
    monkeypatch.setattr(tenders.db, "get_pursuit", lambda ws, pid: {
        "id": pid, "opportunities": {"portal_ref_no": "GEM/2026/B/7876746",
                                     "authority": "South Eastern Railway"}})
    linked: dict = {}
    monkeypatch.setattr(tenders.db, "link_pursuit_tender",
                        lambda ws, pid, tid: linked.update({"p": pid, "t": tid}))

    tenders._apply_pursuit_context("ws-1", "p-1", "t-1", tender_number="", authority="")

    assert captured["num"] == "GEM/2026/B/7876746"
    assert captured["auth"] == "South Eastern Railway"
    assert linked == {"p": "p-1", "t": "t-1"}


def test_the_document_wins_over_the_portal(monkeypatch):
    """A number read off the document is the primary source; the feed is the fallback."""
    from app import tenders

    captured: dict = {}
    monkeypatch.setattr(tenders.db, "set_tender_meta",
                        lambda tid, ws, num, auth: captured.update({"num": num}))
    monkeypatch.setattr(tenders.db, "get_pursuit", lambda ws, pid: {
        "id": pid, "opportunities": {"portal_ref_no": "FEED/REF", "authority": ""}})
    monkeypatch.setattr(tenders.db, "link_pursuit_tender", lambda ws, pid, tid: None)

    tenders._apply_pursuit_context("ws-1", "p-1", "t-1",
                                   tender_number="DOC/REF", authority="")
    assert captured["num"] == "DOC/REF"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/engine && uv run pytest tests/test_pursuits.py -k pursuit_context -v`
Expected: FAIL — `AttributeError: module 'app.tenders' has no attribute '_apply_pursuit_context'`

- [ ] **Step 3: Write minimal implementation**

Add to `services/engine/app/tenders.py`:

```python
def _apply_pursuit_context(
    workspace_id: str, pursuit_id: str, tender_id: str,
    tender_number: str, authority: str,
) -> None:
    """Link the pursuit to the tender and fill in what the document did not state.

    Precedence is document-first, deliberately. The tender package is the legal artefact and
    `display_title`/`extract_meta` already prefer it; the feed row is a portal listing about
    that document. Only where the document is silent does the portal's own reference fill the
    gap — and it is the portal's published value, not an inference.

    Non-fatal by construction. A pursuit that cannot be read must never fail an upload: the
    package is the product and the link is bookkeeping.
    """
    try:
        pursuit = db.get_pursuit(workspace_id, pursuit_id)
        if pursuit is None:
            log.warning("pursuit %s not found for workspace %s — tender %s ingested unlinked",
                        pursuit_id, workspace_id, tender_id)
            return
        opp = pursuit.get("opportunities") or {}
        number = tender_number or opp.get("portal_ref_no") or ""
        auth = authority or opp.get("authority") or ""
        if number or auth:
            db.set_tender_meta(tender_id, workspace_id, number, auth)
        db.link_pursuit_tender(workspace_id, pursuit_id, tender_id)
    except Exception:  # noqa: BLE001 — bookkeeping must not be able to break ingest
        log.exception("pursuit linking failed for tender %s — ingest continues", tender_id)
```

Change `_process_ingest`'s signature and add the call before the return:

```python
def _process_ingest(workspace_id: str, documents: list[tuple[str, bytes]], title: str,
                    pursuit_id: str = "") -> dict:
```

```python
    if pursuit_id:
        _apply_pursuit_context(workspace_id, pursuit_id, tender["id"],
                               meta.tender_number or "", meta.authority or "")
```

Change `ingest_tender` to accept and forward it:

```python
async def ingest_tender(
    user: CurrentUser, file: Annotated[list[UploadFile], File()],
    title: str = "", pursuit_id: str = "",
) -> dict:
```

```python
    return ok(await run_in_threadpool(
        _process_ingest, user.workspace_id, documents, name, pursuit_id
    ))
```

- [ ] **Step 4: Run tests**

Run: `cd services/engine && uv run pytest tests/test_pursuits.py tests/test_ingest.py -v`
Expected: PASS. `test_ingest.py` must stay green — `pursuit_id` defaults to `""` precisely so the existing upload path is untouched.

- [ ] **Step 5: Commit**

```bash
git add services/engine/app/tenders.py services/engine/tests/test_pursuits.py
git commit -m "feat(pursuits): ingest links the pursuit and inherits what the document omitted"
```

---

### Task 8: The Pursue action in the feed

**Files:**
- Modify: `apps/web/components/OpportunityFeed.tsx`
- Test: `apps/web/components/OpportunityFeed.test.ts`

- [ ] **Step 1: Write the failing test**

Append to `apps/web/components/OpportunityFeed.test.ts`:

```typescript
import { pursuitHref } from "./OpportunityFeed";

describe("pursue action", () => {
  test("carries the pursuit id to the upload screen", () => {
    expect(pursuitHref("p-42")).toBe("/tenders/upload?pursuit=p-42");
  });

  test("encodes an id that would otherwise break the query string", () => {
    expect(pursuitHref("a b&c")).toBe("/tenders/upload?pursuit=a%20b%26c");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/web && pnpm vitest run components/OpportunityFeed.test.ts`
Expected: FAIL — `pursuitHref` is not exported

- [ ] **Step 3: Write minimal implementation**

In `apps/web/components/OpportunityFeed.tsx`:

```typescript
export function pursuitHref(pursuitId: string): string {
  return `/tenders/upload?pursuit=${encodeURIComponent(pursuitId)}`;
}
```

Add a Pursue button to each in-scope row that POSTs to `/api/opportunities/${id}/pursue`, then routes to `pursuitHref(data.id)`. Disable it on first click — the endpoint is idempotent, but a double-submit that produces two navigations is still a bug (known-pitfalls: disable-on-first-click).

- [ ] **Step 4: Run tests**

Run: `cd apps/web && pnpm vitest run && pnpm typecheck && pnpm lint`
Expected: PASS, typecheck 0, lint 0

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/OpportunityFeed.tsx apps/web/components/OpportunityFeed.test.ts
git commit -m "feat(pursuits): Pursue on a feed row, straight into upload with context attached"
```

---

### Task 9: Upload screen carries the pursuit context

**Files:**
- Modify: `apps/web/app/(app)/tenders/upload/page.tsx`

- [ ] **Step 1: Read the pursuit and render the banner**

Read `?pursuit=` from `searchParams`, fetch the pursuit through the engine, and render above the dropzone: the portal reference, the authority, the closing date, the portal name, and the document links as external anchors.

The banner must say what we did not do:

```tsx
<p className="mt-2 text-xs text-muted">
  We do not download these for you — this product never signs in to a portal.
  Open each link, download the package, and drop it here.
</p>
```

- [ ] **Step 2: Forward the pursuit id on submit**

Append `pursuit_id` to the `FormData` posted to `/api/tenders/ingest`.

- [ ] **Step 3: Verify manually**

Run `pnpm dev 2>&1 | tee .claude/dev-server.log`, sign in as FIX-1, click Pursue on a feed row, and confirm the upload screen shows the reference and the links.

- [ ] **Step 4: Run checks and commit**

```bash
cd apps/web && pnpm typecheck && pnpm lint && pnpm test
git add "apps/web/app/(app)/tenders/upload/page.tsx"
git commit -m "feat(pursuits): the upload screen knows which tender you came for"
```

---

### Task 10: Isolation proof and ship

**Files:**
- Create: `services/engine/tests/isolation/test_pursuit_isolation.py`

- [ ] **Step 1: Write the isolation test**

```python
"""ET-6 for pursuits. Runs against the ephemeral stack only — `tools/local-db.sh` refuses any
non-localhost DB_URL because it drops and rebuilds `public`."""

import pytest
from tests.isolation.conftest import grant_membership, sign_in


@pytest.mark.isolation
def test_a_pursuit_is_invisible_to_another_workspace(ephemeral_db, seeded_opportunity):
    ws_a, ws_b = ephemeral_db.workspace("A"), ephemeral_db.workspace("B")
    grant_membership(ws_a, "priya@meridian.test")
    grant_membership(ws_b, "raj@other.test")

    token_a = sign_in("priya@meridian.test")
    created = ephemeral_db.post(
        f"/api/opportunities/{seeded_opportunity}/pursue", token=token_a
    )
    assert created["ok"] is True

    token_b = sign_in("raj@other.test")
    listed = ephemeral_db.get("/api/pursuits", token=token_b)
    assert created["data"]["id"] not in [p["id"] for p in listed["data"]]


@pytest.mark.isolation
def test_pursuing_the_same_opportunity_twice_is_one_row(ephemeral_db, seeded_opportunity):
    ws = ephemeral_db.workspace("A")
    grant_membership(ws, "priya@meridian.test")
    token = sign_in("priya@meridian.test")
    a = ephemeral_db.post(f"/api/opportunities/{seeded_opportunity}/pursue", token=token)
    b = ephemeral_db.post(f"/api/opportunities/{seeded_opportunity}/pursue", token=token)
    assert a["data"]["id"] == b["data"]["id"]
```

Cache the token per user — GoTrue rate-limits password grants and a 429 fails a random test, which reads as a product defect (known-pitfalls).

- [ ] **Step 2: Run against the ephemeral stack**

```bash
cd services/engine && supabase start && ./tools/local-db.sh && uv run pytest tests/isolation/test_pursuit_isolation.py -v
```
Expected: PASS, 2 passed

- [ ] **Step 3: Full verification**

```bash
cd services/engine && uv run pytest && uv run ruff check
cd ../../apps/web && pnpm typecheck && pnpm lint && pnpm test
```

- [ ] **Step 4: Apply migration 0039 to production BEFORE deploying code**

```bash
./tools/apply-migration.sh 0039_pursuits.sql
```
The script accepts any `2xx` — a `201` with an empty result array is success, not failure.

- [ ] **Step 5: Deploy per `docs/deploy.md`, then commit**

```bash
git add services/engine/tests/isolation/test_pursuit_isolation.py
git commit -m "test(pursuits): ET-6 isolation and idempotency against the ephemeral stack"
```

---

## What this plan deliberately does not do

- **No document auto-fetch.** Chosen explicitly. The presigned BidAssist links expire, and storing rather than deep-linking tender documents needs a fresh read of G-10 and the GeM §8 posture. The pursuit is built so auto-fetch drops in later as a queue feeding the same `pursuit_id` — nothing here has to be rebuilt for it.
- **No outcome writing.** `outcomes` still has no writer and Module D is still dark. That is the next slice and it is now cheap, because `pursuits.state` is the lifecycle it was missing. Do not fold it in here.
- **No change to the estimator or rubric.** Codex is right that `EstimateView.tsx:103` claims "calibrated" over a count-driven band, and that `directional_accuracy` has no call site so its guard can never fire. Both are real. Neither is on this plan's path, and mixing a claim-retraction into a schema change makes both harder to review.
- **Nothing gated on the pursuit.** It records and links; it blocks no lock, no analysis, no export. Same reasoning that kept spec-fit read-only in v1: a brand-new object that can block an export before it has been seen on twenty real tenders is how a product starts refusing to work.
- **No filtering of the opportunity feed, by any source, for any reason.** Withdrawn from this plan on 2026-09-06 — see the Phase 1 preamble. Coverage is what the feed is for; anything that reduces it needs a named owner and a decision, not a tidy-up.

## Self-review notes

- **Spec coverage:** Phase 1 (Tasks 1–3) settles the `display_reviewed` scope question in comments and the customer file. Phase 2 (Tasks 4–10) builds the pursuit chain. The one item from the review that is deliberately unplanned is the partner-agreement read, because it is commercial.
- **Type consistency:** `pursuit_id` is the parameter name in `_process_ingest`, `ingest_tender`, `_apply_pursuit_context`, the `FormData` field and the query string. `pursuit_state` values are `pursuing | ingested | submitted | abandoned` in the migration, the constraints and `link_pursuit_tender`.
- **Symbols verified against the tree at `aa4394d`:** `db.get_workspace_markets` exists (`db.py:1226`) and is the same resolver `list_opportunities` already uses — reuse it, do not add a second. `db.get_match` does not exist; Task 6 creates it. `db._market_scope` (`db.py:1334`) is where a feed-wide filter *would* go, which is exactly why Phase 1 records that one must not be added there without a decision.
- **Removed in revision:** `displayable_source_ids`, `_display_source_filter`, `count_withheld_for_display`, `withheldLabel` and `withheld_pending_review` were specified in the first draft and are now withdrawn. If you find a reference to any of them, it is a leftover — delete it rather than implementing it.
