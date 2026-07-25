# Deployment

Both services run as containers on **Google Cloud Run, `asia-south1` (Mumbai)**.

| Service | URL | Container |
|---|---|---|
| Web (Next.js) | https://tendercraft-web-822379741897.asia-south1.run.app | `Dockerfile.web` (repo root — pnpm workspace needs the root as build context) |
| Engine (FastAPI) | https://tendercraft-engine-822379741897.asia-south1.run.app | `services/engine/Dockerfile` |

Project `resonant-tube-280016`. Mumbai was chosen deliberately: PRD §9 requires Indian
residency, and this is the half of that we control today. **The model endpoint is still
`generativelanguage.googleapis.com` (Google AI Studio), which has no region pinning — see
the residency blocker in BUILD-LOG before any real client data.**

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

```bash
set -a; source .env; set +a
P=resonant-tube-280016; R=asia-south1
E=https://tendercraft-engine-822379741897.asia-south1.run.app
IMG="$R-docker.pkg.dev/$P/cloud-run-source-deploy/tendercraft-web:latest"

# engine — builds from source, Dockerfile in services/engine
cd services/engine
gcloud run deploy tendercraft-engine --source . --project=$P --region=$R \
  --allow-unauthenticated --memory=2Gi --cpu=2 --timeout=600 --max-instances=5 \
  --set-env-vars="NEXT_PUBLIC_SUPABASE_URL=${NEXT_PUBLIC_SUPABASE_URL}" \
  --set-secrets="SUPABASE_SERVICE_JWT=tendercraft-supabase-service-key:latest,GEMINI_API_KEY=tendercraft-gemini-api-key:latest"

# web — needs build args, so it goes through a build config rather than --source
cd ../..
gcloud builds submit --config=cloudbuild.web.yaml --project=$P --region=$R \
  --substitutions="_SB_URL=${NEXT_PUBLIC_SUPABASE_URL},_SB_ANON=${NEXT_PUBLIC_SUPABASE_ANON_KEY},_IMAGE=${IMG}"
gcloud run deploy tendercraft-web --image="$IMG" --project=$P --region=$R \
  --allow-unauthenticated --memory=1Gi --cpu=1 --timeout=300 --max-instances=5 \
  --set-env-vars="NEXT_PUBLIC_SUPABASE_URL=${NEXT_PUBLIC_SUPABASE_URL},NEXT_PUBLIC_SUPABASE_ANON_KEY=${NEXT_PUBLIC_SUPABASE_ANON_KEY},ENGINE_URL=${E}"
```

## Cost posture

`min-instances` is **0** on both — they scale to zero, so idle cost is nothing. The
tradeoff is a cold start of a few seconds on the first request after ~15 minutes idle.
For a scheduled demo, warm both a couple of minutes beforehand:

```bash
curl -s -o /dev/null https://tendercraft-web-822379741897.asia-south1.run.app/login
curl -s -o /dev/null https://tendercraft-engine-822379741897.asia-south1.run.app/health
```

To remove cold starts entirely (roughly $15–25/month for the pair):
`gcloud run services update tendercraft-{web,engine} --min-instances=1 --region=asia-south1`

## Two things that bit during the first deploy

1. **`app/config.py` walked `parents[3]`** to find the repo-root `.env`. In a container the
   app sits at `/app/app`, which has only 3 parents — so it raised `IndexError` at import
   and Cloud Run reported it only as "container failed to listen on PORT". A dev
   convenience must never be able to take down production; it is guarded now.
2. **`outputFileTracingRoot` used `new URL().pathname`**, which percent-encodes. The repo
   path contains a space, so the traced root became `…/07%20Tech%20Projects/…`, Next could
   not resolve it, and it **silently skipped standalone output while still reporting a
   successful build**. Use `fileURLToPath`.
