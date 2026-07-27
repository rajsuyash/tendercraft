# Discovery & Traceability — known pitfalls

Read before writing code; append when you hit a new one. `docs/known-pitfalls.md` applies in full — everything there about Supabase, RLS, cursors, latency, containers and the AI pipeline is live on this surface too. Below is what is specific to Modules F and G.

Format: **symptom → cause → fix.**

## Seeded from the base repo's scars (these will recur here)

- Adapters fetching with a bare `httpx.get()` → new TCP+TLS handshake per call, and worse, the SSRF hop-resolution controls skipped entirely → one pooled, guarded fetcher; the guardrail script fails the build on a direct HTTP import in `sources/`.
- `follow_redirects=True` on a portal fetch → re-enables the redirect-to-metadata bypass → keep it `False`, re-validate every hop. Discovery multiplies untrusted URLs by orders of magnitude; this is the surface where a dormant SSRF hole gets found.
- A cursor on a non-unique column → a bulk source poll gives every row the same insert timestamp, so `created_at < cursor` skips the rest of the page → cursor on the full `(created_at, id)` tuple, emitted with a `Z` suffix.
- New tables without `tenant_id` + RLS + an isolation test → cross-workspace reads. The feed, rules and matrix rows are all workspace-scoped. A consultant seeing client A's shortlist inside client B is ET-6, Sev-1.
- Four counters describing the same object will disagree → one `coverage()` function feeding matrix, export gate and dashboard (G-FR7).
- A UI array mirroring a server enum will drift → rule operators and matrix statuses are closed sets; if the UI lists them, say so in a comment at both ends.

## Anticipated, specific to this surface

- **A broken adapter renders as an empty feed, not as an error.** The portal changed its markup, the parser returns zero rows, and the feed simply looks quiet. Nobody notices for six weeks, and the product's single most valuable promise is silently false the whole time → item-count deviation vs. the trailing median is an **incident** (EC-8); the feed carries a per-source coverage banner naming any degraded source and its last successful fetch. **A zero from a source that has never returned zero is a bug until proven otherwise.**
- **Dedup tuned on precision quietly deletes tenders.** Fuzzy merging looks great in a demo — fewer duplicates, tidier feed — and every wrong merge removes a real tender with no error message anywhere. → merge on exact normalized `portal_ref_no` only; near-matches group as a suggestion. FIX-7 carries a deliberate near-miss pair (same authority, same closing date, different tender); if it ever merges, the gate is broken.
- **A model filling a `null` field defeats G-9 through the back door.** An adapter that asks a model to guess `estimated_value` gives model output the power to move an item past a value-band rule — the exclusion path becomes model-driven without a single line that looks like exclusion → `null` stays `null`; deterministic rules must treat `null` as "does not match an exclusion", never as "excluded".
- **A relevance score rendered as a decimal will be believed.** 0.62 implies a calibration this signal does not have, and users will build rules on it → bands only, with the cited past project that produced the band.
- **Depth-1 eligibility labels will be treated as verdicts.** They are provisional by construction, computed from a listing record and a partial NIT → label the depth in the DOM (`[data-triage-depth]`), never let Depth-1 feed a Bid/No-Bid card, and rank `Likely ineligible` items down rather than hiding them (C-FR9).
- **The daily digest becomes the new thing nobody reads.** A feed at 300 items/day is exactly the Excel tracker it replaced → in-scope volume is a gate (F-AC2, ≤ 25/day), and rule tuning is part of onboarding, not a settings page the user finds later.
- **Triage cost scales with the feed, not with bids.** Running an extractor over every NIT for every workspace is the cost blowup this module can produce → the escalation ladder in product PRD §4.1 is deterministic and capped; log cost per workspace-day and render it in settings before the bill teaches you.
- **An aggregator digest email parsed as one tender loses nine.** Forwarded digests contain many tenders in one message → parse into individual opportunities where structure permits; where it does not, flag for manual split and **never drop the email** (EC-10).
- **Requirement sentences hide in table cells, footnotes and annexure references.** A shredder tuned on prose silently under-counts, and the unmapped denominator — the whole point of G-FR2 — reports a comfortable zero → FIX-10 plants one of each; an unresolvable structure is listed for human resolution, never dropped.
- **A re-imported spreadsheet rewriting the locked TOM.** Someone edits a requirement cell in Excel to "clarify" it, re-imports, and the locked tender model — the artifact everything downstream trusts — changes without passing the lock gate → requirement text, level and anchor are import-protected; an edit there is a conflict, not a merge.
- **An answer reused from a losing bid, presented without that context.** Reuse without outcome linkage propagates whatever lost → suggestions carry the source bid, its date, and its outcome where known.
- **A template-marker document reaching the answer library.** Already learned on the bidder side: an unfilled template ("[Insert Designation]") cited into a proposal looks *sourced*. The answer library is a second doorway into the same failure → run the existing template-marker detection on anything entering it.
