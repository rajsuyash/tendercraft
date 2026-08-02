"use client";

/**
 * The vendor's annual report.
 *
 * Uploads through `/api/knowledge/ingest` — the same path as every other piece of evidence — so
 * it gets the existing text extraction, size ceiling, classification and provenance rather than
 * a second parallel one. The profile only records WHICH library document it is, because "the
 * annual report" is a question a bid manager asks and `doc_type = 'financial'` cannot answer:
 * a turnover certificate is financial too.
 *
 * Worth uploading for two reasons, and the copy says both: it is the source a reviewer wants
 * beside the turnover figures, and it describes what the company sells in the vocabulary its
 * market uses — which is what a tender title is written in, and what a capability statement
 * usually is not.
 */

import { useRef, useState } from "react";

import { translator, type Locale } from "@/lib/i18n";

export function AnnualReportUpload({
  documentId,
  documentName,
  onUploaded,
  locale = "en",
}: {
  documentId: string | null;
  documentName: string | null;
  /** Reports the new library document id up; the parent saves it with the rest of the profile. */
  onUploaded: (id: string, name: string) => void;
  locale?: Locale;
}) {
  const t = translator(locale);
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);

  async function upload(file: File) {
    setBusy(true);
    setError(null);
    setWarning(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch("/api/knowledge/ingest", { method: "POST", body: form });
      const body = await res.json().catch(() => null);
      if (!body?.ok) {
        setError(body?.error?.message ?? t("Could not read that file."));
        return;
      }
      // An unfilled template reaching the library is how "[Insert Designation]" ends up quoted,
      // with a citation attached, in a government submission (docs/known-pitfalls.md).
      const placeholders: string[] = body.data.template_placeholders ?? [];
      if (placeholders.length) {
        setWarning(
          `${t("This file still contains template placeholders")}: ${placeholders
            .slice(0, 3)
            .join(", ")}`,
        );
      }
      onUploaded(body.data.id, body.data.name ?? file.name);
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  }

  return (
    <div data-annual-report>
      {documentId ? (
        <p className="text-sm text-ink">
          <span data-annual-report-name className="font-medium">
            {documentName ?? t("Annual report on file")}
          </span>
          <span className="ml-2 text-xs text-muted">{t("in your knowledge base")}</span>
        </p>
      ) : (
        <p data-missing-field className="text-sm text-warning">
          {t("Not provided")}
        </p>
      )}

      <input
        ref={input}
        type="file"
        accept=".pdf,.doc,.docx,.txt"
        data-annual-report-input
        disabled={busy}
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) void upload(f);
        }}
        className="mt-2 block w-full text-sm text-muted file:mr-3 file:rounded file:border file:border-border file:bg-surface file:px-3 file:py-1.5 file:text-sm file:text-ink"
      />
      <p className="mt-1 text-xs text-muted">
        {t(
          "Stored in your knowledge base with your other evidence. It is also read when you ask for keyword suggestions — an annual report names what you sell in the words the market uses.",
        )}
      </p>
      {busy && <p className="mt-1 text-xs text-muted">{t("Reading the document…")}</p>}
      {warning && <p className="mt-1 text-xs text-warning">{warning}</p>}
      {error && <p className="mt-1 text-xs text-danger">{error}</p>}
    </div>
  );
}
