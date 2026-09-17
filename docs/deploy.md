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
  --allow-unauthenticated --memory=2Gi --cpu=2 --timeout=3600 --max-instances=5 \
  --update-env-vars="NEXT_PUBLIC_SUPABASE_URL=${NEXT_PUBLIC_SUPABASE_URL}" \
  --set-secrets="SUPABASE_SERVICE_JWT=tendercraft-supabase-service-key:latest,GEMINI_API_KEY=tendercraft-gemini-api-key:latest"

# `--update-env-vars`, NOT `--set-env-vars`. The engine now carries eleven variables and this
# command names one: `--set-env-vars` REPLACES the whole set, so the documented form silently
# drops APP_URL, both connector URLs, the cron pair and the inbound domain. That is how
# GEM_CONNECTOR_URL went missing (see the pitfall below).

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

### bidassist-connector — live since 2026-08-29

`services/bidassist-connector` is the licensed multi-portal Indian feed: ten portals, railways
ahead of GeM. Enabled after the decision owner ruled on G-8 (`docs/discovery/source-bidassist.md`
— the guardrail's subject is a *portal*, not a vendor we pay). The registry row carries that
date, and `for_market()` refuses any source without one, so the ruling genuinely gates traffic.

Three things are specific to this service, and each is load-bearing.

**It is the only container in the system holding a source credential.** The key is a Secret
Manager secret injected at RUNTIME, never a build arg — a build arg is baked into an image layer
and survives every `docker history` afterwards. It is `--no-allow-unauthenticated`, unlike
`gem-connector-in` which permits `allUsers`: that connector reads public pages, this one spends a
paid quota and returns licensed data, so an open invoker would let anyone bill us.

**It takes three variables, not one.** Without `BIDASSIST_TENDER_FEED_ID` and
`BIDASSIST_AWARD_FEED_ID` the endpoints refuse by name rather than sweeping zero rows — because
an aggregator returning nothing is indistinguishable from a quiet market, which is exactly how
`GEM_CONNECTOR_URL` stayed broken for weeks.

**The runtime service account needs `roles/secretmanager.secretAccessor` on the secret itself.**
Project-level access is not granted here; every other secret has a per-secret binding. The first
deploy failed on this, and the error arrives at *Creating Revision* — after a full container
build — so it reads like a deploy bug rather than a one-line IAM gap.

```bash
gcloud secrets add-iam-policy-binding tendercraft-bidassist-api-key --project=$P \
  --member="serviceAccount:822379741897-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

cd services/bidassist-connector
gcloud run deploy bidassist-connector --source . --project=$P --region=$R \
  --no-allow-unauthenticated --memory=1Gi --cpu=1 --timeout=900 --max-instances=2 \
  --service-account=822379741897-compute@developer.gserviceaccount.com \
  --update-env-vars="BIDASSIST_TENDER_FEED_ID=${BIDASSIST_TENDER_FEED_ID},BIDASSIST_AWARD_FEED_ID=${BIDASSIST_AWARD_FEED_ID}" \
  --set-secrets="BIDASSIST_API_KEY=tendercraft-bidassist-api-key:latest"

# then, on the ENGINE (merge, never --set-env-vars):
gcloud run services update $ENG --project=$P --region=$R \
  --update-env-vars="BIDASSIST_CONNECTOR_URL=<its url>"
```

## Cost posture

> **Corrected 2026-09-14 — this said `min-instances` is 0 on both, and it is 1 on both.**
> Read off the live services rather than the runbook: engine and web are each `minScale: 1`
> (engine `maxScale: 5`), so neither scales to zero and neither has the cold start described
> below. Whoever raised them did not update this file — and the first draft of this very
> correction said "0 on the web service" without checking, which is the same mistake one
> paragraph later. Measure both, every time:
>
> ```bash
> for S in tendercraft-engine-eu tendercraft-web-eu; do
>   echo -n "$S "
>   gcloud run services describe "$S" --project=resonant-tube-280016 \
>     --region=europe-north1 --format=json | \
>     python3 -c "import json,sys; a=json.load(sys.stdin)['spec']['template']['metadata'].get('annotations',{}); print({k.split('/')[-1]:v for k,v in a.items() if 'Scale' in k or 'throttling' in k})"
> done
> ```
>
> **`run.googleapis.com/cpu-throttling` is unset on the engine, which means CPU is THROTTLED
> once a response is flushed.** That is load-bearing now: `app/tenders.py::_extract_quietly`
> runs the schedule spec read as a FastAPI `BackgroundTask` after the response, so it can
> stall until the next request wakes the instance. It is not lost (minScale is 1) and the
> state stays honest (`specs_extracted_at` remains NULL, the manual button covers it), but if
> stalled reads start appearing in the logs the fix is `--no-cpu-throttling` or a jobs table,
> not a longer timeout.

The text below describes the `min-instances: 0` posture, which is **not** what is deployed
today (see the correction above). Kept because it is the right posture to return to if idle
cost matters, and because the warm-up command is still what you want after a deploy:

```bash
curl -s -o /dev/null https://tendercraft-web-eu-822379741897.europe-north1.run.app/login
curl -s -o /dev/null https://tendercraft-engine-eu-822379741897.europe-north1.run.app/health
```

To remove cold starts entirely (roughly $15–25/month for the pair):
`gcloud run services update tendercraft-{web-eu,engine-eu} --min-instances=1 --region=europe-north1`

## Scheduled jobs

Three product jobs, all in Cloud Scheduler `europe-west1`:

| Job | Schedule (UTC) | Calls | Answers |
|---|---|---|---|
| `tendercraft-sweep` | `0 2,7,12 * * *` (3× daily, incl. weekends) | `POST /internal/cron/sweep` | keeps the corpus current — everything else reads it |
| `tendercraft-alert-digest` | `0 3-13 * * 1-5` (hourly, 08:30–18:30 IST) | `POST /internal/cron/digest` | UML ask 1 — *automatically* circulate relevant tenders |
| `tendercraft-stage-watch` | `0 5,11 * * 1-5` (10:30 + 16:30 IST) | `POST /internal/cron/watch` | UML ask 4 — monitor GeM evaluation stage |

**The sweep runs first each morning and on weekends too**, because tenders are published on
days nobody is at a desk and a Monday digest built on Friday's corpus is a digest about closed
tenders. It sweeps each market ONCE across all workspaces (the corpus is shared) and then
recomputes matches per workspace; `refresh_corpus` stops as soon as a page yields nothing new,
so a routine run costs a few pages rather than a full enumeration.

Without it the feed only moves when someone presses **Refresh**, and it rots in a way that
looks healthy — a date in the corner, rows in the table, and every tender closed weeks ago.
That was the production state on 2026-08-25.

**The engine's request timeout is 3600s because of this job.** At the default 600s the first
scheduled sweep was killed mid-run: the corpus phase had finished, so the data looked updated,
but the per-workspace recompute never ran and the match counts stayed on the old numbers with
nothing logged — Cloud Run cuts the request without an access-log line, so it does not even
look like a failure. If a future job needs longer than an hour it must stop being one HTTP
request rather than chase the ceiling.

**Auth is Google OIDC, not a Supabase session.** All three run as
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

### Pausing and un-pausing the digest

Pause `tendercraft-alert-digest` while it has nothing to do: it fires eleven times a day and,
as of 2026-09-17, no workspace has alerts switched on and the engine service carries no mail
key — so every run selects zero workspaces and sends zero mail.

```bash
gcloud scheduler jobs pause tendercraft-alert-digest \
  --project=resonant-tube-280016 --location=europe-west1
```

**Both** of the following must hold before resuming. Either one alone still produces a no-op.

1. **At least one workspace has alerts on.** `db.list_alerting_workspaces` reads
   `notification_settings` where `enabled is true`; an empty result is the whole digest.

   ```bash
   supabase db query --linked \
     "select workspace_id from public.notification_settings where enabled;"
   ```

2. **The engine can send.** `app/mailer.py` reads `RESEND_API_KEY` and `RESEND_FROM`. With the
   key unset the digest reports "this deployment cannot send"; with `RESEND_FROM` unset it
   falls back to `onboarding@resend.dev`, a Resend test address and not a sender a customer
   digest may use. Read the service's environment:

   ```bash
   gcloud run services describe tendercraft-engine-eu \
     --project=resonant-tube-280016 --region=europe-north1 \
     --format='value(spec.template.spec.containers[0].env[].name)'
   ```

   Measured 2026-09-17: neither name is present. Add them with `--update-env-vars`, never
   `--set-env-vars`, which replaces the whole environment (`docs/known-pitfalls.md`); the key
   belongs in Secret Manager beside the other two.

```bash
gcloud scheduler jobs resume tendercraft-alert-digest \
  --project=resonant-tube-280016 --location=europe-west1
```

### Retry policy

Baseline, read off the live jobs on 2026-09-17:

```bash
for J in tendercraft-sweep tendercraft-alert-digest tendercraft-stage-watch; do
  printf '%s ' "$J"
  gcloud scheduler jobs describe "$J" \
    --project=resonant-tube-280016 --location=europe-west1 \
    --format='value(retryConfig)'
done
```

| Job | retryCount | minBackoff | maxBackoff | maxDoublings | maxRetryDuration |
|---|---:|---|---|---:|---|
| `tendercraft-sweep` | 1 | 5s | 3600s | 5 | 0s |
| `tendercraft-alert-digest` | **2** | 5s | 3600s | 5 | 0s |
| `tendercraft-stage-watch` | 1 | 5s | 3600s | 5 | 0s |

`retryCount` counts retries, not attempts, so the digest makes three calls per trigger — which
is the three `POST /internal/cron/digest` inside one minute that the engine log shows at
12:00 UTC on 2026-09-17, under the quota block. The other two already retry once; the commands
below make the policy explicit on all three and widen the backoff.

```bash
for J in tendercraft-sweep tendercraft-alert-digest tendercraft-stage-watch; do
  gcloud scheduler jobs update http "$J" \
    --project=resonant-tube-280016 --location=europe-west1 \
    --max-retry-attempts=1 --min-backoff=60s --max-backoff=60s
done
```

Every failure these jobs actually have is one a second attempt cannot fix: a quota block lasts
until someone pays or the cycle rolls over, a database outage lasts minutes, a bad deploy lasts
until the next deploy. A 502 thirty seconds after a 502 carries no new information and costs a
scheduler log line, and under a quota block those lines are most of what the log contains —
which is the expensive part, because the real signal is in there with them. One retry covers
the only case retrying helps: a dropped connection or a cold instance. Setting the policy on a
paused job is harmless and does not resume it.

### What a quota block looks like from the engine

Recorded 2026-09-17, when the Supabase org exceeded its Free egress quota and the API was
blocked:

- `GET /health` returns **200**. It touches nothing but the process.
- PostgREST and Auth return **402** to every request.
- Every `POST /internal/cron/*` returns **502**: the handler's first read raises.
- Cloud Run monitoring stays green throughout. The container is healthy; what is behind it is
  not. Nothing goes red, no alert fires, and the first notification is a vendor email.

The shallow `/health` is why this was invisible — it answers a question nobody was asking.
`/health/deep` is being added for exactly this case (workstream A of
`docs/plan/2026-09-17-supabase-free-tier-plan.md`): a check that fails when the database is
unreachable, so a quota block surfaces on the schedule instead of two days later by email.
Cloud Run's readiness probe stays on the shallow one.

## Reading the egress ledger

**Why this exists.** On 2026-09-17 the org hit **12.89 GB of Supabase egress against a 5.5 GB
Free quota** and the API started answering 402 to every request. The first anyone knew was a
vendor email, because nothing in the engine counted a byte and `/health` answers 200 whatever
the database is doing. Both halves of that are fixed here.

**Bytes RECEIVED is what Supabase bills.** Bytes sent are nearly free, so the ledger counts
`len(resp.content)` on every PostgREST response and nothing else.

### The per-call log line

`app/db.py::_rest` logs one INFO per query through the `tendercraft.egress` logger, JSON-shaped
so Cloud Logging parses it. Table names and byte counts only — never a row, never a header:

```json
{"severity":"INFO","message":"supabase egress","logger":"tendercraft.egress",
 "method":"GET","table":"opportunities","route":"POST /internal/cron/sweep",
 "bytes":1216544,"day_bytes":5980233,"day_calls":412}
```

`route` is the request path with identifying segments collapsed (`GET /api/tenders/{id}/analysis`),
so the by-route table stays bounded however many tenders exist.

**None of this shipped until `LOG_LEVEL` did.** The engine had no logging configuration, so the
root logger sat at WARNING and no `logger.info` line in this codebase had ever reached Cloud
Logging — seven days of logs held zero, checked against a positive control. `LOG_LEVEL` defaults
to INFO; set it to WARNING to silence the ledger, and know that silences the cost line too.

A day's total, across every instance:

```bash
gcloud logging read \
  'resource.labels.service_name="tendercraft-engine-eu" jsonPayload.message="supabase egress"' \
  --project=$P --freshness=24h --format='value(jsonPayload.bytes)' | paste -sd+ | bc
```

### The in-process accumulator

`GET /internal/cron/health` (already OIDC-gated, same caller as the three jobs) returns today's
ledger — bytes, calls, by table and by route, biggest first — alongside a **deep** database
probe:

```bash
TOKEN=$(gcloud auth print-identity-token --audiences="$ENGINE_URL")
curl -s -H "Authorization: Bearer $TOKEN" "$ENGINE_URL/internal/cron/health" | jq .data
```

Two things to know before reading the number:

- **It is per container, and Cloud Run scales to zero.** The accumulator answers "today, on
  this instance"; the log query above answers "this cycle, across all of them". Reconciling the
  two is how you notice an instance you did not know about.
- **It rolls over at UTC midnight**, not IST. The Supabase quota cycle is UTC too.

### The health checks, and which is which

| Endpoint | Touches the database | Point it at |
|---|---|---|
| `GET /health` | **No** — by design (EC-6: deterministic screens stay up when Supabase is down) | Cloud Run readiness, the post-deploy warm-up curl |
| `GET /health/deep` | Yes — one `limit=1` row, reports the upstream status code | an uptime check you want to page on |
| `GET /internal/cron/health` | Yes, plus the ledger | Cloud Scheduler |

Anything but a 2xx from PostgREST is unhealthy and answers **503**, so a quota block shows up as
a failing check the same hour instead of an email two days later. `cron/health` still returns
its payload on the 503 — a check that fails without saying how much egress preceded it sends you
looking in a second place.

### The thresholds this is measured against

From `docs/plan/2026-09-17-supabase-free-tier-plan.md` §1 — the bar for going back to Free, read
on or about 2026-10-20 over the trailing 21 days:

| Measure | Bar | Note |
|---|---|---|
| Egress | **≤ 3.5 GB** projected per 30-day cycle | 35% margin under the 5.5 GB Free quota, **with engineering-session days included**. A number that only holds when nobody is working on the product is not a number. |
| Database size | **≤ 300 MB**, growing < 2 MB/day | Free's limit is 500 MB. It was 55 MB after the 2026-09-14 vacuum. |
| Pro-only features | none in use | PITR, extended backups, larger compute, custom domain. |

Any one failing means stay on Pro, and the ledger says why. Either outcome is a success; the
failure mode is deciding without it.

## Downgrading Supabase to Free, and how to know whether to

The org went to Pro for one billing cycle on 2026-09-17 so this decision could be made from a
ledger instead of a feeling. Plan: `docs/plan/2026-09-17-supabase-free-tier-plan.md`. Every
published fact below was read off Supabase's own pages on 2026-09-17 and is quoted; where a
page does not answer the question, this says so rather than guessing. `$P` and `$E` are the
project and engine URL from *Redeploy* above.

### 1. When

| Date | What |
|---|---|
| **on or about 2026-10-20** | Read §2, fill every row, decide. |
| **2026-10-24** | The Pro cycle ends. Downgrading after this bills a second month. |

Four days of slack, deliberately — enough to re-read a figure that looks wrong. The downgrade
itself is self-serve and takes a minute, so the window buys thinking time and nothing else.

### 2. What to read, exactly

Four rows, four instruments. **A blank row is an undecided decision, not a pass.**

| # | Measure | Bar (plan §1) | Measured | Verdict |
|---|---|---|---|---|
| 1 | Egress, projected per 30-day cycle | ≤ 3.5 GB | `[ledger: egress GB, 21-day trailing → fill 2026-10-20]` | ☐ pass ☐ fail |
| 2 | Database size | ≤ 300 MB | `[ledger: database MB → fill 2026-10-20]` | ☐ pass ☐ fail |
| 3 | Database growth | < 2 MB/day | `[ledger: database MB/day → fill 2026-10-20]` | ☐ pass ☐ fail |
| 4 | Pro-only add-ons in use | none | `[ledger: add-ons in use → fill 2026-10-20]` | ☐ pass ☐ fail |

**Engineering-session days count.** A number that only holds when nobody is working on the
product is not a number.

#### Row 1 — egress

Both instruments are set out under *Reading the egress ledger* above: the log query totals the
cycle across every instance, the accumulator reports today on one of them. Read both.

```bash
gcloud logging read \
  'resource.labels.service_name="tendercraft-engine-eu" jsonPayload.message="supabase egress"' \
  --project=$P --freshness=21d --format='value(jsonPayload.bytes)' | paste -sd+ | bc
```

Project it: `bytes × 30 / 21`. Cloud Logging's default retention is 30 days, so a 21-day window
sits inside it — but if the oldest line returned is newer than 21 days, the base is shorter than
you asked for and the projection has to say so.

The by-table and by-route split, and the deep database probe in the same response, come from
`GET /internal/cron/health` — the call is in *The in-process accumulator* above.

#### Rows 2 and 3 — database size and growth

One read over `pg_database_size`, through the Management API. That is the transport
`tools/apply-migration.sh` uses, and both of its gotchas apply unchanged: the User-Agent header
(Cloudflare 403s a default script UA) and the error **body**, which carries the Postgres message
the status line does not.

```bash
set -a; . ./.env; set +a
REF="$(printf '%s' "$NEXT_PUBLIC_SUPABASE_URL" | sed -E 's#https://([^.]+)\..*#\1#')"

printf '%s' '{"query":"select pg_size_pretty(pg_database_size(current_database())) as db_size, pg_database_size(current_database()) as bytes;"}' \
| curl -sS -X POST "https://api.supabase.com/v1/projects/$REF/database/query" \
    -H "Authorization: Bearer $SUPABASE_ACCESS_TOKEN" \
    -H "Content-Type: application/json" \
    -H "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)" \
    --data-binary @-
```

The dashboard SQL editor runs the same statement if you would rather not source `.env`.

**Row 3 needs two readings, and nothing in this repo keeps a size history.** Take a baseline now
and record it here, or 2026-10-20 has nothing to subtract from:

- baseline `[ledger: database MB, baseline → fill on first reading]`,
  taken `[ledger: baseline date → fill on first reading]`
- 55 MB immediately after the 2026-09-14 vacuum, for reference (`docs/known-pitfalls.md`).

#### Row 4 — Pro-only add-ons

The org billing page lists every active add-on with its price and is the single authority:

- <https://supabase.com/dashboard/org/_/billing>

Confirm per project too, and **check both projects** — the wall (F13) means there are two:

| Add-on | Page |
|---|---|
| Daily backups | <https://supabase.com/dashboard/project/_/database/backups/scheduled> |
| Point-in-Time Recovery | <https://supabase.com/dashboard/project/_/database/backups/pitr> |
| Compute size and disk | <https://supabase.com/dashboard/project/_/settings/infrastructure> |
| Custom domain | <https://supabase.com/dashboard/project/_/settings/general> |

### 3. What changes on Free, concretely

Read off <https://supabase.com/pricing> and the docs pages it links, on 2026-09-17.

| What | Free | Pro | What it means here |
|---|---|---|---|
| Egress | "5 GB egress" and "5 GB cached egress" | "250 GB egress (then $0.09 per GB)" | The vendor notice that started this quoted 5.5 GB; the published number is 5 GB. The 3.5 GB bar clears either. Egress counts "Database, Auth, Storage, Edge Functions, Realtime and Log Drains" — the ledger sees only PostgREST, so read it as a floor. |
| Database size | "500 MB database size (Shared CPU • 500 MB RAM)" | "8 GB disk size per project included, then $0.125 per GB" | 55 MB after the 2026-09-14 vacuum. Row 2's bar is 300 MB. |
| Compute | Nano, $0 | "Pro and Team plans include Micro compute in the base price" | **Confirm on the billing page.** The docs cover the upward direction only — "You cannot launch Nano instances on paid plans, only Micro and above - but you might have Nano instances after upgrading from Free Plan" — and say nothing about what a Micro becomes on the way down. |
| Automatic backups | "Not included" | "7 days" | Free gets none. The docs tell free projects to "regularly export their data using the Supabase CLI `db dump` command". **Nothing in this repo does that today**; on Free it becomes ours to schedule. |
| Point-in-Time Recovery | "Not included" | "$100 per month per 7 days retention" | An add-on on top of Pro, not part of it. Not in use — row 4 confirms. |
| Supabase log retention | "1 day" | "7 days" | Does not touch the egress ledger, which lives in Cloud Logging. It does mean a Supabase-side incident older than a day cannot be reconstructed from their logs. |
| Custom domain | "Not included" | "$10 per domain per month per project add on" | "Custom domains are available as a paid add-on for projects on a paid plan". Not in use. |
| Inactivity pause | "Free projects are paused after 1 week of inactivity" | not paused | The operational change. See below. |
| Active projects | "Limit of 2 active projects" | — | "You are entitled to two active free projects. **Paused projects do not count towards your quota.**" So the paused evaluate project costs neither money nor a slot — but resuming it takes the second of two, and there is no third. |

#### The pause is the change that actually bites

"A Free plan project is considered inactive if it does not receive sufficient user database
activity over the past week", and "Typically a few user requests to the database each day over
the previous week is enough to keep the project from being paused."

That is what the two `supabase-keepalive` jobs are for (*Supabase keepalive (free tier)*,
below). **That section says to delete both jobs when the projects move to Pro.** If that was
done, they must be recreated *before* the downgrade — the inactivity clock starts when the plan
changes, not when someone remembers.

```bash
gcloud scheduler jobs list --project=$P --location=europe-west1
```

Measured 2026-09-17: both still exist, since workstream F set a retry policy on all five jobs.
Confirm anyway. It is one command, and what it catches is a paused production database.

If one ever does pause: "Open the Supabase Dashboard" → "Select the organization, followed by
the paused project" → "Click **Resume project** and confirm". How long a pause stays reversible
is **not settled by the published pages**: the docs say "there is a 1-year window to restore the
project on the platform from within Supabase Studio", while a 2024-06-24 changelog entry says
paused Free projects are restorable for 90 days. Do not let it pause.

### 4. How to downgrade

1. Open <https://supabase.com/dashboard/org/_/billing>.
2. Click **Change subscription plan**.
3. Select the Free Plan.

Published, verbatim:

- "The cancellation is immediate."
- "any prepaid subscription fee will be credited back to your organization for unused time in
  the billing cycle. These credits do not expire and will be applied to future invoices"
- "you will also be charged for any excessive usage in the billing cycle"

That last line is why row 1 is read *before* clicking: a cycle that went over on egress is
billed on the way out, and the downgrade does not forgive it.

**Does the running project blip?** The published docs do not say. Nothing on the subscription,
pricing, compute or pausing pages mentions downtime, a restart or a dropped connection during a
plan change. Treat it as unknown — downgrade outside the customer's working hours, with §5 open.

Before clicking:

- [ ] Rows 1–4 filled in and passing, with the ledger output pasted into this file.
- [ ] Both keepalive jobs present.
- [ ] A dump taken and stored off-site. The last Pro daily backup is the last automatic backup
      there will be.

```bash
supabase db dump --linked --file "backup-$(date -u +%Y%m%d).sql"
```

### 5. The morning after

Four checks, in this order. Each fails differently, which is the point.

1. **The database answers.** Not `/health` — that returns 200 through a quota block and a pause
   alike.

   ```bash
   curl -s -o /dev/null -w '%{http_code}\n' "$E/health/deep"
   ```

   200 is healthy. 503 carries `DB_UNHEALTHY` and the upstream status in the envelope.

2. **A scheduled sweep completed.** The accumulator must show bytes against `opportunities`; a
   sweep that ran and read nothing is exactly what this catches.

   ```bash
   TOKEN=$(gcloud auth print-identity-token --audiences="$E")
   curl -s -H "Authorization: Bearer $TOKEN" "$E/internal/cron/health" \
     | jq '.data.egress.bytes, .data.egress.by_table'
   ```

3. **The customer can sign in.** Open the web service and complete a real sign-in. Auth is a
   separate Supabase surface from PostgREST and returned its own 402 during the block, so check
   1 passing does not cover it.

4. **The first full day is under budget.** 3.5 GB over 30 days is **0.117 GB — about 117 MB — a
   day**. Run row 1's query with `--freshness=24h` and compare. One day over is information, not
   a verdict; three in a row is the ledger telling you to go back to Pro.

### 6. When NOT to downgrade

Staying on Pro is not a failure of this exercise. Plan §1 is explicit that either outcome is a
success and that the only failure is deciding without the ledger — so if any row in §2 fails,
stay, and write the failing number in it; that is the plan working, not a setback. There is also
one reason to stay that no row measures: **a customer contract that requires daily backups or
point-in-time recovery.** Free has neither, and a `db dump` on a cron is not the same commitment
as a vendor's retention guarantee. If such a clause exists or is being negotiated, Pro is the
answer whatever the egress says, and that is the owner's call rather than a number's.

## Inbound email (UML ask 4)

`POST /api/inbound/email` accepts a forwarded GeM message, files it, and raises a `bid_action`
when it asks for something. Auth is **HMAC-SHA256 over the raw request body** against
`DISCOVERY_INBOUND_SECRET` (Secret Manager: `tendercraft-inbound-secret`), so it is
provider-agnostic — Cloudflare Email Routing, SES, Mailgun or a small Worker all satisfy it.
Unset secret fails closed (503).

A workspace's address is `<workspaces.inbound_token>@$DISCOVERY_INBOUND_DOMAIN`. Get one with:

```bash
supabase db query --linked "select name, inbound_token from public.workspaces;"
```

**Live since 2026-08-24 on `inbound.aisewak.com`, via Resend** (region eu-west-1, receiving on,
sending off). Two DNS records at Hostinger in the **aisewak.com** zone — a DKIM `TXT` on
`resend._domainkey.inbound` and an `MX` on `inbound` → `inbound-smtp.eu-west-1.amazonaws.com`.
Neither touches `aisewak.com` itself; check that first if company mail ever looks wrong:

```bash
dig +short MX aisewak.com          # must stay 10 SMTP.GOOGLE.com
dig +short MX inbound.aisewak.com  # 10 inbound-smtp.eu-west-1.amazonaws.com
```

**Cloudflare Email Routing was tried first and rejected:** it refuses a subdomain zone on the
free plan and wants the root domain, which would have meant moving nameservers off Hostinger
along with the live Google Workspace MX. Not a trade worth making for this feature.

Resend signs with **svix**, so the endpoint verifies either scheme (`RESEND_WEBHOOK_SECRET`)
and its webhook carries **metadata only** — the body needs a second authenticated read with
`RESEND_INBOUND_API_KEY`. That key is deliberately separate from `RESEND_API_KEY`: the sending
key is send-only and returns `restricted_api_key` on every read path.

Secrets: `tendercraft-resend-webhook-secret`, `tendercraft-resend-inbound-key`.

Smoke test it the way the provider will:

```bash
BODY='{"to":"<token>@inbound.tendercraft.aisewak.com","from":"noreply@gem.gov.in",
       "subject":"Clarification sought","text":"Submit by 30-09-2026 for GEM/2026/B/7876746."}'
SIG=$(python3 -c 'import hmac,hashlib,sys;print(hmac.new(sys.argv[1].encode(),sys.argv[2].encode(),hashlib.sha256).hexdigest())' "$SECRET" "$BODY")
curl -X POST "$E/api/inbound/email" -H "X-TenderCraft-Signature: $SIG" -d "$BODY"
```

Replays are expected traffic, not errors: every provider retries on a non-2xx, so a duplicate
returns 200 with `"status":"duplicate"` and raises no second action.

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
(`GET /health/deep` is the one that does — see *Reading the egress ledger* above. It was added
after a quota block produced exactly this symptom for two days.)
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
