# Deployment

Both services run as containers on **Google Cloud Run, `europe-north1` (Hamina)**.

| Service | URL | Container |
|---|---|---|
| Web (Next.js) | https://tendercraft-web-eu-822379741897.europe-north1.run.app | `Dockerfile.web` (repo root — pnpm workspace needs the root as build context) |
| Engine (FastAPI) | https://tendercraft-engine-eu-822379741897.europe-north1.run.app | `services/engine/Dockerfile` |

Project `resonant-tube-280016`.

> **This file said `asia-south1` until 2026-08-16, and those services no longer exist.** The
> compute was moved to `europe-north1` on 2026-07-26 to sit beside the Supabase project in
> Stockholm — every DB round trip had been costing ~130ms and endpoints got 9-15x faster with
> no code change (`docs/latency-plan.md`, `docs/known-pitfalls.md`). The Mumbai services were
> **deleted** so the slow deployment could not be demoed by accident, so the commands below,
> as they were written, would have deployed a *new* service at a hostname nothing points at
> while production carried on unchanged — a deploy that appears to succeed and changes nothing.
> Region is now a variable in one place below.
>
> Mumbai remains the destination: PRD §9 requires Indian residency, and satisfying it means
> moving the DATABASE (`docs/latency-plan.md` Option B), not the compute back. **The model
> endpoint is `generativelanguage.googleapis.com` (Google AI Studio), which has no region
> pinning — see the residency blocker in BUILD-LOG before any real client data.**

## Secrets

The service-role key and the Gemini key live in **Secret Manager**, not env vars, because
the service-role key bypasses RLS entirely. The Cloud Run service account is granted
`secretAccessor` on each secret individually rather than project-wide.

```
tendercraft-supabase-service-key   -> SUPABASE_SERVICE_JWT
tendercraft-gemini-api-key         -> GEMINI_API_KEY
```

`NEXT_PUBLIC_*` are plain env vars — the anon key and project URL are public by design
(RLS is what protects the data). They must also be passed as **build args**, because Next
inlines them into the client bundle at build time; runtime-only would ship an empty value.

## Redeploy

**Apply any new migrations FIRST.** The engine reads columns the database must already have;
old code ignores new columns, so migrations-then-code is the only ordering with no broken
window. `services/engine/migrations/` is the chain, applied in filename order. `tools/local-db.sh`
is for the throwaway CI database ONLY — it drops `schema public` and refuses any non-localhost
`DB_URL`.

```bash
set -a; source .env; set +a
P=resonant-tube-280016; R=europe-north1
WEB=tendercraft-web-eu; ENG=tendercraft-engine-eu
E=https://tendercraft-engine-eu-822379741897.europe-north1.run.app
IMG="$R-docker.pkg.dev/$P/cloud-run-source-deploy/tendercraft-web:latest"

# engine — builds from source, Dockerfile in services/engine
cd services/engine
gcloud run deploy $ENG --source . --project=$P --region=$R \
  --allow-unauthenticated --memory=2Gi --cpu=2 --timeout=600 --max-instances=5 \
  --set-env-vars="NEXT_PUBLIC_SUPABASE_URL=${NEXT_PUBLIC_SUPABASE_URL}" \
  --set-secrets="SUPABASE_SERVICE_JWT=tendercraft-supabase-service-key:latest,GEMINI_API_KEY=tendercraft-gemini-api-key:latest"

# web — needs build args, so it goes through a build config rather than --source
cd ../..
gcloud builds submit --config=cloudbuild.web.yaml --project=$P --region=$R \
  --substitutions="_SB_URL=${NEXT_PUBLIC_SUPABASE_URL},_SB_ANON=${NEXT_PUBLIC_SUPABASE_ANON_KEY},_IMAGE=${IMG}"
gcloud run deploy $WEB --image="$IMG" --project=$P --region=$R \
  --allow-unauthenticated --memory=1Gi --cpu=1 --timeout=300 --max-instances=5 \
  --set-env-vars="NEXT_PUBLIC_SUPABASE_URL=${NEXT_PUBLIC_SUPABASE_URL},NEXT_PUBLIC_SUPABASE_ANON_KEY=${NEXT_PUBLIC_SUPABASE_ANON_KEY},ENGINE_URL=${E}"
```

Confirm the service names before deploying — `gcloud run services list --project=$P` is the
only authority, and a typo creates a new service rather than failing.

## Cost posture

`min-instances` is **0** on both — they scale to zero, so idle cost is nothing. The
tradeoff is a cold start of a few seconds on the first request after ~15 minutes idle.
For a scheduled demo, warm both a couple of minutes beforehand:

