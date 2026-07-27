#!/usr/bin/env bash
# Throughput-extension guardrails — tendercraft-evaluate-throughput-PRD.md.
#
# Scope note, so nobody adds a check that already exists elsewhere:
#
#   tools/check-wall.sh          F13 — the two products share no data, DB or credential
#   .github/workflows/ci.yml     no model imports in evaluate/deterministic/, and 100% branch
#                                coverage there. That job greps the DIRECTORY, so presence.py,
#                                rulepack.py and disclosure.py are covered the moment they land.
#                                Do not re-implement it here.
#
# What is left is two structural invariants that only a grep catches, both introduced by this
# extension and neither visible to an existing test:
#
#   T-1  No financial figure outside bid_financials. Bulk intake (F14) multiplies the chances of
#        writing a price into the wrong table, and a new column holding an amount silently
#        bypasses the row-level seal that makes F9 work. tests/test_sealed_bid_gate.py asserts
#        the ENDPOINT behaves; it cannot see a migration that adds `amount` to bid_files.
#
#   T-2  The disclosure filter runs BEFORE generation (F28-AC3). A debrief prompt assembled from
#        unfiltered evaluation data and redacted afterwards is not a gate. This is the only path
#        in either product where evaluation data is packaged for someone outside the authority.
#
# Ships BEFORE the features, same reasoning as the wall and the discovery guardrails: a guardrail
# retrofitted after the code is a guardrail with holes. Skips cleanly until the code exists.
#
# Exits non-zero on any breach. Never make this advisory.

set -euo pipefail
cd "$(dirname "$0")/.."

fail=0
err() { echo "::error::$*"; fail=1; }
ok()  { echo "  ok — $*"; }

ENGINE="services/evaluate-engine"
DET="$ENGINE/evaluate/deterministic"
MIGRATIONS="$ENGINE/migrations"

if [ ! -d "$ENGINE" ]; then
  echo "throughput guardrails: evaluate engine not scaffolded yet — skipping"
  exit 0
fi

# ── T-1: no financial figure outside bid_financials ─────────────────────────
echo "── T-1: financial figures live only in bid_financials ──────────────"

if [ -d "$MIGRATIONS" ]; then
  # Column names that hold money. Checked per CREATE TABLE / ALTER TABLE statement so the
  # bid_financials table itself is exempt and everything else is not.
  money_re='(amount|price|rate|quoted|bid_value|cost)[a-z_]*[[:space:]]+(numeric|decimal|money|bigint|integer|int)'

  # Exempt tables. The rule protects BIDDER-QUOTED money, which is sealed until F9 unlock.
  # It is not about every number with a currency:
  #   bid_financials — the sealed table itself, by definition
  #   drafts         — the AUTHORITY's own pre-publication estimates (estimated value, EMD
  #                    amount). These are printed in the tender document and handed to every
  #                    bidder; there is nothing to seal and no bid to leak. A draft cannot
  #                    contain a bidder's price because it exists before bids do.
  exempt='bid_financials|drafts'

  offenders=$(awk -v IGNORECASE=1 '
    /create[[:space:]]+table|alter[[:space:]]+table/ { tbl=$0 }
    { print FILENAME ":" FNR ":" tbl "\t" $0 }
  ' "$MIGRATIONS"/*.sql 2>/dev/null \
    | grep -iE "$money_re" \
    | grep -viE "$exempt" \
    || true)

  if [ -n "$offenders" ]; then
    echo "$offenders" | cut -f1 | sort -u | sed 's/^/    /'
    err "T-1: a money-valued column outside bid_financials. Financial content is row-level sealed
     until F9 unlock; a new table holding an amount bypasses that seal without failing any test.
     Put it in bid_financials, or rename the column if it genuinely is not money."
  else
    ok "no money-valued columns outside bid_financials"
  fi
else
  echo "  (no migrations yet — skipped)"
fi

# ── T-2: disclosure filters before generation ───────────────────────────────
echo "── T-2: the disclosure filter runs before generation (F28-AC3) ─────"

DEBRIEF_PROMPT="$ENGINE/prompts/debrief.md"
DISCLOSURE="$DET/disclosure.py"

if [ ! -f "$DISCLOSURE" ]; then
  echo "  (deterministic/disclosure.py not built yet — milestone N5 — skipped)"
else
  ok "deterministic/disclosure.py present"

  # Whoever builds the debrief prompt must import the filter. If a module reads the debrief
  # prompt file but never mentions disclosure, it is assembling a prompt from unfiltered data.
  while IFS= read -r consumer; do
    [ -z "$consumer" ] && continue
    if ! grep -qE 'disclosure' "$consumer"; then
      err "T-2: $consumer builds the debrief prompt but never imports the disclosure filter.
     Forbidden fields must never enter the prompt (F28-AC3) — redacting the output afterwards
     is not a gate."
    else
      ok "$(basename "$consumer") imports the disclosure filter"
    fi
  done < <(grep -rlE 'debrief\.md|debrief_prompt' "$ENGINE/evaluate" 2>/dev/null || true)

  # Deny-by-default: an allowlist that fails open is not an allowlist (F28-ERR1).
  if ! grep -qE 'ALLOW|PERMITTED|_allowed|allowlist' "$DISCLOSURE"; then
    err "T-2: disclosure.py has no visible allowlist. The permitted field set must be enumerated
     and everything else denied by default (F28-ERR1)."
  else
    ok "disclosure.py enumerates a permitted field set"
  fi
fi

# ── T-3: the rulepack is data, and it is present ────────────────────────────
echo "── T-3: the regulatory rulepack is data and loadable ───────────────"

RULEPACK=$(grep -oE '^EVAL_RULEPACK_PATH=.*' .env.example 2>/dev/null | head -1 | cut -d= -f2- | tr -d ' ')
if [ -z "$RULEPACK" ]; then
  err "T-3: EVAL_RULEPACK_PATH absent from .env.example (ENV-13)."
elif [ ! -f "$RULEPACK" ]; then
  err "T-3: rulepack not found at $RULEPACK. F23-ERR1 fails fast at startup for exactly this
     reason — a silently rule-less draft workspace is the worst available degradation."
elif command -v python3 >/dev/null 2>&1 && ! python3 -c "import json,sys; json.load(open('$RULEPACK'))" 2>/dev/null; then
  err "T-3: rulepack at $RULEPACK is not valid JSON."
else
  ok "rulepack present and parses: $RULEPACK"
  if command -v python3 >/dev/null 2>&1; then
    unverified=$(python3 -c "
import json
d = json.load(open('$RULEPACK'))
print(sum(1 for r in d.get('rules', []) if not r.get('citation_verified')))" 2>/dev/null || echo 0)
    if [ "${unverified:-0}" -gt 0 ]; then
      echo "  ::warning::$unverified rule(s) still carry citation_verified:false — a"
      echo "  procurement-legal read is required before F23 ships (throughput PRD §12 TODO)."
      echo "  Advisory only: this must not block the build before N4."
    fi
  fi
fi

echo
if [ "$fail" -ne 0 ]; then
  echo "throughput guardrails: BREACHED ✗"
  exit 1
fi
echo "throughput guardrails: intact ✓"
