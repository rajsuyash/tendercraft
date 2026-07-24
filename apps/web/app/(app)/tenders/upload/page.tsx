"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

// S3 — Upload Tender. Drop a PDF -> engine ingest (OCR/extract) -> verification queue.
export default function UploadPage() {
  const router = useRouter();
  const [status, setStatus] = useState<"idle" | "processing" | "error">("idle");
  const [message, setMessage] = useState<string | null>(null);
  const [illegible, setIllegible] = useState<{ tenderId: string; pages: number[] } | null>(null);

  async function upload(file: File) {
    setStatus("processing");
    setIllegible(null);
    setMessage(`Parsing ${file.name}…`);
    const form = new FormData();
    form.append("file", file);
    form.append("title", file.name.replace(/\.pdf$/i, ""));
    const res = await fetch("/api/tenders/ingest", { method: "POST", body: form });
    const body = await res.json();
    if (!res.ok) {
      setStatus("error");
      setMessage(body.error?.message ?? "Upload failed");
      return;
    }
    const pages: number[] = body.data.illegible_pages ?? [];
    if (pages.length > 0) {
      // EC-1 / S3-D1: don't silently pass a low-quality scan — surface the pages to re-upload.
      setStatus("idle");
      setMessage(null);
      setIllegible({ tenderId: body.data.tender_id, pages });
      return;
    }
    router.push(`/tenders/${body.data.tender_id}/verify`);
  }

  return (
    <main className="mx-auto max-w-2xl p-page">
      <h1 className="mb-1 font-heading text-2xl font-semibold text-ink">Upload Tender</h1>
      <p className="mb-6 text-sm text-muted">
        PDF tender packages (GeM / CPPP / state portals). Scanned pages route to manual review
        when text is illegible.
      </p>

      <label
        data-dropzone
        className="flex cursor-pointer flex-col items-center justify-center rounded-card border-2 border-dashed border-border bg-surface p-12 text-center hover:border-primary"
      >
        <input
          type="file"
          accept="application/pdf"
          className="hidden"
          disabled={status === "processing"}
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) upload(f);
          }}
        />
        <p className="font-heading text-lg font-medium text-ink">Drop tender package here</p>
        <p className="mt-1 text-sm text-muted">or click to browse files</p>
      </label>

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
            Page{illegible.pages.length === 1 ? "" : "s"} {illegible.pages.join(", ")} appear to be
            scans with little extractable text. Re-upload a clearer copy of{" "}
            {illegible.pages.length === 1 ? "that page" : "those pages"}, then continue to
            verification.
          </p>
          <button
            onClick={() => router.push(`/tenders/${illegible.tenderId}/verify`)}
            className="mt-3 rounded border border-warning px-3 py-1 text-xs font-medium hover:bg-warning/10"
          >
            Continue with what was extracted
          </button>
        </div>
      )}
    </main>
  );
}
