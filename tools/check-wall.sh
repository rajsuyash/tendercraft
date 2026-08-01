#!/usr/bin/env bash
# F13 — the conflict-of-interest wall, enforced.
#
# TenderCraft helps bidders win tenders. TenderCraft Evaluate scores those tenders for the
# buyer. A company doing both cannot share a database, a credential, or a line of data-access
# code between them and still be credible to a public authority. "We have RLS policies" does
# not survive a procurement audit; "different database, no network path" does.
#
# This script is that claim, made testable. It runs in CI on every push and it is the exit
# criterion of M0 — before any evaluate feature exists, because a wall retrofitted after the
# data model is a wall with holes.
#
# Exits non-zero on any breach. Never make this advisory.

set -euo pipefail
cd "$(dirname "$0")/.."

fail=0
err() { echo "::error::$*"; fail=1; }

BIDDER_APP="apps/web"
BIDDER_ENGINE="services/engine"
EVAL_APP="apps/evaluate"
EVAL_ENGINE="services/evaluate-engine"

# Nothing to check until the evaluate surfaces exist. Deliberately NOT an error: this script
# ships in M0 before the app does, and a green wall check on an empty product is honest.
if [ ! -d "$EVAL_APP" ] && [ ! -d "$EVAL_ENGINE" ]; then
  echo "wall: evaluate surfaces not present yet — nothing to check (expected before M0 completes)"
  exit 0
fi

echo "── F13-AC1: no imports across the wall ─────────────────────────────"

# Evaluate must never import bidder code. The realistic breach is not malice, it is a
# well-meaning refactor extracting a "shared" db.py — which is exactly how the wall dies.
#
# The evaluate engine's own package is `evaluate/`, NOT `app/`, precisely so this check can
# be unambiguous: inside the evaluate engine, `from app…` or `from pipeline…` can only mean
# the bidder's packages. The first version of this script excluded matches whose PATH began
# with the evaluate app dir — which, since evaluate's own code lived there, excluded every
# file it was supposed to inspect and reported "wall: intact" on a planted breach. A guard
# that cannot fail is worse than no guard, because it is believed.
if [ -d "$EVAL_ENGINE" ]; then
  if grep -rnE '^[[:space:]]*(from|import)[[:space:]]+(app|pipeline)[.[:space:]]' "$EVAL_ENGINE" \
      --include='*.py' 2>/dev/null; then
    err "evaluate engine imports the bidder engine's packages (F13-AC1)"
  fi
  if [ -d "$EVAL_ENGINE/app" ]; then
    err "evaluate engine must name its package 'evaluate/', not 'app/' — see F13-AC1 above"
  fi
fi

if [ -d "$EVAL_APP" ]; then
  if grep -rnE "from ['\"](\.\./)*(apps/web|@tendercraft/web)" "$EVAL_APP" \
      --include='*.ts' --include='*.tsx' 2>/dev/null; then
    err "evaluate app imports from the bidder app (F13-AC1)"
  fi
fi

# ...and the reverse. A bidder-side import of evaluate code is the same breach wearing a
# different hat: it would give bidder code a path to evaluation data.
for d in "$BIDDER_APP" "$BIDDER_ENGINE"; do
  [ -d "$d" ] || continue
  if grep -rnE "evaluate[_-]?engine|apps/evaluate|@tendercraft/evaluate" "$d" \
      --include='*.py' --include='*.ts' --include='*.tsx' 2>/dev/null; then
    err "bidder surface ($d) references the evaluate product (F13-AC1)"
  fi
done

echo "── F13-AC2: the two products do not share a database ───────────────"

# The failure mode is convergent config — someone points staging at the bidder project
# "just to test". Compare the configured hosts and fail the build if they are equal.
bidder_url="${NEXT_PUBLIC_SUPABASE_URL:-}"
eval_url="${NEXT_PUBLIC_EVAL_SUPABASE_URL:-}"

if [ -n "$bidder_url" ] && [ -n "$eval_url" ]; then
  if [ "$bidder_url" = "$eval_url" ]; then
    err "NEXT_PUBLIC_EVAL_SUPABASE_URL equals the bidder URL — the wall is down (F13-AC2)"
  else
    echo "wall: distinct Supabase hosts confirmed"
  fi
else
  # Not fatal in a fork/PR without secrets, but never silently "passing".
  echo "wall: one or both Supabase URLs absent from the environment — host comparison skipped"
