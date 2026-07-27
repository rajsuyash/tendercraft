import Link from "next/link";

import { GenerateMatrixButton, MatrixWorkspace, type Matrix } from "@/components/MatrixWorkspace";
import { engineFetch } from "@/lib/engine";

/**
 * S17 — the compliance matrix, available from TOM lock onward with no proposal and no
 * Generator run. That is the whole point of Module G: the bid manager who will draft in Word
 * still gets the artifact they would otherwise spend a day building in Excel.
 *
 * Coverage and the completeness verdict are read from the engine, never recomputed here —
 * one figure, one function (G-FR7).
 */
export default async function MatrixPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const res = await engineFetch(`/api/tenders/${id}/matrix`, { method: "GET" });
  const body = await res.json();

  if (!res.ok || !body.ok) {
    const code = body?.error?.code;
    return (
      <main className="p-page">
        <h1 className="font-heading text-2xl font-semibold text-ink">Compliance matrix</h1>
        <div data-matrix-empty className="mt-6 rounded-card border border-hairline bg-surface p-card">
          <p className="text-sm text-muted">
            {code === "TOM_NOT_LOCKED"
              ? "Lock the tender model first — the matrix copies requirement text from it, and an unlocked model can still change."
              : (body?.error?.message ?? "Could not load the matrix.")}
          </p>
          <Link
            href={`/tenders/${id}`}
            className="mt-3 inline-block text-sm font-medium text-primary hover:underline"
          >
            Back to tender →
          </Link>
        </div>
      </main>
    );
  }

  const matrix = body.data as Matrix;

  if (matrix.rows.length === 0) {
    return (
      <main className="p-page">
        <h1 className="font-heading text-2xl font-semibold text-ink">Compliance matrix</h1>
        <div data-matrix-empty className="mt-6 rounded-card border border-hairline bg-surface p-card">
          <p className="text-sm text-muted">
            No matrix yet. Generating builds one row per locked requirement, with its source
            anchor, and lists every requirement sentence in the document that has no row.
          </p>
          {/* Deliberately not a plain form POST: that would navigate the user onto the raw
              JSON envelope on any non-2xx, which this codebase has already been bitten by. */}
          <GenerateMatrixButton tenderId={id} />
        </div>
      </main>
    );
  }

  return (
    <main className="p-page">
      <header className="mb-6">
        <h1 className="font-heading text-2xl font-semibold text-ink">Compliance matrix</h1>
        {/* Name the tender. Bid desks run 15–30 pursuits at once; a page headed only
            "Compliance matrix" is ambiguous the moment a second tab is open. */}
        <p className="text-sm text-muted">
          <Link href={`/tenders/${id}`} className="text-primary hover:underline">
            {matrix.title ?? "Tender"}
          </Link>{" "}
          · every requirement in the locked tender model, with where it is answered and who owns
          it. Export to Excel and re-import without losing traceability.
        </p>
      </header>
      <MatrixWorkspace tenderId={id} initial={matrix} />
    </main>
  );
}

