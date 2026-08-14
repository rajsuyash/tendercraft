/**
 * S19 — manufacturing capability · `/capability`
 *
 * Module H's input side (`docs/feedback/usha-martin.md` asks 2 and 3). The registry and the
 * saved specs are independent reads, so they go out together — serially they would be two
 * app-to-database round trips stacked in front of first paint (docs/known-pitfalls.md).
 */
import {
  CapabilityEditor,
  type ParamDef,
  type ProductSpec,
} from "@/components/CapabilityEditor";
import { engineFetch } from "@/lib/engine";

export const dynamic = "force-dynamic";

export default async function CapabilityPage() {
  const [specsRes, registryRes] = await Promise.all([
    engineFetch("/api/product-specs"),
    engineFetch("/api/spec-parameters"),
  ]);

  const specsBody = specsRes.ok ? await specsRes.json().catch(() => null) : null;
  const registryBody = registryRes.ok ? await registryRes.json().catch(() => null) : null;

  // The registry is the allowlist the editor's dropdown is built from. Without it there is
  // nothing to record, so this is a real failure rather than an empty list.
  if (!registryBody?.ok) {
    return (
      <main className="p-page">
        <h1 className="font-heading text-2xl font-semibold text-ink">Manufacturing capability</h1>
        <div
          data-capability-error
          className="mt-6 rounded-card border border-danger bg-danger-bg p-card"
        >
          <p className="font-medium text-danger">
            The parameter registry could not be loaded ({registryBody?.error?.code ?? "UNAVAILABLE"}
            ).
          </p>
          <p className="mt-2 text-sm text-muted">
            Nothing you have recorded is affected. Retry once the engine is reachable.
          </p>
        </div>
      </main>
    );
  }

  return (
    <CapabilityEditor
      specs={(specsBody?.ok ? specsBody.data.specs : []) as ProductSpec[]}
      registry={registryBody.data.parameters as ParamDef[]}
    />
  );
}
