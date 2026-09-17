# Supabase: run on the Free tier on purpose, not by luck

**Date:** 2026-09-17 · **Owner decision this plan serves:** upgrade the `tendercraft` org to Pro
for one billing cycle, then downgrade on or before 2026-10-24 **if the measured numbers say
Free is enough**. This plan exists so that decision is made from a ledger, not a feeling.
**Orchestrator:** this session. **Executors:** Opus 5 subagents, one per workstream, in git
worktrees, merged by the orchestrator in the order below.

## 0. What is true today (measured 2026-09-17)

The org hit 12.89 GB of egress against a 5.5 GB Free quota and Supabase blocked the API. This
is the 2026-09-14 incident (`docs/known-pitfalls.md`, "Test debris is not inert") arriving
late: 12.16 GB of the total accrued before that day's fix, 0.73 GB in the three days after.

| Source | Per run | Runs/day | GB/day | Note |
|---|---|---|---|---|
| Sweep: recompute reads, 5 IN workspaces × 1.16 MB | 5.8 MB | 3 | 0.017 | `select=*`; the gate reads 7 columns |
| Sweep: recompute read, 1 FR workspace | 4.66 MB | 3 | 0.014 | one French demo workspace, no customer |
| Sweep: corpus upsert echo (`return=representation`) | ~2–5 MB | 3 | ~0.01 | the match upsert already uses `return=minimal` |
| Digest | 0 | 11 | 0 | zero workspaces have notifications enabled; no mail key |
| Stage watch | tiny | 2 | ~0 | |
| **Scheduled total** | | | **≈0.05** | **≈1.5 GB per cycle** |
| Observed post-fix (notice delta) | | | **0.24** | includes a heavy engineering session; **≈7 GB per cycle** |

Two conclusions follow. Scheduled work alone fits Free with room. Interactive and engineering
use does not, and it is unmeasured, which is the actual problem: **nothing in the engine
records how many bytes come back from Supabase, per call or per day.** The downgrade decision
cannot be made from a Supabase email that arrives after the quota is gone.

Of the six workspaces with a member, five are demo fixtures (Meridian Infotech, Sterling
Logistics, PwC India, a second Usha Martin, Groupe Convergence Conseil). One is the customer.
The 2026-09-14 predicate was "has a member"; a seeded demo account satisfies it.

The other Free limit is database size, 500 MB. It was 55 MB after the 2026-09-14 vacuum.
Confirm, and watch it.

## 0b. Execution log — Waves 1 and 2, shipped 2026-09-17

All five code workstreams merged, gated on the merged tree each time, and deployed. Engine
revision `tendercraft-engine-eu-00075-cxq`, web `tendercraft-web-eu-00074-fpc`. Migration
0047 applied to production and confirmed via `information_schema` (PostgREST is still 402,
so "served" is not yet provable). Final gate: 1,662 engine tests, 100% branch coverage on
`app/deterministic/`, ruff clean; web typecheck, lint, 80 tests, build clean.

| Workstream | Landed | What it measured or found |
|---|---|---|
| A. Instrument | logging config, egress ledger, `/health/deep`, `cron/health` accumulator | Raising the root level also switched on httpx's per-request INFO and doubled every ledger line; pinned. `/health/deep` reports the live block as `DB_UNHEALTHY: supabase returned 402` |
| B. Opt-in sweep | migration 0047, fail-open fan-out, admin toggle | Migration replayed 0001→0047 on a throwaway Postgres when Docker was broken; backfill true for all 6 member workspaces confirmed in production |
| F. Scheduler | digest paused; all five jobs capped at 1 retry, 60 s backoff | Baseline showed the digest at 2 retries (three calls per trigger, the observed symptom) and both keepalives at 3 |
| C. Narrow the sweep read | ten pinned columns at the recompute call site | Grep said seven; reading the consumers found ten, three reached only via document enrichment. Estimated ~50% of a serialised row, below the hoped 60–80% because title, document URLs and parsed eligibility must stay |
| D. Write echoes | 26 writes to `return=minimal`, 5 return types changed, `_count_matches` on the ledger, shared `tests/conftest.py` | PostgREST's own default is `return=minimal`; the wrapper's `representation` default was unchosen policy across 83 sites. Found `create_pursuit`/`link_pursuit_tender` passing a `headers=` kwarg `_rest` never accepted: `TypeError` on every call since written, swallowed by the caller |
| E. Interactive paths | `get_sections`, `get_criteria`, `get_valid_library_docs` narrowed per caller; vocabulary endpoint memoised | Measured with the real ledger over a local Postgres. `GET /api/library` had no caller and returned 402 kB per request; `original_md` was 37% of every sections read and unread by any consumer |

