# UX: Truth First, Then First-Run — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the interface stating things that are not true, then make a workspace that already has data land on the work instead of on six empty boxes.

**Architecture:** No new screens, no new tables, no route changes. Phase 1 corrects claims the UI makes that the data contradicts. Phase 2 makes `/proposals` list proposals. Phase 3 puts the populated things in front of the customer. Nav restructure is deliberately last and gated on a human decision, because it is the only part that is taste rather than correctness.

**Tech Stack:** Next.js 15 App Router · TypeScript · Vitest · design tokens only

---

## The finding that orders this plan

`apps/web/app/(app)/dashboard/page.tsx:70-71`:

```js
{ label: t("Active tenders"),        value: activeCount ?? 0 },   // measured
{ label: t("Awaiting verification"), value: 0 },                  // hardcoded
{ label: t("Drafts in review"),      value: 0 },                  // hardcoded
```

Two of four KPI tiles are literal zeros rendered identically to the measured one. Verified against production on 2026-09-09: the Usha Martin workspace has **861 unconfirmed criteria**, displayed as `0`.

This is not a polish item. The product's entire position is that it does not assert what it has not checked — `NOT ASSESSED` rather than a guess, `needs_review` rather than a coerced verdict, "Published means recorded here by you". A front-page tile inventing a measurement contradicts the thing being sold, and it does it first.

Everything else in this plan is smaller than that.

---

## Verified before planning

| Claim | Status |
|---|---|
| Dashboard KPIs 2 and 3 are hardcoded `0` | **Confirmed** — `dashboard/page.tsx:70-71`; real value 861 |
| `ProposalsPage` lists tenders, not proposals | **Confirmed** — queries `tenders`, limit 50; own comment says "every tender is a potential proposal" |
| Verdict tokens used for workflow state | **Confirmed** — `STATUS_STYLE` maps approved/exported to `bg-success-bg text-success` |
| `TendersPage` swallows errors into an empty list | **NOT confirmed** — uses `engineFetch`; no `?? []` found. Do not act on this without re-checking |
| Learning's "Coverage of your latest tender" mislabels `reuse_coverage()` | Reported by review, **not independently verified** — check `deterministic/learning.py` before renaming |

---

## Constraints

1. **Design tokens only.** No new colour or type values (`docs/conventions.md`).
2. **Verdict semantics are reserved.** `success`/`danger`/`warning` mean Pass/Fail/Needs-review and nothing else. Workflow status and trend direction use neutral/primary.
3. **Contractual `data-*` selectors are design ACs.** Never remove one; `docs/DESIGN_SPEC.md` §E.
4. **Every screen keeps default + loading + empty + error.**
5. **Honest refusals survive.** `NOT ASSESSED`, "Published means recorded here by you", unknown-not-flat trends, expired-evidence exclusion. A screen that implies a check ran when it did not is worse than one that says it cannot answer.
6. **Counts are head-only queries**, matching the existing `activeCount` pattern — a KPI must never depend on how many rows happened to render.

---

## Phase 1 — Stop saying untrue things *(ship alone)*

### Task 1: The Dashboard reports what it measured
**Files:** `apps/web/app/(app)/dashboard/page.tsx` · `apps/web/app/(app)/dashboard/kpis.test.ts`

Replace both hardcoded zeros with head-only counts, alongside the existing `activeCount`:
- **Awaiting verification** — `criteria` where `confirmed = false`
- **Drafts in review** — `proposals` where `status = 'review'`

A failed count renders `—`, never `0`. Zero and unknown are different claims and this tile has already conflated them once.

### Task 2: Workflow status stops borrowing verdict colours
**Files:** `apps/web/app/(app)/proposals/page.tsx` · `apps/web/components/LearningMeter.tsx`

`STATUS_STYLE` approved/exported → neutral/primary tokens. `LearningMeter` trend direction likewise. A green chip in this product means Pass; using it for "exported" teaches the opposite of what the compliance screens rely on.

### Task 3: "No deadline" stops overstating what is known
**Files:** `apps/web/app/(app)/tenders/page.tsx` · `apps/web/app/(app)/dashboard/page.tsx` (`deadlineLabel`) · i18n

`"No deadline"` → `"Deadline not recorded"`. The portal may publish one we did not read; the current label asserts the tender has none. French string added — a bare string leaks English into FR chrome.

---

## Phase 2 — `/proposals` lists proposals

**Files:** `apps/web/app/(app)/proposals/page.tsx` + test

Query `proposals`, join tender title and number, paginate. Today membership comes from the latest 50 **tenders**, so three real proposals render as 50 rows of which 47 say "lock TOM first" — and an older proposal can disappear behind the tender limit entirely. Empty state becomes "No proposals yet" with a link to `/tenders`, not a test of whether tenders exist. Creation stays in the tender workflow; `proposals/[id]` already keys on tender id, so no route or schema change.

---

## Phase 3 — Land on the work

**Files:** `apps/web/app/(app)/dashboard/page.tsx` · `apps/web/app/(app)/library/page.tsx` · empty-state actions

- Dashboard leads with **"N tenders imported. Choose one to assess"** plus inventory counts, each row linking to its existing `/tenders/:id/readiness`. `ReadinessHub` and `readiness_routes.py` already do the whole job; the landing page simply never points at it.
- `library/page.tsx` renders the populated document table **above** the two empty optional panels.
- Empty states that are a missing *input* get the action inside them (Add manufacturing envelope, Record catalogue item, Add a past bid). Empty states that are a *future outcome* say when they become available and give no instruction to manufacture the metric.
- Cut the editorial. "Cannot assess diameter fit: no manufacturing range recorded" is useful. "which is the truth, but it is not useful" is the designer talking to themselves.

---

## Phase 4 — Navigation *(needs a human decision, not shipped by this plan)*

Proposed: primary **Tenders · Opportunities · Proposals**; inputs **Documents · Vendor profile · Manufacturing capability**; footer **Settings · Help**. Rename Knowledge Base → Documents, Learning → Answer reuse. Hide Proposals until one exists; keep input editors always visible, because hiding an editor prevents supplying the input it exists to collect.

Not shipped here. It is the only part that is taste rather than correctness, it moves every URL a user may have bookmarked, and `docs/DESIGN_SPEC.md` §D stops at S13 so the later screens have no ratified design ACs to check against.

---

## Not doing

- **Acting on the `TendersPage` error-swallowing claim** until it is verified. It did not reproduce.
- **Renaming Learning's coverage metric** until `reuse_coverage()` is read. The rename is probably right; asserting it without reading the function is the mistake this plan exists to correct.
- **A wizard or a workspace checklist.** A wizard forces one order onto tenders that need different ones; a checklist implies filling every input produces compliance readiness. Inline prompts already exist in `ReadinessHub` and `ScheduleFit` — extend those.
- **Removing any honest refusal.**
