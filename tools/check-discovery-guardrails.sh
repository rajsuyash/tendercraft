#!/usr/bin/env bash
# G-8 / G-9 / G-10 — the discovery guardrails, enforced.
#
# Module F reaches out to hundreds of third-party portals on a schedule. It is the only part
# of TenderCraft that touches systems we do not own, and the only part where the failure mode
# is legal rather than functional. Three rules from tendercraft-discovery-PRD.md §5 carry the
# whole posture:
#
#   G-8   No authenticated acquisition. Adapters never log in, never replay a session cookie,
#         never store a portal credential, never solve or bypass a bot check. A source that
#         needs auth is served by the customer forwarding their own alert email (T3), or not
#         at all.
#   G-9   No model-driven exclusion. Only a named, user-authored deterministic rule may move
#         an item out of the primary feed. A model may rank and summarise; it may never decide
#         what a human never sees. A missed tender produces no error message anywhere — it is
#         the one failure in this product with no natural feedback signal (ET-7).
#   G-10  Crawl discipline. Every outbound fetch goes through the guarded fetcher: robots.txt,
#         identified user agent, per-host rate cap, backoff, byte cap, and the SSRF controls in
#         docs/known-pitfalls.md. Discovery multiplies the number of untrusted URLs this system
#         touches by orders of magnitude, so a bare httpx call in an adapter is not a style nit.
#
# This script is those rules made testable. It runs in CI on every push and it ships BEFORE
# the first adapter, because a guardrail retrofitted after the crawler is a guardrail with
# holes — the same reasoning that put tools/check-wall.sh in M0.
#
# Exits non-zero on any breach. Never make this advisory.

set -euo pipefail
cd "$(dirname "$0")/.."

fail=0
err() { echo "::error::$*"; fail=1; }

ENGINE="services/engine"
DISCOVERY="$ENGINE/app/discovery"
SOURCES="$DISCOVERY/sources"
RULES="$ENGINE/app/deterministic/discovery.py"
REGISTRY="$DISCOVERY/registry.py"
FETCH="$DISCOVERY/fetch.py"

# Nothing to check until the discovery surface exists. Deliberately NOT an error: this script
# lands in PH4a before any adapter does, and a green check on an absent module is honest.
if [ ! -d "$DISCOVERY" ]; then
  echo "discovery: surface not present yet — nothing to check (expected before PH4b)"
  exit 0
fi

echo "── G-8: no authenticated acquisition ───────────────────────────────"

# The realistic breach is not malice. It is a well-meaning engineer discovering that one state
# portal needs a session to paginate, and adding "just a cookie" to unblock a sprint. That one
# cookie converts a public-page reader into a credentialed scraper and puts base PRD §9 —
# "no credentialed scraping in violation of portal terms" — into the past tense.
if grep -rniE '(set-cookie|cookies?[[:space:]]*=|session[[:space:]]*=|\blogin\b|signin|\bpassword\b|captcha|recaptcha|2captcha|anticaptcha|selenium|undetected_chrome|stealth)' \
    "$DISCOVERY" --include='*.py' 2>/dev/null; then
  err "discovery code references authentication, session state, or bot-check evasion (G-8)"
fi

# An Authorization header on an outbound portal fetch is the same breach wearing a tie. The
# inbound email webhook DOES authenticate — but it lives outside app/discovery (see the
# conventions doc), so this check stays unconditional here rather than growing an exception
# that would eventually be used for the thing it was meant to forbid.
if grep -rniE '"?[Aa]uthorization"?[[:space:]]*:|Bearer[[:space:]]' \
    "$DISCOVERY" --include='*.py' 2>/dev/null; then
  err "discovery code sets an Authorization header on an outbound fetch (G-8)"
fi

echo "── G-9: no model-driven exclusion ──────────────────────────────────"