E's before/after, real response bytes per request, the production counter over a seeded
local database (both web pages measured by SQL proxy and found already narrow):

| request | before | after | Δ |
|---|---:|---:|---:|
| GET /api/library | 402,899 | 2,539 | −99% |
| POST /profile/keyword-suggestions | 408,366 | 25,606 | −94% |
| GET /capability/vocabulary (warm) | 247,701 | 5,483 | −98% |
| GET /readiness | 63,819 | 36,665 | −43% |
| GET /submission | 407,106 | 250,304 | −39% |
| GET /compliance-matrix | 343,141 | 213,493 | −38% |
| POST /sections/generate | 832,213 | 702,570 | −16% |
| POST /prepare | 687,212 | 605,756 | −12% |
| POST /analyze | 93,826 | 93,820 | wide on purpose |

**Not yet done, and why.** Live verification of every item above against production: blocked
by the 402 until the org is upgraded. The five demo workspaces are still swept: the toggle
exists, the decision is the owner's (§5 step 2). Workstream G, the runbook, is written with
the decision figures left as placeholders to be filled from the ledger around 2026-10-20.

## 1. The bar for downgrading

On or about 2026-10-20, the ledger from workstream A must show, for the trailing 21 days:

- egress ≤ 3.5 GB projected per 30-day cycle (a 35% margin under 5.5 GB), **with the
  engineering-session days included, not excluded** — a number that only holds when nobody
  is working on the product is not a number;
- database size ≤ 300 MB and not growing faster than 2 MB/day;
- no Pro-only feature in use (PITR, daily backups beyond Free, larger compute, custom domain).

If any of those fails, stay on Pro and the ledger says why. Either outcome is a success for
this plan; the failure mode is deciding without the ledger.

## 2. Workstreams

Each is one Opus 5 subagent in its own worktree. **No subagent touches production**: the API
is returning 402 until the upgrade lands, and even after it does, live verification is the
orchestrator's job after merge. Verification is unit tests, 100% branch coverage on
`app/deterministic/`, ruff, typecheck, lint, build. Every subagent reads
`docs/known-pitfalls.md` before writing code; three entries there are about exactly this
table and this job.

### A. Instrument it (first, because everything else is judged by it)

**Files:** `services/engine/app/main.py`, `services/engine/app/db.py::_rest` (a byte counter
only — do not change any query), `services/engine/app/http.py`, a new
`services/engine/app/deterministic/egress.py`, `.env.example`, `docs/deploy.md`.

1. **A logging configuration.** The engine has none, so `logger.info` falls to a root logger
   at WARNING and no application INFO line has ever reached Cloud Logging — seven days of logs
   contain zero, confirmed against a positive control. Configure the root logger from
   `LOG_LEVEL` (default INFO) in `main.py`, JSON-shaped so Cloud Logging parses severity.
   This also makes the Gemini cost line ship, which the cost audit needs.
2. **An egress ledger.** In `_rest`, record `len(resp.content)` per call, tagged with method,
   table, and the route or job that issued it (a contextvar set by the request middleware and
   by each cron handler). Log one line per call at INFO and keep an in-process daily
   accumulator. Bytes received is what Supabase bills; bytes sent is nearly free. Pure
   arithmetic lives in `deterministic/egress.py` at 100% branch coverage.
