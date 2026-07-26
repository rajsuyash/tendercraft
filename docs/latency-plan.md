# Latency plan — closing the geography gap

Status: **Option A EXECUTED 2026-07-26.** Both services now run in `europe-north1` (Finland),
next to the Supabase project in Stockholm. Option B remains the plan for the move to India.

Live demo URLs. The `asia-south1` services were **deleted** on 2026-07-26 so the slow
deployment could not be demoed by accident; those hostnames now 404.

```
web    https://tendercraft-web-eu-822379741897.europe-north1.run.app
engine https://tendercraft-engine-eu-822379741897.europe-north1.run.app
```

Rolling back to Mumbai is still possible — the images remain in the `asia-south1` Artifact
Registry repo (`tendercraft-web:perf`, `tendercraft-engine:perf2`), so it is two
`gcloud run deploy` commands plus repointing `ENGINE_URL`. It is a recreate, not a revision
revert, and the hostnames will differ from the originals.

### Measured result

Same image, same code, same database — only the region changed. Server-side, warm:

| Endpoint | `asia-south1` | `europe-north1` | |
|---|---|---|---|
| `/api/me` | 2.421s | 0.156s | 15.5x |
| `/api/tenders/:id/readiness` | 2.405s | 0.212s | 11.3x |
| `/api/tenders/:id/submission` | 2.797s | 0.247s | 11.3x |
| `/api/workspaces` | 0.858s | 0.090s | 9.5x |

Whole-page, server-side, against the original audit baseline:

| Route | Audit baseline | After code work (Mumbai) | After region move |
|---|---|---|---|
| `/tenders/:id/readiness` | 6.3–6.9s | 2.31s | **0.303s** |
| `/proposals/:id/export` | 3.8–4.0s | 2.17s | **0.294s** |
| `/proposals/:id/score` | 3.7s | 3.05s | **0.312s** |
| `/settings` | ≤3.4s | 1.91s | **0.271s** |
| `/dashboard` | 3.2s cold | 1.43s | **0.275s** |

Click-to-content in the browser: **316–687ms**, with the skeleton painting at **7–13ms**.

The original context, retained because it is the reasoning that led here:

## The one fact everything else follows from

| | Where | |
|---|---|---|
| Compute | Cloud Run `asia-south1` | Mumbai |
| Database | Supabase `eu-north-1` | Stockholm |

**~130ms per database round trip**, and a page render makes many. The code changes already
shipped cut the *number* of round trips (pooled connections, parallel reads, no duplicate
work, streaming shell). They cannot cut the 130ms. Only moving one of the two boxes does that.

Measured after those changes, warm, server-side: the fastest endpoint in the app that touches
the DB at all is `/api/me` at **0.32s** — and it does exactly two queries. That 0.32s floor is
geography, not code.

## Option A — move the compute to the data (recommended for the demo)

Redeploy both Cloud Run services to `europe-north1` (Hamina, Finland), next to the Supabase
project in Stockholm.

- **Data movement: none.** The database does not move, so there is no migration, no dump/restore,
  no RLS re-verification, no cutover window, no rollback plan beyond `gcloud run deploy` back to
  `asia-south1`.
- **Effort:** two `gcloud run deploy` invocations against the images already in Artifact Registry,
  plus repointing `ENGINE_URL` and updating the Supabase Auth allowed-redirect URLs to the new
  service hostnames.
- **Expected:** Hamina↔Stockholm is ~400km, so ~10–15ms per round trip against today's ~130ms —
  roughly a 10x cut on the dominant cost. `/readiness` should land near 0.2s.
- **Cost to users:** one extra ~130ms on the browser→server hop for Indian users. That is paid
  ONCE per page; the 130ms it removes was being paid ten-plus times per page. Cloud Run also sits
  behind Google's anycast edge, so TLS still terminates near the user.
- **Verify before committing:** deploy the engine to `europe-north1` as a canary, hit
  `/api/tenders/:id/readiness`, and compare against the Mumbai revision. If the gain is not ~5x,
  stop and re-measure rather than proceeding on the estimate above.

**Why this is right for a demo specifically:** PRD §9 Indian residency is the reason to prefer
Mumbai, and residency is not binding until real customer data is in the system. Until then,
hosting compute in the EU next to a database that is *already* in the EU changes nothing about
where the data lives — it is in Stockholm either way. Today's split gets the worst of both:
EU data residency AND Mumbai-to-Stockholm latency.

## Option B — move the data to the compute (for when this is paid work)

Migrate to a new Supabase project in `ap-south-1` (Mumbai). This is the option that also
satisfies PRD §9, and it is the one to run when the product moves to Indian cloud.

Sequence:

1. **Create** the `ap-south-1` project. Capture its URL, anon key, and service key.
2. **Schema.** Apply `migrations/0001..0015` in order against the new project. Do not
   `pg_dump --schema` from the old one — replaying the tracked migrations is what proves the
   migration set is complete, and this is the only chance to find out that it isn't.
3. **Verify the security model BEFORE any data lands.** Run `tests/isolation/` against the new
   project. It must pass unmodified. Specifically confirm: RLS enabled on every table,
   `current_workspace_id()` present and membership-validating, the `audit_events` append-only
   trigger, and the partial unique index on live invitations. A table that arrives without its
   policy is a silent cross-workspace read, and the isolation suite is what catches it.
4. **Data.** `pg_dump --data-only` → restore. Order matters for FKs; restore with triggers
   disabled, then re-enable — noting that `audit_events` is append-only, so its trigger must be
   re-enabled *after* its rows land or the restore is refused.
5. **Storage.** Copy the Supabase Storage buckets separately; `pg_dump` does not carry them.
6. **Auth.** Users live in `auth.users`, which is Supabase-managed. Migrating them preserves
   `sub` claims — and every `profiles.user_id`, `workspace_members.user_id`, and audit `actor`
   references those UUIDs. If the user table cannot be transferred with IDs intact, the
   migration becomes a re-invite, not a copy. **Resolve this question before starting anything
   else** — it is the one that decides whether Option B is an afternoon or a project.
7. **Cutover.** Update `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` (build args
   too — they are inlined at build time), and the `tendercraft-supabase-service-key` secret.
   Rebuild the web image; the engine only needs the env change.
8. **Rollback.** Keep the old project live and untouched until the new one has served real
   traffic. Rollback is redeploying the previous revision, which still points at Stockholm.

Known trap from `known-pitfalls.md`: the old project has accumulated undeletable isolation-test
workspaces, because `audit_events` refuses deletion even to the service role. Do not copy that
debris forward — filter the data dump to real workspaces, and run the isolation suite against a
dedicated project from now on.

## Not recommended: migrating to Railway

Railway bills measured usage rather than reserved allocation, so it is genuinely ~5x cheaper
for this idle-heavy workload (~$6/mo against ~$37/mo for Cloud Run `min-instances=1`). It is
still the wrong move here: Railway's regions are Netherlands, US West, US East, and Singapore —
**there is no India region**. That caps how good Option B can ever get and puts compute outside
India permanently, which is the thing PRD §9 eventually forbids. Revisit only if the residency
requirement is dropped.

## Cold starts

`min-instances` is 0 on both services; the first visitor after an idle period pays a container
start (3.2s measured on `/dashboard`). Deliberately left at 0: Cloud Run bills min-instances
against *allocated* CPU and memory 24/7, which is ~$37/mo for the current 1 vCPU/1 GiB web and
2 vCPU/2 GiB engine — a lot for a demo, and the route-level loading skeleton now covers the
start visually rather than showing a frozen screen. Revisit after the region move, when the
remaining latency is small enough that a cold start is the dominant complaint.
