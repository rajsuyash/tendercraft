# Discovery & Traceability — test strategy

Extends `docs/test-strategy.md`. The rule is unchanged: **an AC is verified at its tagged layer only.** Passing unit tests never satisfy a browser AC; a green eval never satisfies a deterministic gate.

| Layer | Owner | Covers here |
|---|---|---|
| unit | `uv run pytest` · `pnpm test` | **all deterministic discovery logic** — merge (F-AC4), rule evaluation and feed partition (F-AC6), matrix generation, the unmapped denominator (G-AC1), coverage (G-AC8), import-conflict detection (G-AC5), Depth-1 comparators (C-AC8). 100% branch coverage, same as every other gate — these are in `app/deterministic/` and inherit the existing `--cov-fail-under=100` job. |
| integration | `uv run pytest` + `/verify-api` | endpoint contracts and envelope, cursor pagination on the feed, inbound-webhook signature rejection (`INBOUND_UNVERIFIED`), triage cap (`TRIAGE_CAP_REACHED`), **workspace-isolation tests on opportunities, rules and matrix rows** (ET-6, CI-blocking) |
| guardrails | `pnpm guardrails` (`tools/check-discovery-guardrails.sh`) | G-8, G-9, G-10, and the existence of the two catastrophic-gate test files. CI-blocking on every push, skip-clean before the surface exists. **Verified against nine planted breaches before being trusted** — re-verify the same way after any edit to the script. |
| browser-verify | `/verify-discovery` | S14–S18 flows, plus two data-level assertions the DOM cannot make (below) |
| design-review | `/design-review S14..S18` | the design ACs in the product PRD §11 |
| evals | `/evals` (golden sets in `evals/discovery/`) | eligibility-subset extraction recall, requirement-sentence recall (G-AC2), relevance banding sanity, answer-match ranking, fault injection |
| **backtest** | `evals/discovery/replay/` | **F-AC1 — the primary gate for the whole module.** Replays a design partner's real 12-month bid history against the feed and reports recall. Not an eval: no thresholds are tuned here, and no case is ever edited. |
| manual | human sign-off | terms-of-service review per source before its registry entry is written; portal-contact response handling |

## Two assertions the DOM cannot make

`/verify-discovery` must inspect **network responses**, not only rendered output — both of these are about data that must not exist or must not be reachable:

1. **F-AC6 — nothing excluded except by a named user rule.** Every item in the Excluded bucket must carry a `rule_id` in the API response. An item excluded with a null or model-derived reason is a G-9 breach that a DOM check cannot see, because an excluded item renders identically either way.
2. **C-AC10 — Depth-1 never feeds a recommendation.** No Bid/No-Bid field may appear in any response for an opportunity whose eligibility depth is 1. A DOM-only check passes when the card is merely hidden.

## Coverage targets

80% line on the new web routes and engine modules; **100% branch on `app/deterministic/discovery.py` and `matrix.py`** — they inherit the existing gate job, which is the point of putting them there. Adapters are covered by fixture-replay tests against FIX-6 snapshots, never by live network calls in CI.

## What must be true before M9 exits

FIX-9 (the partner backtest corpus) exists and F-AC1 ≥ 95% on it. Without that corpus the module's central claim — "you will stop missing tenders" — has no test at any layer, and M9 has no exit gate. Recruit for it during M6.