3. **A health check that reads one row.** `/health` returns 200 while the database returns
   402; add `/health/deep` that does `select 1` through PostgREST and reports the status code
   it got. Point Cloud Run's readiness at the shallow one and the scheduler's `cron/health` at
   the deep one, so a quota block shows up as a failing check instead of an email two days
   later.
4. **A daily egress line the owner can read.** `GET /internal/cron/health` (already
   OIDC-gated) returns the accumulator: bytes today, by table, by route. Document in
   `docs/deploy.md` how to read it and the §1 thresholds.

Acceptance: a unit test proves the ledger attributes bytes to the right table and route; a
test proves the deep health check reports a 402 as unhealthy and a 200 as healthy; ruff,
pytest, coverage gate green.

### B. Sweep only the workspaces someone chose

**Files:** new migration `0047_workspace_discovery_enabled.sql`,
`services/engine/app/discovery/ingest.py` (fan-out), `services/engine/app/cron_routes.py`,
`services/engine/app/db.py` (one read, one write), `apps/web/app/(app)/settings/page.tsx` +
a small client component, the settings route handler.

1. `workspaces.discovery_enabled boolean not null default true`, **backfilled true** for every
   workspace that has a member. That preserves today's behaviour exactly on deploy (ET-7: a
   silent exclusion is the failure this feature exists to prevent). Which workspaces to turn
   OFF is the owner's decision, made through the toggle — never a name pattern, never a
   heuristic about fixtures (the pitfalls file explains why).
2. The sweep's per-workspace fan-out filters on the flag. **A set that filters must fail
   open:** if the read of the flag fails, sweep every member workspace and log it. The
   2026-09-14 entry in the pitfalls file says this in more words.
