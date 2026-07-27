#!/usr/bin/env bash
# Build a throwaway Supabase database from the migration chain — for CI, and for anyone who
# wants a scratch environment locally.
#
# Why this exists: the ET-6 isolation suite is CI-blocking, and it needs a LIVE Supabase
# (GoTrue sign-in, PostgREST, RLS) rather than a bare Postgres. Pointing it at the production
# project was the obvious option and is the wrong one — the suite creates workspaces and
# audits actions in them, and `audit_events` is append-only, so every CI run would deposit
# PERMANENTLY undeletable rows into the database we develop against (see
# docs/known-pitfalls.md; this already blocked a constraint on `workspaces` once). A local
# stack is destroyed with the container, costs nothing, has no shared GoTrue rate limit, and
# needs no repository secrets — so fork PRs can run the Sev-1 control too.
#
# Bonus guarantee, and it is not a small one: this replays migrations 0001→N onto an EMPTY
# database on every push. Nothing else verifies that. Without it we could not stand up a
# staging environment, could not migrate regions, and could not recover from a loss — and we
# would not find out until we tried.
#
# Usage: supabase start && ./tools/local-db.sh

set -euo pipefail
cd "$(dirname "$0")/.."

DB_URL="${DB_URL:-postgresql://postgres:postgres@127.0.0.1:54322/postgres}"
API_URL="${API_URL:-http://127.0.0.1:54321}"
MIGRATIONS="services/engine/migrations"

# ---------------------------------------------------------------------------------------
# HARD GUARD. This script DROPS SCHEMA public CASCADE. It must be impossible to point it at a
# real project, no matter what someone exports into DB_URL in a hurry.
# ---------------------------------------------------------------------------------------
case "$DB_URL" in
  *@127.0.0.1:*|*@localhost:*|*@db:*) ;;   # local stack, or the service name inside CI compose
  *)
    echo "::error::refusing to run against a non-local database: ${DB_URL%%\?*}"
    echo "          this script drops and rebuilds the public schema"
    exit 1
    ;;
esac

# The chain is NOT replay-safe over an already-migrated database — 0010 renames tenant_id to
# workspace_id, so re-running 0001 fails on a column that no longer exists. That is correct for
# a migration chain and it is why this starts from empty every time rather than trying to be
# idempotent.
echo "── resetting public schema (local only) ────────────────────────────"
psql "$DB_URL" -v ON_ERROR_STOP=1 -q -c "drop schema if exists public cascade; create schema public;" > /dev/null
echo "  empty"

export PGOPTIONS='-c client_min_messages=warning'

echo "── replaying $(ls "$MIGRATIONS"/*.sql | wc -l | tr -d ' ') migrations ─────────────────"
for f in "$MIGRATIONS"/*.sql; do
  printf '  %s' "$(basename "$f")"
  psql "$DB_URL" -v ON_ERROR_STOP=1 -q -f "$f" > /dev/null
  printf '  ok\n'
done

echo "── grants ──────────────────────────────────────────────────────────"
# Hosted Supabase grants these to the API roles by default; a database built by piping SQL
# through psql does not, so PostgREST answers 42501 for every table. Mirroring the hosted
# grants is what makes the local database behave like production.
#
# This does NOT weaken the isolation proof: `anon` and `authenticated` remain fully subject to
# RLS, which is the actual control, and `service_role` bypasses RLS here exactly as it does in
# production. Granting table privileges is precisely why the RLS policies have to be right.
psql "$DB_URL" -v ON_ERROR_STOP=1 -q <<'SQL' > /dev/null
grant usage on schema public to anon, authenticated, service_role;
grant all on all tables    in schema public to anon, authenticated, service_role;
grant all on all sequences in schema public to anon, authenticated, service_role;
grant all on all functions in schema public to anon, authenticated, service_role;
alter default privileges in schema public
  grant all on tables to anon, authenticated, service_role;
SQL
echo "  applied"

echo "── PostgREST schema cache ──────────────────────────────────────────"
# PostgREST cached the schema when the stack booted, which was BEFORE these tables existed.
# Without this reload every request 404s on a table that is plainly there — a confusing
# failure that reads like a broken migration.
psql "$DB_URL" -q -c "notify pgrst, 'reload schema';" > /dev/null
for i in $(seq 1 20); do
  code=$(curl -s -o /dev/null -w '%{http_code}' \
    "$API_URL/rest/v1/workspaces?select=id&limit=1" \
    -H "apikey: ${SUPABASE_SERVICE_JWT:-}" -H "Authorization: Bearer ${SUPABASE_SERVICE_JWT:-}")
  if [ "$code" = "200" ]; then echo "  ready after ${i}s"; exit 0; fi
  sleep 1
done

echo "::error::PostgREST did not serve public.workspaces after the reload (last status $code)"
exit 1