# Ranking is a model's job. Deciding what a human never sees is not. Enforced structurally:
# the exclusion path lives in app/deterministic/ (already model-import-free, enforced by the
# engine CI job) and the AI-touching app/discovery/ tree may not contain an exclusion path
# at all.
if grep -rnE '\bdef[[:space:]]+[a-z_]*(exclude|suppress|hide|filter_out|drop)[a-z_]*\(' \
    "$DISCOVERY" --include='*.py' 2>/dev/null; then
  err "an exclusion/suppression function lives in app/discovery — it belongs in app/deterministic/discovery.py (G-9)"
fi

if [ -f "$RULES" ]; then
  # Belt and braces over the engine job's blanket deterministic check: name the AC so a
  # failure here reads as "the feed can now hide things a model chose to hide" rather than
  # as a generic lint error.
  if grep -rnE '^[[:space:]]*(from|import)[[:space:]]+(pipeline|app\.discovery|google|anthropic|openai)' \
      "$RULES" 2>/dev/null; then
    err "app/deterministic/discovery.py imports model or discovery-pipeline code (G-9 / F-AC6)"
  fi
else
  err "app/discovery exists but app/deterministic/discovery.py does not — the rules engine must be deterministic before the feed can exclude anything (G-9)"
fi

# F-AC4 is a zero-tolerance gate: two distinct tenders shown as one deletes a tender from the
# user's world with no error message. Following the sealed-bid precedent in the evaluate CI
# job — require the test to EXIST, because a green suite that never tested the catastrophic
# gate is worse than a red one.
if [ ! -f "$ENGINE/tests/test_discovery_merge.py" ]; then
  err "tests/test_discovery_merge.py missing — F-AC4 (zero wrong merges) is unproven"
fi
if [ ! -f "$ENGINE/tests/test_discovery_rules.py" ]; then
  err "tests/test_discovery_rules.py missing — F-AC6 (nothing excluded except by a named user rule) is unproven"
fi

echo "── G-10: crawl discipline ──────────────────────────────────────────"

# Every adapter fetches through the guarded fetcher. A bare httpx/requests/urllib call skips
# robots, the rate cap, the byte cap AND the SSRF hop-resolution controls at once — and it is
# the single easiest line for an adapter author to write by accident.
if [ -d "$SOURCES" ]; then
  if grep -rnE '^[[:space:]]*(import|from)[[:space:]]+(httpx|requests|urllib|aiohttp|http\.client)' \
      "$SOURCES" --include='*.py' 2>/dev/null; then
    err "a source adapter imports an HTTP client directly — fetch via app/discovery/fetch.py (G-10)"
  fi
fi

if [ -f "$FETCH" ]; then
  for control in robots user_agent rate byte; do
    grep -qi "$control" "$FETCH" || err "app/discovery/fetch.py has no '$control' control — G-10 requires robots.txt, an identified user agent, a per-host rate cap and a byte cap"
  done
else
  [ -d "$SOURCES" ] && err "source adapters exist but app/discovery/fetch.py does not — there is no guarded fetch path (G-10)"
fi

# An adapter absent from the registry is an adapter whose terms were never reviewed. The
# registry is where a source's tier and terms-review date live; if a file can crawl without
# appearing there, the review step is optional in practice.
if [ -d "$SOURCES" ]; then
  if [ ! -f "$REGISTRY" ]; then
    err "source adapters exist but app/discovery/registry.py does not — every source needs a recorded tier and terms-review date (G-10)"
  else
    for f in "$SOURCES"/*.py; do
      [ -e "$f" ] || continue
      name="$(basename "$f" .py)"
      case "$name" in __init__|base) continue ;; esac
      grep -q "$name" "$REGISTRY" || err "source adapter '$name' is not listed in app/discovery/registry.py — unregistered means terms-unreviewed (G-10)"
    done
  fi
fi

if [ "$fail" -eq 0 ]; then
  echo
  echo "discovery guardrails: intact ✓"
else
  echo
  echo "discovery guardrails: BREACHED — see errors above. These are not lint failures; they"
  echo "      are the difference between reading public pages and scraping a portal we were"
  echo "      told not to scrape."
fi
exit "$fail"
