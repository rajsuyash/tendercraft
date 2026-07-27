"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

export type IntakeFile = {
  file_id: string;
  filename: string;
  status: string;
  page_count: number | null;
  error_code: string | null;
  error_detail: string | null;
  ocr_pages: number[];
  illegible_pages: number[];
  proposed_bidder_name: string | null;
  document_type: string | null;
  envelope: string | null;
  confidence: string | null;
  evidence_text: string | null;
  anchor_page: number | null;
  confirmed: boolean;
  bidder_name: string | null;
  in_triage: boolean;
};

export type IntakeState = {
  files: IntakeFile[];
  triage_count: number;
  attribution_threshold: string;
  bids: { id: string; bidder_name: string }[];
};

type BulkResult = {
  received: number;
  ingested: number;
  duplicates: number;
  failed: { filename: string; error_code: string | null; detail: string | null }[];
  rejected_entries: string[];
};

const DOC_TYPE_LABEL: Record<string, string> = {
  technical_bid: "Technical bid",
  financial_bid: "Financial bid",
  emd: "EMD",
  certificate: "Certificate",
  affidavit: "Affidavit",
  form: "Form",
  authorisation: "Authorisation",
  experience_certificate: "Experience certificate",
  financial_statement: "Financial statement",
  covering_letter: "Covering letter",
  other: "Other",
};

