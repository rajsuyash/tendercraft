/**
 * S21 — the learning meter · `/knowledge`
 *
 * `docs/learning-loop.md` Phase 4. The loop closes at export (services/engine/app/learning.py);
 * this is where a workspace can see whether closing it is actually helping, including when the
 * answer is no.
 */
import { LearningMeter, type Maturity } from "@/components/LearningMeter";
import { engineFetch } from "@/lib/engine";

export const dynamic = "force-dynamic";

export default async function KnowledgePage() {
  const res = await engineFetch("/api/learning/maturity");
  const body = res.ok ? await res.json().catch(() => null) : null;

  if (!body?.ok) {
    return (
      <main className="p-page">
        <h1 className="font-heading text-2xl font-semibold text-ink">What the system has learned</h1>
        <div
          data-learning-error
          className="mt-6 rounded-card border border-danger bg-danger-bg p-card"
        >
          <p className="font-medium text-danger">
            The learning meter could not be loaded ({body?.error?.code ?? "UNAVAILABLE"}).
          </p>
          <p className="mt-2 text-sm text-muted">
            Nothing in your answer library is affected — this screen only reads it.
          </p>
        </div>
      </main>
    );
  }

  return <LearningMeter maturity={body.data as Maturity} />;
}
