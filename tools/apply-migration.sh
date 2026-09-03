#!/usr/bin/env bash
# Apply one migration to the HOSTED database, via the Supabase Management API.
#
# `tools/local-db.sh` is the throwaway CI database and drops `schema public`; this is its
# opposite number and the only scripted path to production. Everything awkward in here is a
# pitfall that cost a round trip the first time (docs/known-pitfalls.md, "Talking to the hosted
# database from a script"):
#
#   * `SUPABASE_DB_URL` is empty in `.env`, so `psql` silently targets a local socket and fails
#     with "is the server running locally?" — which reads as a broken local stack rather than a
#     missing variable. The Management API is the route that works, and it runs DDL.
#   * That API sits behind Cloudflare, which 403s a default script user agent with `error code:
#     1010` on every request including `select 1`. Hence the UA header.
#   * Its error BODY carries the Postgres message; the status line carries nothing. A bare
#     "HTTP 400" costs a round trip that `column ... is of type market[]` would have answered.
#     So failures print the body.
#
# Usage:  ./tools/apply-migration.sh services/engine/migrations/0037_award_sources.sql
#
# Reads SUPABASE_ACCESS_TOKEN and NEXT_PUBLIC_SUPABASE_URL from .env. Prints what it is about
# to do and against which project ref, because the wall (F13) means there are TWO Supabase
# projects and applying a bidder migration to the evaluate one would be a bad afternoon.

set -euo pipefail
cd "$(dirname "$0")/.."

FILE="${1:-}"
[ -n "$FILE" ] || { echo "usage: $0 <path/to/migration.sql>" >&2; exit 2; }
[ -f "$FILE" ] || { echo "no such migration: $FILE" >&2; exit 2; }

set -a; . ./.env; set +a

: "${SUPABASE_ACCESS_TOKEN:?set SUPABASE_ACCESS_TOKEN in .env (Supabase account token)}"
: "${NEXT_PUBLIC_SUPABASE_URL:?set NEXT_PUBLIC_SUPABASE_URL in .env}"

# https://<ref>.supabase.co → <ref>
REF="$(printf '%s' "$NEXT_PUBLIC_SUPABASE_URL" | sed -E 's#https://([^.]+)\..*#\1#')"
[ -n "$REF" ] || { echo "could not read a project ref out of $NEXT_PUBLIC_SUPABASE_URL" >&2; exit 2; }

echo "applying $FILE"
echo "     to  project $REF"

BODY="$(python3 -c 'import json,sys; print(json.dumps({"query": open(sys.argv[1]).read()}))' "$FILE")"

HTTP="$(printf '%s' "$BODY" | curl -sS -o /tmp/apply-migration.out -w '%{http_code}' \
  -X POST "https://api.supabase.com/v1/projects/$REF/database/query" \
  -H "Authorization: Bearer $SUPABASE_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -H "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)" \
  --data-binary @-)"

if [ "$HTTP" != "200" ]; then
  echo "FAILED — HTTP $HTTP" >&2
  cat /tmp/apply-migration.out >&2
  echo >&2
  exit 1
fi

echo "ok — $HTTP"
cat /tmp/apply-migration.out
echo
