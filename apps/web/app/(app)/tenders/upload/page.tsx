"use client";

import { useRouter } from "next/navigation";

import { StageProgress } from "@/components/StageProgress";
import { useState } from "react";

// S3 — Upload Tender. Drop the package -> engine ingest (OCR/extract) -> verification queue.
// One tender per PACKAGE, not per file: annexures carry eligibility clauses, and three
// separate tenders with three readiness checklists is not what the buyer published.
export default function UploadPage() {
  const router = useRouter();
  const [status, setStatus] = useState<"idle" | "processing" | "error">("idle");
  const [message, setMessage] = useState<string | null>(null);
  const [illegible, setIllegible] = useState<{ tenderId: string; pages: string[] } | null>(null);

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
