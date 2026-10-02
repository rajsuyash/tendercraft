# Cloud Run min-instances 1 → 0 (2026-10-02)

## What changed

`tendercraft-engine-eu` and `tendercraft-web-eu` (project `resonant-tube-280016`, region
`europe-north1`) were set to `--min-instances=0`. Nothing else changed: CPU throttling,
maxScale, image and env are untouched.

| Service | Before (measured 2026-10-02) | After (measured) | Serving revision |
|---|---|---|---|
| engine | minScale 1 / maxScale 5, 2 vCPU / 2 GiB | `{'maxScale': '5'}` | `tendercraft-engine-eu-00079-59m` (100%) |
| web | minScale 1 / maxScale 5, 1 vCPU / 1 GiB | `{'maxScale': '5'}` | `tendercraft-web-eu-00078-n2d` (100%) |

Smoke test after the change: web `/login` 200 in 2.09s (cold start); engine `/health` 200 in
0.10–0.13s.

```bash
gcloud run services update tendercraft-engine-eu --min-instances=0 --region=europe-north1 --project=resonant-tube-280016 --quiet
gcloud run services update tendercraft-web-eu --min-instances=0 --region=europe-north1 --project=resonant-tube-280016 --quiet
```

## Why

Google Cloud Billing → Reports, billing account `01DA5A-3BD796-4C3580`, grouped by SKU,
2026-07-01 → 2026-10-02: **€75.01 net** (incl. −€14.08 savings); Google's forecast for Jul–Oct
was €114.57.

| SKU | Net |
|---|---|
| Cloud Run — Services Min Instance Memory (Request-based billing) | €34.21 |
| Cloud Run — Services Min Instance CPU (Request-based billing) | €27.68 |
| Cloud Run — Services CPU (Request-based billing) | €5.37 |
| Cloud Build — E2 CPU (europe-north1 + asia-south1 + global) | €3.39 |
| Artifact Registry — Storage (21.84 GiB-month) | €1.77 |
| Cloud Run — Services Memory (Request-based billing) | €0.68 |
| Cloud Build — E2 RAM europe-north1 | €0.44 |
| Secret Manager — storage | €0.36 |

The two min-instance lines are €61.89, about **83% of spend** — paying for warm instances that
were idle. Cloud Monitoring `billable_instance_time` showed ~720 h per 30 days on each of the
two services. Card charges: €5.14 on 2026-08-01, €44.12 on 2026-10-01.

Expected saving ≈ €35/month — an **estimate**, not yet measured. Re-check Billing → Reports
for November.

## Trade-offs / risks

- **Cold start** on the first request after idle: ≈2s measured on web `/login` today; 3.2s on
  `/dashboard` per `docs/latency-plan.md`.
- **Engine background spec read.** `app/tenders.py::_extract_quietly` runs as a FastAPI
  `BackgroundTask` after the response, with CPU throttled. At minScale 0 an idle instance can be
  reclaimed, so that read can now be *lost*, not just stalled. State stays honest
  (`specs_extracted_at` stays NULL; the manual button re-runs it) — see `docs/deploy.md`
  § Cost posture. If lost extractions show up, fix with `--no-cpu-throttling` or a jobs table,
  not by going back to min-instances=1.
- **Cloud Scheduler crons** (sweep / alert-digest / stage-watch) call HTTP endpoints, so they
  wake the service themselves — no change expected.

## Stale docs to fix later (not edited here)

- `docs/deploy.md` § Cost posture — the 2026-09-14 correction block says minScale is 1 on both.
- `services/engine/app/tenders.py` — comments (grep `min-instances is 1`) say the same.

## Rollback

```bash
gcloud run services update tendercraft-engine-eu --min-instances=1 --region=europe-north1 --project=resonant-tube-280016
gcloud run services update tendercraft-web-eu --min-instances=1 --region=europe-north1 --project=resonant-tube-280016
```

## Other optional saving

Artifact Registry holds ~21.8 GiB of images. A cleanup policy (keep the last N) would trim
roughly €0.60/month.

## Follow-ups (same day)

- **Measured, not estimated:** Cloud Monitoring `billable_instance_time` shows both services at
  60 billable min/hour up to the new revisions (created 16:04–16:05 UTC), then **zero** for the
  three hours after. The euro saving still needs the November billing report.
- **Budget guard:** budget "GCP monthly guard (post min-instances cut)" on billing account
  `01DA5A-3BD796-4C3580` — €15/month, email at 50% and 100% of actual spend and at 100% of
  forecast. If idle billing comes back, this fires before the invoice does.
- **Artifact Registry cleanup policy** on both `cloud-run-source-deploy` repos (europe-north1,
  asia-south1): delete versions older than 30 days, but always keep each package's 10 most
  recent (Keep wins over Delete), so every service's live image and recent rollbacks survive.
  Before: europe-north1 14.0 GB (74 engine + 72 web images). Applied by Google asynchronously.
- `services/engine/app/tenders.py` comments updated in `d12d9a0`.