export function BulkIntake({ tenderId, state }: { tenderId: string; state: IntakeState }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BulkResult | null>(null);

  async function upload(files: FileList) {
    setBusy(true);
    setError(null);
    setResult(null);
    const form = new FormData();
    for (const f of Array.from(files)) form.append("files", f);
    const res = await fetch(`/api/tenders/${tenderId}/bids/bulk`, { method: "POST", body: form });
    const body = await res.json();
    setBusy(false);
    if (!body.ok) {
      setError(body.error?.message ?? "Could not read the upload");
      return;
    }
    setResult(body.data);
    router.refresh();
  }

  return (
    <section className="mt-6 rounded-card border border-border bg-surface p-card">
      <h2 className="font-heading text-base font-medium text-ink">
        Drop the whole folder
      </h2>
      <p className="mt-1 max-w-2xl text-sm text-muted">
        Everything the portal gave you, at once — PDFs, scans and spreadsheets, or a single ZIP.
        Each file is read, matched to the bidder who sent it, and filed as technical or financial.
        Anything we are not sure about waits for you rather than being guessed at.
      </p>

      <label
        data-bulk-dropzone
        className={`mt-4 flex flex-col items-center justify-center rounded border-2 border-dashed border-border bg-surface-alt p-8 text-center ${
          busy ? "opacity-60" : "cursor-pointer hover:border-primary"
        }`}
      >
        <input
          type="file"
          multiple
          accept=".pdf,.zip,.xlsx,.xlsm,.csv,application/pdf,application/zip"
          className="hidden"
          disabled={busy}
          onChange={(e) => {
            const f = e.target.files;
            if (f && f.length) upload(f);
          }}
        />
        <p className="text-sm font-medium text-ink">
          {busy ? "Reading the submissions…" : "Drop files or a ZIP here"}
        </p>
        <p className="mt-1 text-xs text-muted">
          PDF · ZIP · XLSX · CSV — scanned pages are transcribed automatically
        </p>
      </label>

      {busy && (
        <p className="mt-3 rounded border border-border bg-surface-alt p-3 text-sm text-ink">
          Unpacking, reading each file and working out who sent it. Large archives take a few
          minutes; nothing is lost if you wait.
        </p>
      )}

      {result && (
        <div className="mt-3 rounded border border-border bg-surface-alt p-3 text-sm">
          <p className="font-medium text-ink">
            {result.ingested} of {result.received} file{result.received === 1 ? "" : "s"} read
            {result.duplicates > 0 && ` · ${result.duplicates} already here`}
          </p>
          {result.failed.length > 0 && (
            <ul className="mt-2 space-y-1">
              {result.failed.map((f) => (
                <li key={f.filename} className="text-danger">
                  {f.filename} — {f.detail ?? f.error_code ?? "could not be read"}
                </li>
              ))}
            </ul>
          )}
          {result.rejected_entries.length > 0 && (
            <p className="mt-2 text-warning">
              {result.rejected_entries.length} entr
              {result.rejected_entries.length === 1 ? "y was" : "ies were"} refused from the
              archive: {result.rejected_entries.join(", ")}
            </p>
          )}
        </div>
      )}

      {error && (
        <p role="alert" className="mt-3 rounded border border-danger bg-danger-bg p-3 text-sm text-danger">
          {error}
        </p>
      )}

      {state.triage_count > 0 && (
        <div
          data-triage-banner
          className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded border border-warning bg-warning-bg p-3"
        >
          <p className="text-sm text-warning">
            <strong data-triage-count>{state.triage_count}</strong> file
            {state.triage_count === 1 ? "" : "s"} could not be matched to a bidder with enough
            confidence. Screening stays closed until you settle them — a matrix built on a
            partial set of files looks finished and is not.
          </p>
          <Link
            href={`/tenders/${tenderId}/bids/triage`}
            className="rounded border border-warning px-3 py-1.5 text-sm font-medium text-warning"
          >
            Review {state.triage_count} file{state.triage_count === 1 ? "" : "s"}
          </Link>
        </div>
      )}

      {state.files.length > 0 && (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead>
              <tr className="border-b border-border text-xs uppercase tracking-wide text-muted">
                <th className="py-2 pr-3 font-medium">File</th>
                <th className="py-2 pr-3 font-medium">Bidder</th>
                <th className="py-2 pr-3 font-medium">Type</th>
                <th className="py-2 pr-3 font-medium">Envelope</th>
                <th className="py-2 font-medium">Confidence</th>
              </tr>
            </thead>
            <tbody>
              {state.files.map((f) => (
                <tr key={f.file_id} className="border-b border-border align-top last:border-0">
                  <td className="py-2.5 pr-3">
                    <p className="text-ink">{f.filename}</p>
                    <p className="mt-0.5 text-xs text-muted">
                      {f.page_count ?? "—"} page{f.page_count === 1 ? "" : "s"}
                      {f.ocr_pages.length > 0 && ` · ${f.ocr_pages.length} transcribed from scan`}
                      {f.illegible_pages.length > 0 && (
                        <span className="text-warning">
                          {" "}· {f.illegible_pages.length} still unreadable (p.
                          {f.illegible_pages.join(", p.")})
                        </span>
                      )}
                    </p>
                    {f.error_code && (
                      <p className="mt-0.5 text-xs text-danger">
                        {f.error_detail ?? f.error_code}
                      </p>
                    )}
                  </td>
                  <td className="py-2.5 pr-3">
                    {f.bidder_name ? (
                      <span className="text-ink">{f.bidder_name}</span>
                    ) : (
                      <span className="text-warning">Needs you</span>
                    )}
                    {f.evidence_text && (
                      <p className="mt-0.5 max-w-xs truncate text-xs text-muted" title={f.evidence_text}>
                        “{f.evidence_text}”
                        {f.anchor_page ? ` · p.${f.anchor_page}` : ""}
                      </p>
                    )}
                  </td>
                  <td className="py-2.5 pr-3 text-muted">
                    {f.document_type ? DOC_TYPE_LABEL[f.document_type] ?? f.document_type : "—"}
                  </td>
                  <td className="py-2.5 pr-3">
                    {f.envelope === "financial" ? (
                      <span className="rounded-full bg-info-bg px-2.5 py-0.5 text-xs font-medium text-info">
                        Financial · sealed
                      </span>
                    ) : f.envelope === "technical" ? (
                      <span className="text-muted">Technical</span>
                    ) : (
                      <span className="text-warning">Unknown</span>
                    )}
                  </td>
                  <td className="py-2.5 tabular-nums text-muted">
                    {f.confirmed
                      ? "Confirmed by you"
                      : f.confidence
                        ? Number(f.confidence).toFixed(2)
                        : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
