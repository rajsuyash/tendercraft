"use client";

import { useRouter, useSearchParams } from "next/navigation";

import { StageProgress } from "@/components/StageProgress";
import { Suspense, useEffect, useState } from "react";

/** The pursuit context, in the shape `GET /api/pursuits/{id}` returns. */
type Pursuit = {
  id: string;
  opportunities: {
    portal_ref_no: string | null;
    authority: string | null;
    title: string | null;
    closing_at: string | null;
    document_urls: string[] | null;
  } | null;
};

// S3 — Upload Tender. Drop the package -> engine ingest (OCR/extract) -> verification queue.
// One tender per PACKAGE, not per file: annexures carry eligibility clauses, and three
// separate tenders with three readiness checklists is not what the buyer published.
//
// `useSearchParams` forces a Suspense boundary in the App Router, so the page is split: the
// default export supplies the boundary and UploadForm does the work.
export default function UploadPage() {
  return (
    <Suspense fallback={<main className="mx-auto max-w-2xl p-page" />}>
      <UploadForm />
    </Suspense>
  );
}

function UploadForm() {
  const router = useRouter();
  const search = useSearchParams();
  const pursuitId = search.get("pursuit") ?? "";
  const [status, setStatus] = useState<"idle" | "processing" | "error">("idle");
  const [message, setMessage] = useState<string | null>(null);
  const [illegible, setIllegible] = useState<{ tenderId: string; pages: string[] } | null>(null);
  const [pursuit, setPursuit] = useState<Pursuit | null>(null);

  // Fetched, never read out of the query string. A tender reference shown as authoritative has
  // to come from the row; the URL only says WHICH row.
  useEffect(() => {
    if (!pursuitId) return;
    let live = true;
    void (async () => {
      const r = await fetch(`/api/pursuits/${encodeURIComponent(pursuitId)}`);
      const body = await r.json().catch(() => null);
      if (live && r.ok && body?.ok) setPursuit(body.data as Pursuit);
    })();
    return () => {
      live = false;
    };
  }, [pursuitId]);

  async function upload(files: FileList) {
    const chosen = Array.from(files);
    const first = chosen[0];
    if (!first) return;
    setStatus("processing");
    setIllegible(null);
    setMessage(
      chosen.length === 1
        ? `Reading ${first.name}…`
        : `Reading ${chosen.length} documents: ${chosen.map((f) => f.name).join(", ")}`,
    );
    const form = new FormData();
    // Repeated field name — the engine reads `file` as a list, so the package arrives intact.
    for (const f of chosen) form.append("file", f);
    // The title is a fallback the engine uses only when no document states its own (the
    // first file is the notice by convention; ordering beyond that does not matter).
    form.append("title", first.name.replace(/\.[^.]+$/, ""));
    // Links the resulting tender back to the opportunity it came from, and lets the engine fill
    // in a reference or authority the document itself does not state. Document wins; the portal
    // only fills gaps.
    if (pursuitId) form.append("pursuit_id", pursuitId);
    const res = await fetch("/api/tenders/ingest", { method: "POST", body: form });
    const body = await res.json();
    if (!res.ok) {
      setStatus("error");
      setMessage(body.error?.message ?? "Upload failed");
      return;
    }
    const pages: string[] = body.data.illegible_pages ?? [];
    if (pages.length > 0) {
      // EC-1 / S3-D1: don't silently pass a low-quality scan — surface the pages to re-upload.
      setStatus("idle");
      setMessage(null);
      setIllegible({ tenderId: body.data.tender_id, pages });
      return;
    }
    router.push(`/tenders/${body.data.tender_id}/readiness`);
  }

  return (
    <main className="mx-auto max-w-2xl p-page">
      <h1 className="mb-1 font-heading text-2xl font-semibold text-ink">Upload Tender</h1>
      <p className="mb-6 text-sm text-muted">
        The whole package at once — notice, annexures and BOQ sheets (PDF, XLSX, CSV) become one
        tender. Scanned pages route to manual review when text is illegible.
      </p>

      {pursuit?.opportunities && (
        <section
          data-pursuit-context={pursuit.id}
          className="mb-6 rounded-card border border-border bg-surface-alt p-card"
        >
          <p className="text-xs font-medium uppercase tracking-wide text-muted">
            Uploading for
          </p>
          <p className="mt-1 font-heading text-base font-medium text-ink">
            {pursuit.opportunities.title ?? "Tender"}
          </p>
          <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-1.5 text-sm sm:grid-cols-2">
            {pursuit.opportunities.portal_ref_no && (
              <div className="flex gap-2">
                <dt className="text-muted">Reference</dt>
                <dd className="text-ink">{pursuit.opportunities.portal_ref_no}</dd>
              </div>
            )}
            {pursuit.opportunities.authority && (
              <div className="flex gap-2">
                <dt className="text-muted">Authority</dt>
                <dd className="text-ink">{pursuit.opportunities.authority}</dd>
              </div>
            )}
            {pursuit.opportunities.closing_at && (
              <div className="flex gap-2">
                <dt className="text-muted">Closes</dt>
                <dd className="text-ink">
                  {new Date(pursuit.opportunities.closing_at).toLocaleDateString("en-GB", {
                    day: "2-digit",
                    month: "2-digit",
                    year: "numeric",
                    timeZone: "UTC",
                  })}
                </dd>
              </div>
            )}
          </dl>

          {(pursuit.opportunities.document_urls ?? []).length > 0 && (
            <div className="mt-4">
              <p className="text-xs font-medium uppercase tracking-wide text-muted">
                On the portal
              </p>
              <ul className="mt-1.5 space-y-1">
                {(pursuit.opportunities.document_urls ?? []).map((url, i) => (
                  <li key={url}>
                    <a
                      href={url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm text-primary hover:underline"
                    >
                      Document {i + 1} ↗
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Said out loud, in the same shape as "Published means recorded by you" on S20:
              the user must never think we fetched these for them. */}
          <p className="mt-3 text-xs text-muted">
            We do not download these for you — this product never signs in to a portal. Open
            each link, download the package, and drop it below.
          </p>
        </section>
      )}

      <label
        data-dropzone
        className="flex cursor-pointer flex-col items-center justify-center rounded-card border-2 border-dashed border-border bg-surface p-12 text-center hover:border-primary"
      >
        <input
          type="file"
          multiple
          accept=".pdf,.xlsx,.xlsm,.csv,application/pdf"
          className="hidden"
          disabled={status === "processing"}
          onChange={(e) => {
            const f = e.target.files;
            if (f && f.length) upload(f);
          }}
        />
        <p className="font-heading text-lg font-medium text-ink">Drop tender package here</p>
        <p className="mt-1 text-sm text-muted">
          or click to browse — select every file of the package together
        </p>
        <p className="mt-2 text-xs text-muted">PDF · XLSX · CSV — up to 50 MB in total</p>
      </label>

      {status === "processing" && (
        <div className="mt-4">
          <StageProgress
            stages={[
              "Reading the document",
              "Extracting text from each page",
              "Identifying eligibility requirements",
              "Reading the tender number and title",
              "Building your readiness checklist",
            ]}
            secondsPerStage={9}
            note="usually 30–60s for a short RFP"
          />
        </div>
      )}

      {message && (
        <p
          data-upload-status
          className={`mt-4 text-sm ${status === "error" ? "text-danger" : "text-muted"}`}
        >
          {message}
        </p>
      )}

      {illegible && (
        <div
          data-ocr-gate-warning
          className="mt-4 rounded-card border border-warning bg-warning-bg p-card text-sm text-warning"
        >
          <p className="font-medium">Some pages could not be read (OCR quality gate)</p>
          <p className="mt-1">
            {illegible.pages.join(", ")} appear to be scans with little extractable text —
            each is named by the document it belongs to. Re-upload a clearer copy of{" "}
            {illegible.pages.length === 1 ? "that page" : "those pages"}, then continue to
            verification.
          </p>
          <button
            onClick={() => router.push(`/tenders/${illegible.tenderId}/readiness`)}
            className="mt-3 rounded border border-warning px-3 py-1 text-xs font-medium hover:bg-warning/10"
          >
            Continue with what was extracted
          </button>
        </div>
      )}
    </main>
  );
}