```bash
curl -s -o /dev/null https://tendercraft-web-eu-822379741897.europe-north1.run.app/login
curl -s -o /dev/null https://tendercraft-engine-eu-822379741897.europe-north1.run.app/health
```

To remove cold starts entirely (roughly $15–25/month for the pair):
`gcloud run services update tendercraft-{web-eu,engine-eu} --min-instances=1 --region=europe-north1`

## Scheduled jobs

Two product jobs, both in Cloud Scheduler `europe-west1`:

| Job | Schedule (UTC) | Calls | Answers |
|---|---|---|---|
| `tendercraft-alert-digest` | `0 3-13 * * 1-5` (hourly, 08:30–18:30 IST) | `POST /internal/cron/digest` | UML ask 1 — *automatically* circulate relevant tenders |
| `tendercraft-stage-watch` | `0 5,11 * * 1-5` (10:30 + 16:30 IST) | `POST /internal/cron/watch` | UML ask 4 — monitor GeM evaluation stage |

**Auth is Google OIDC, not a Supabase session.** Both jobs run as
`tendercraft-cron@…iam.gserviceaccount.com`, and `app/cron_auth.py` checks two things
independently: the token's audience is this service's URL, and the caller's email is in
`CRON_SERVICE_ACCOUNTS`. Either alone is weak — anyone can mint a valid Google token for an
arbitrary audience, and a token minted for another service is still a valid Google token.
There is no shared secret to store or rotate. **Both env vars unset fails closed** (503), so a
deployment that forgets them has no scheduled jobs rather than an open write endpoint.

Diagnose without side effects — this sends nothing and touches no portal:

```bash
gcloud scheduler jobs run tendercraft-alert-digest --project=$P --location=europe-west1
# then, for the caller identity the engine actually saw:
gcloud logging read 'resource.labels.service_name="tendercraft-engine-eu"' \
  --project=$P --limit=5 --freshness=10m --format="value(textPayload)"
```

The digest is safe to re-run: `select_for_digest` is handed the already-sent ledger, so a
second run in the same hour sends nothing. The watcher is capped at 25 bids per workspace
because each costs up to three requests to a government site.

Both endpoints exist so a schedule can call what a button already calls — the route adds no
threshold of its own. A scheduled run and a user pressing *Check watched bids* must produce
the same outcome, or only one of the two paths is the one that gets tested.

## Supabase keepalive (free tier)

Supabase pauses a **free-tier** project after 7 days with no API activity. Both Cloud Run
services scale to zero, so an idle week is normal here and the pause is not hypothetical.

**There are two Supabase projects** — the wall (F13) requires it — so there are two jobs,
one per project, both every 3 days:

```bash
gcloud scheduler jobs list --project=$P --location=europe-west1
```

| Job | Project | Pings |
|---|---|---|
| `supabase-keepalive` | bidder | `/rest/v1/workspaces?select=id&limit=1` |
| `supabase-keepalive-evaluate` | evaluate | `/rest/v1/tenders?select=id&limit=1` |

`europe-west1`, not `europe-north1` — Scheduler has no Hamina region. Each carries that
project's own anon `apikey` header (public by design, same key its web bundle ships). They
read one id; RLS returns nothing to an anon caller, which is fine — the request is the
point, not the rows.

**The evaluate project had already paused** when these were added (2026-08-24): it has had
no users since July, while the bidder project stayed warm on connector traffic. Symptom to
recognise, because it does not look like a pause — DNS resolves normally and Cloudflare
answers, so you get **502 on `/auth/v1/*` and 521 on `/rest/v1/*`**, and both Cloud Run
services still return 200 on `/health` because that handler never touches the database.
Resume is a dashboard click; a keepalive prevents the pause but cannot undo one.

**Delete both jobs when the projects move to Pro.** Pro does not pause, and a keepalive
that outlives its reason is a cron nobody can explain.

## Two things that bit during the first deploy

1. **`app/config.py` walked `parents[3]`** to find the repo-root `.env`. In a container the
   app sits at `/app/app`, which has only 3 parents — so it raised `IndexError` at import
   and Cloud Run reported it only as "container failed to listen on PORT". A dev
   convenience must never be able to take down production; it is guarded now.
2. **`outputFileTracingRoot` used `new URL().pathname`**, which percent-encodes. The repo
   path contains a space, so the traced root became `…/07%20Tech%20Projects/…`, Next could
   not resolve it, and it **silently skipped standalone output while still reporting a
   successful build**. Use `fileURLToPath`.
