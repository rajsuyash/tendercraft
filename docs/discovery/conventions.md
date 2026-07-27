# Discovery & Traceability — conventions

Extends `docs/conventions.md`. Everything there still binds: envelope, Pydantic v2 at the boundary, tenant from the JWT, prompts as files, one model client, design tokens only. Below is what Modules F and G add.

## Guardrails (CI-blocking — `tools/check-discovery-guardrails.sh`, `pnpm guardrails`)

The script is the enforcement, this section is the reasoning. It skips cleanly until `services/engine/app/discovery/` exists, so it lands before the first adapter — a guardrail retrofitted after the crawler is a guardrail with holes.

| Rule | Enforced by |
|---|---|
| **G-8** no login, session cookie, stored portal credential, CAPTCHA bypass, or headless-stealth tooling anywhere in `app/discovery/`; no `Authorization` header on an outbound portal fetch | grep over the discovery tree |
| **G-9** no exclusion/suppression/hide/drop function may exist in `app/discovery/`; `app/deterministic/discovery.py` must exist and must not import `pipeline` or a model SDK | structural check + import check |
| **F-AC4 / F-AC6** `tests/test_discovery_merge.py` and `tests/test_discovery_rules.py` must exist | file presence, following the sealed-bid precedent — a green suite that never tested the catastrophic gate is worse than a red one |
| **G-10** adapters may not import `httpx`/`requests`/`urllib`/`aiohttp` directly; `app/discovery/fetch.py` must carry robots, user-agent, rate and byte controls; every adapter file must appear in `app/discovery/registry.py` | import check + content check + registry cross-check |

**The inbound-email webhook authenticates and that is correct** — it verifies a provider signature on data arriving *to us*. It therefore lives in `app/inbound_routes.py`, **not** under `app/discovery/`, so the G-8 check can stay unconditional. Do not "fix" this by adding an exception to the guard: an exception carved for the legitimate case is the exception that eventually covers the illegitimate one.

## Source adapters

- One file per source under `app/discovery/sources/`, named for the source, listed in `registry.py` with `{tier, base_url, cadence, terms_reviewed, reviewer, parser_fingerprint}`. **Unregistered means terms-unreviewed** — the guard fails the build.
- Adapters parse and normalize; they do not fetch (the guarded fetcher does), do not decide (deterministic code does), and do not infer. **A field the source does not publish is `null`.** Never let a model fill a field that a deterministic rule reads — that is G-9 defeated through the back door.
- The NIC eProcurement stack is one adapter family with per-instance config, not 25 adapters. Estimate in adapters, not portals.
- Every adapter stores its raw snapshot with a retrieval timestamp before parsing. A feed item without a reproducible snapshot must not render (F-FR2).
- Parser fingerprint mismatch = source-health incident, not a silent zero (EC-8).

## Fetching

Everything outbound goes through `app/discovery/fetch.py`, which composes the SSRF controls already documented in `docs/known-pitfalls.md` (resolve every hop with `getaddrinfo`, reject private/loopback/link-local/reserved/multicast, follow redirects **manually** with re-validation, `follow_redirects=False`, stream with a byte cap) with robots.txt, an identified user agent carrying a contact URL, a per-host rate cap, and exponential backoff on 429/5xx. Reuse one pooled client (`app/http.py` pattern) — a fresh TCP+TLS handshake per fetch is the latency trap already learned once.

`DISCOVERY_USER_AGENT` and `DISCOVERY_CONTACT_URL` are **required with no default**. An unidentified crawler is a G-10 breach, so a missing value must stop the process, not degrade it.

A portal that asks us to stop: disable the source, notify affected workspaces, offer the T3 path. Never throttle-and-continue, never rotate IPs, never change the UA to look like a browser.

## Rules and the feed

- A rule is a named, user-authored, deterministic predicate over the normalized record. It is stored, versioned, and editable, and **every excluded item names the rule that excluded it**.
- Exclusion is reversible and visible: the Excluded bucket always shows its count on the primary feed. `[data-excluded-count]` is a contractual selector.
- Ranking signals render as three independent values (gate / eligibility / relevance band), never fused into one score. Relevance is a **band with a cited past project** — a decimal implies precision this signal does not have.
- Depth-1 eligibility labels are always visibly provisional and never feed a Bid/No-Bid card. `[data-triage-depth]` is contractual.

## Module G

- Coverage is computed **once**, in one function, and every surface reads it from there. Four counters describing the same object will disagree — this is already a known pitfall on this codebase.
- The unmapped-sentence set is the denominator that makes "we covered everything" a measurement instead of an assertion. A matrix may not be marked complete while it is non-empty.
- XLSX row identity travels in a stable hidden key column. Requirement text, level and source anchor are import-protected: an edited requirement cell is an `MATRIX_IMPORT_CONFLICT`, never a silent TOM rewrite.
- A prior answer enters a draft only on explicit user acceptance, and always carries provenance (source bid, date, outcome). Reuse is a suggestion with a receipt.

## Prompts and evals

New prompt files: `prompts/opportunity_summary.md`, `prompts/eligibility_subset.md`, `prompts/requirement_shred.md`, `prompts/answer_match.md`. Golden sets under `evals/discovery/`. The F-AC1 replay harness lives in `evals/discovery/replay/` and is a **backtest, not an eval** — it replays a partner's real bid history against the feed and reports recall. Treat its cases as fixtures: never edited to make a run pass.
