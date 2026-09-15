-- What the tender DEMANDS, cached against the text it was read from.
--
-- Why a cache is a correctness feature here rather than a performance one. `analysis.decide`
-- is pure arithmetic with no model anywhere near it, and the bid/no-bid card still moved
-- between identical runs — because whether a clause IS a gate depends on a model reading.
-- Measured 2026-09-15 on the live Oil India bid: six extractions of "In case of trader/agent,
-- valid authorization certificate from OEM to be submitted along with the bid" returned
-- `none` at 0.90 four times and `certification_valid` at 1.00 twice. Confidently on both
-- sides, so no confidence threshold separates them, and the card alternated between
-- NEEDS REVIEW and "nothing disqualifies you" with nothing about the tender or the bidder
-- having changed.
--
-- A compliance product may not answer the same question two ways. Reading once and storing
-- the answer makes the verdict reproducible and auditable: `requirement` is the exact input
-- the stored verdict was computed from.
--
-- `requirement_hash` covers BOTH the criterion text and the prompt file's own digest, on the
-- `discovery/relevance.py::input_hash` rule — change any of it and it is re-read, change
-- nothing and it is not. Without the prompt half, improving the prompt would leave every
-- existing tender frozen on the old reading forever, which is the cache silently becoming
-- the product.
--
-- Deliberately NOT backfilled, like 0040-0044: NULL means "never read", which is true of
-- every existing row, and is not the same as any particular reading.
alter table public.criteria
  add column if not exists requirement jsonb,
  add column if not exists requirement_hash text;

comment on column public.criteria.requirement is
  'The extracted requirement the stored verdict was computed from. NULL = never extracted.';
comment on column public.criteria.requirement_hash is
  'sha256 over the criterion text AND the analyzer prompt digest. A mismatch re-reads; see '
  'migration 0045 for why re-reading on every run was a correctness defect.';