fi

# ── credential comparisons ────────────────────────────────────────────────────
#
# These two checks used to be written as `if [ -n "$A" ] && [ -n "$B" ]; then compare; fi`,
# which reads as "compare when we can". In CI neither variable is ever set, so the whole block
# was skipped and the wall printed "intact" having verified NOTHING about credentials. That is
# how the shared model credential survived: the comment above the old F13-AC3 block said it
# "stays visible in every CI run", and it had in fact never run once.
#
# So: compare wherever the credentials can be reached — the environment first, then Secret
# Manager if gcloud is authenticated (which covers every deploy) — and when neither is
# available, SAY SO. An unverifiable check must announce itself; silence reads as a pass.

# Hash rather than compare raw, so nothing sensitive can ever reach a log.
fingerprint() { printf '%s' "$1" | shasum -a 256 | cut -c1-16; }

# Best-effort read of a Secret Manager version. Empty on any failure, including no gcloud,
# no auth and no such secret — all of which mean "cannot verify here", never "verified".
secret_fp() {
  command -v gcloud >/dev/null 2>&1 || return 0
  local v
  v=$(gcloud secrets versions access latest --secret="$1" \
        --project="${WALL_GCP_PROJECT:-resonant-tube-280016}" 2>/dev/null) || return 0
  [ -n "$v" ] && fingerprint "$v"
}

# $1 label · $2 AC id · $3,$4 env values · $5,$6 secret names · $7 waiver env var name
compare_credential() {
  local label="$1" ac="$2" a="$3" b="$4" sa="$5" sb="$6" waiver="$7" fa fb src
  if [ -n "$a" ] && [ -n "$b" ]; then
    fa=$(fingerprint "$a"); fb=$(fingerprint "$b"); src="environment"
  else
    fa=$(secret_fp "$sa"); fb=$(secret_fp "$sb"); src="Secret Manager"
  fi
  if [ -z "$fa" ] || [ -z "$fb" ]; then
    # Loud, and deliberately not an error: a contributor without deploy credentials must still
    # be able to run the wall. What must never happen is this passing silently.
    echo "wall: $ac NOT VERIFIED HERE — $label not in scope (no env value, no Secret Manager access)."
    echo "wall:   run with the credentials present, or from a machine with gcloud auth, to check it."
    return 0
  fi
  if [ "$fa" = "$fb" ]; then
    if [ "${!waiver:-}" = "1" ]; then
      echo "wall: WAIVED — the two products share their $label ($ac). Waiver: $waiver=1"
    else
      err "the two products share their $label ($ac), fingerprint $fa (via $src). Set $waiver=1 to waive."
    fi
  else
    echo "wall: $ac ok — separate $label ($fa / $fb via $src)"
  fi
}

# A shared service key is a shared database by another name.
compare_credential "database service key" "F13-AC2" \
  "${SUPABASE_SERVICE_JWT:-}" "${EVAL_SUPABASE_SERVICE_JWT:-}" \
  "tendercraft-supabase-service-key" "tendercraft-eval-service-jwt" \
  "EVAL_WALL_ALLOW_SHARED_SERVICE_KEY"

# F13-AC3 wants a separate MODEL credential so usage and telemetry never commingle, and so
# either product's key can be revoked without taking the other down.
compare_credential "model credential" "F13-AC3" \
  "${GEMINI_API_KEY:-}" "${EVAL_MODEL_API_KEY:-}" \
  "tendercraft-gemini-api-key" "tendercraft-eval-model-key" \
  "EVAL_WALL_ALLOW_SHARED_KEY"

echo "── F13-AC3: no bidder data reaches the evaluation model ────────────"

# Prompts and eval fixtures are the quiet path: a golden case copied from bidder-side data
# would prime the scoring model on a bidder's content.
for p in "$EVAL_ENGINE/prompts" "$EVAL_ENGINE/evals"; do
  [ -d "$p" ] || continue
  if grep -rniE "meridian|vendor_profiles|library_documents|proposal_sections" "$p" 2>/dev/null; then
    err "evaluate prompts/evals reference bidder-side entities or fixtures (F13-AC3)"
  fi
done

if [ "$fail" -eq 0 ]; then
  echo
  echo "wall: intact ✓"
else
  echo
  echo "wall: BREACHED — see errors above. This is not a lint failure; it is the product's"
  echo "      licence to operate with a government buyer."
fi
exit "$fail"
