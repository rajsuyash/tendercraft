# Golden fixtures — deliberately NOT committed

The `*.pdf` files this directory expects are real GeM bid documents. They are gitignored, and
that is a compliance decision rather than a repo-hygiene one: **this repository is public**, and
GeM's copyright policy states that *"Contents of this website may not be reproduced partially or
fully without due permission in writing in advance from the GeM SPV"*
(`docs/discovery/source-gem.md` §8). Committing them here would publish GeM content to the
world, which is the one thing that clause forbids — and it would do it from the very module
written to respect it.

So the fixtures live on developer machines and in CI caches, never in git history. Tests that
need them skip with a reason; the tests covering the dangerous logic (`parse_amount`'s unit
handling, section bounding, the tri-state booleans, the non-PDF guard) need no fixture and always
run.

## Regenerate them

From `services/gem-connector`:

```bash
uv run python -m tests.fetch_fixtures
```

That performs one listing sweep, picks a services / high-value / BOQ bid, and writes the three
files below. It obeys the same rate cap as production because it goes through `GuardedFetcher`.

| File | Why this one |
|---|---|
| `gem-services-bid-*.pdf` | turnover + estimated value present, EMD/ePBG as `Required: No` |
| `gem-high-*.pdf` | EMD as an **amount**, ePBG as a **percentage**, past-experience years, Crore-scale turnover |
| `gem-boq-*.pdf` | turnover and experience genuinely **absent** — proves `None` means absent, not a parser miss |

The ids change as bids close, so the exact filenames will differ from the ones the tests name.
The tests resolve fixtures by glob prefix for that reason.