3. A toggle in Settings, admin-only, with copy that says what turning it off does ("this
   workspace stops receiving new opportunity matches; existing ones stay"). Audited.
4. Migration comment records the measurement that motivated it: five of six member workspaces
   are demo fixtures, and each costs a full corpus read three times a day.

Acceptance: test that a disabled workspace is skipped; test that a read failure sweeps
everything; test that the toggle is admin-gated; migration applies on an empty schema
(`tools/local-db.sh` replay); web typecheck, lint, tests, build.

### C. Read what the gate reads, not the whole row

**Files:** `services/engine/app/db.py::get_opportunities` (the recompute call only — add a
`select` argument, do not change the default), `services/engine/app/discovery/ingest.py`,
`services/engine/app/discovery/relevance.py`, `services/engine/app/deterministic/discovery.py`.

1. Enumerate every column the recompute path reads from an opportunity row: the gate rules,
   `keyword_relevance`, `input_hash`, `_deterministic_row`, `bands_for`, the match row
   builder, the eligibility parse. The measured list is seven columns; verify it, do not
   trust it.
2. Pass that list as the recompute's `select`. Rows average 1.6–1.9 kB and most of it is text
   the gate never touches; the target is a 60–80% cut of the read, **measured by the ledger
   from A once merged**, not asserted.
3. **Pin the select list to its consumers.** The pitfalls file has the entry: a stub that
   returns more than the real query does is not a test. Write a test that fails if any
   consumer reads a key the select does not provide — by exercising the real functions on a
   row built from the select list only.

Acceptance: that test; the full recompute test suite green; no change to what the gate
decides on any existing test fixture.

### D. Stop asking for rows back that nobody reads

**Files:** `services/engine/app/db.py` only.

1. `_rest` defaults to `Prefer: return=representation`. Audit every POST/PATCH/upsert caller.
   Where the return value is discarded, switch that call to `return=minimal`. Where it is
   used, leave it and say so in a one-line comment. Do **not** flip the default: a write that
   silently starts returning `[]` to a caller that read `rows[0]["id"]` is a 500 in
   production, and this is the class of change that ships green and breaks live.
2. The corpus upsert (`upsert_opportunities`) is the known one: it echoes every ingested row,
   ~2 MB per sweep on GeM pages alone. Confirm its caller's use of the return value before
   changing it.

Acceptance: a test per changed call asserting the header; grep proves no caller of a
now-minimal write indexes its result; full suite green.

### E. The interactive paths, which are where the real number is

**Files:** `services/engine/app/db.py` (`get_valid_library_docs`, `get_sections`,
`get_criteria`, `get_profile_context`), their callers in `proposal_routes.py`,
`readiness_routes.py`, `analyze_routes.py`, and the web pages that select `*`.

1. **Measure first.** Using the ledger from A against a local stack (`supabase start` +
   `tools/local-db.sh`, never production), record bytes per request for: upload/ingest,
   `/prepare`, `/analyze`, `/sections/generate`, `/readiness`, `/proposals/:id` page load,
   `/tenders/:id/analysis` page load. Report the table before changing anything.
2. The likely heavy hitters, to be confirmed by that table: `get_valid_library_docs` loads
   every valid document's `text_content` (up to 20,000 characters each) on every section
   regeneration; `get_sections` with `select=*` carries every `body_md`; `get_criteria` with
   `select=*` now carries the `requirement` jsonb on every row for every caller including
   ones that only need ids.
3. Narrow each to its consumer's needs, with the same consumer-pinning test as C. Where a
   caller genuinely needs the text (drafting needs the chunks), keep it and note the cost.
4. `/prepare` runs analysis and then regenerates every criterion response; the Codex cost
   audit already flagged that per-criterion drafting has no input-hash reuse. That is a
   Gemini-cost item, not an egress one, and is **out of scope here** — record it, do not do it.

Acceptance: the before/after table from step 1, in the PR description; consumer-pinning
tests; full suite green.

### F. Scheduler hygiene (small, ops-only)

**Files:** `docs/deploy.md`; `gcloud scheduler` commands, run by the orchestrator after
review, never by a subagent.

1. Pause `tendercraft-alert-digest` until at least one workspace has notifications enabled
   and `RESEND_API_KEY` is on the service. Eleven no-op runs a day is noise, and under a quota
   block each one retries three times a minute.
2. Set a retry policy on all three jobs so a 5xx does not retry more than once per trigger.
3. Document the pause and the condition for un-pausing beside the job table in `deploy.md`.

The subagent writes the doc change and the exact commands; the orchestrator runs them.

### G. The downgrade runbook

**Files:** `docs/deploy.md` (a new section), this plan's §1.

Written last, after A–E are merged and the ledger has a week of data. States: what to read,
the thresholds from §1, how to downgrade in the dashboard, what changes on Free (compute size,
backup retention, PITR absent, project pause after 7 days idle), and what to check the morning
after. One page.

## 3. Order, and why

```
Wave 1  A  B  F        parallel — A touches main.py/http.py/_rest; B touches migration,
                       ingest fan-out, settings UI; F is docs. No file overlap.
merge   A first (the ledger), then B, then F.

Wave 2  C  D  E        parallel in worktrees — all three touch db.py in different functions.
merge   D first (header-only changes, smallest diff), then C, then E, each rebased on the
        previous. The orchestrator resolves db.py conflicts; the subagents do not.

Wave 3  G              after a week of ledger data.
```

Live verification against production happens **after each merge**, by the orchestrator, once
the upgrade has lifted the 402. The ledger from A is what verifies C, D and E: bytes per sweep
before and after, from the same instrument.

## 4. What this plan deliberately does not do

- **Cache more.** The requirement cache exists because verdicts were moving between runs, not
  to save bytes. Caching drafts and sections is a Gemini-cost question the cost audit covers.
- **Guess which workspaces are demos.** The flag is explicit and the owner sets it.
- **Raise limits or change compute.** Egress is not a compute problem.
- **Touch the isolation suite.** It already refuses non-loopback targets; leave it.
- **Optimise the web pages' Supabase reads beyond the three named in E.** Each page reads a
  few kB; the day's total is dominated by the engine.

## 5. Owner actions, in order

1. Upgrade the org to Pro today. Nothing else in this plan is reachable until the 402 lifts.
2. After B merges: open Settings on each of the five demo workspaces and turn discovery off.
3. Around 2026-10-20: read the ledger against §1, decide, and record the decision here.
