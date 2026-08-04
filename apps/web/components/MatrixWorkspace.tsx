"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { sourceAnchor } from "@/lib/format";

import { ReuseSuggestions } from "./ReuseSuggestions";

// Mirrors app/deterministic/matrix.py::MatrixRowStatus. If one end changes, change the other
// — a UI array that mirrors a server enum WILL drift, and the symptom is a dead-looking
// control that 422s (known-pitfalls).
const UNMAPPED_PREVIEW = 20;

const STATUSES = ["not_started", "drafting", "drafted", "reviewed", "approved"] as const;
type Status = (typeof STATUSES)[number];

const STATUS_LABEL: Record<Status, string> = {
  not_started: "Not started",
  drafting: "Drafting",
  drafted: "Drafted",
  reviewed: "Reviewed",
  approved: "Approved",
};

export type MatrixRow = {
  id: string;
  criterion_id: string;
  requirement_text: string;
  requirement_level: "mandatory" | "desirable" | "self_attestation";
  anchor_page: number | null;
  anchor_clause: string | null;
  anchor_document: string | null;
  evidence_required: string | null;
  response_ref: string | null;
  status: Status;
  notes: string | null;
};

export type Unmapped = {
  id: string;
  sentence: string;
  page: number | null;
  resolution: "open" | "not_a_requirement" | "mapped";
};

export type Matrix = {
  tender_id: string;
  title: string | null;
  rows: MatrixRow[];
  coverage: {
    total: number;
    resolved: number;
    mandatory_total: number;
    mandatory_resolved: number;
    fraction: number;
    mandatory_fraction: number;
  };
  unmapped: Unmapped[];
  open_unmapped: number;
  complete: boolean;
  blockers: string[];
};

// Requirement LEVEL is not a verdict. DESIGN_SPEC §C reserves success/danger/warning for
// Pass/Fail/Needs-review and forbids repurposing them — and rendering every mandatory row in
// danger red made a freshly generated matrix look like a wall of failures when nothing has
// been assessed yet. Level gets neutral weight; verdict colour stays for verdicts.
const LEVEL_STYLE: Record<MatrixRow["requirement_level"], string> = {
  mandatory: "bg-ink/10 text-ink font-semibold",
  desirable: "bg-surface-alt text-muted",
  self_attestation: "bg-surface-alt text-muted",
};

const LEVEL_LABEL: Record<MatrixRow["requirement_level"], string> = {
  mandatory: "Mandatory",
  desirable: "Desirable",
  self_attestation: "Self-attested",
};

/** True once a tender spans more than one document — then the page alone stops resolving. */
function spansDocuments(rows: MatrixRow[]): boolean {
  return new Set(rows.map((r) => r.anchor_document).filter(Boolean)).size > 1;
}

export function MatrixWorkspace({ tenderId, initial }: { tenderId: string; initial: Matrix }) {
  const [matrix, setMatrix] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  const [showAllUnmapped, setShowAllUnmapped] = useState(false);
  const [busy, startTransition] = useTransition();
  const router = useRouter();
  const multiDocument = spansDocuments(matrix.rows);

  async function send(path: string, init: RequestInit) {
    setError(null);
    const res = await fetch(`/api/tenders/${tenderId}/matrix${path}`, init);
    const body = await res.json();
    if (!res.ok || !body.ok) {
      setError(body?.error?.message ?? "request failed");
      return;
    }
    setMatrix(body.data);
    startTransition(() => router.refresh());
  }

  const setStatus = (rowId: string, status: Status) =>
    send(`/rows/${rowId}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ status }),
    });

  const resolve = (id: string, resolution: "not_a_requirement" | "mapped") =>
    send(`/unmapped/${id}/resolve`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ resolution }),
    });

  async function onImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    await send("/import", { method: "POST", body: form });
    e.target.value = "";
  }

  const cov = matrix.coverage;
  const open = matrix.unmapped.filter((u) => u.resolution === "open");
  const outstandingMandatory = cov.mandatory_total - cov.mandatory_resolved;

  return (
    <div className="space-y-6">
      <section className="flex flex-wrap items-center gap-4">
        <div className="rounded-card border border-hairline bg-surface p-card">
          <p className="text-xs uppercase tracking-wide text-muted">Mandatory resolved</p>
          <p className="font-heading text-2xl font-semibold text-ink">
            {cov.mandatory_resolved}/{cov.mandatory_total}
          </p>
          <p className="text-xs text-muted">
            {cov.resolved}/{cov.total} of all requirements
          </p>
        </div>

        {/* The denominator. A count with no list is just another number to distrust. */}
        <div
          data-unmapped-count={matrix.open_unmapped}
          className={`rounded-card border p-card ${
            matrix.open_unmapped > 0
              ? "border-warning bg-warning-bg"
              : "border-hairline bg-surface"
          }`}
        >
          <p className="text-xs uppercase tracking-wide text-muted">Unmapped requirements</p>
          <p
            className={`font-heading text-2xl font-semibold ${
              matrix.open_unmapped > 0 ? "text-warning" : "text-success"
            }`}
          >
            {matrix.open_unmapped}
          </p>
          <p className="text-xs text-muted">
            {matrix.open_unmapped > 0
              ? "sentences found in the tender with no matrix row"
              : "every requirement sentence is accounted for"}
          </p>
        </div>

        <div className="ml-auto flex items-center gap-2">
          <a
            href={`/api/tenders/${tenderId}/matrix/export.xlsx`}
            className="rounded-control border border-hairline px-3 py-1.5 text-sm font-medium text-ink hover:bg-surface-alt"
          >
            Export .xlsx
          </a>
          <label className="cursor-pointer rounded-control border border-hairline px-3 py-1.5 text-sm font-medium text-ink hover:bg-surface-alt">
            Import .xlsx
            <input type="file" accept=".xlsx" className="hidden" onChange={onImport} />
          </label>
        </div>
      </section>

      {error && (
        <p data-matrix-error className="rounded-card border border-danger bg-danger-bg p-card text-sm text-danger">
          {error}
        </p>
      )}

      {/* The gate returns one blocker per offending row, each keyed by criterion id — correct
          for an API, unreadable as a UI. A freshly generated matrix has every mandatory row
          outstanding, so rendering that list verbatim greeted the user with a column of UUIDs
          describing the normal starting state. Summarise; the table below already says which
          rows they are. */}
      {!matrix.complete && (
        <p
          data-matrix-blockers
          data-blocker-count={matrix.blockers.length}
          className="rounded-card border border-hairline bg-surface-alt p-card text-sm text-muted"
        >
          <span className="font-medium text-ink">Not yet complete.</span>{" "}
          {[
            matrix.open_unmapped > 0 &&
              `${matrix.open_unmapped} requirement sentence${matrix.open_unmapped === 1 ? "" : "s"} still unmapped`,
            outstandingMandatory > 0 &&
              `${outstandingMandatory} mandatory requirement${outstandingMandatory === 1 ? "" : "s"} not yet drafted`,
          ]
            .filter(Boolean)
            .join(" · ")}
        </p>
      )}

      {open.length > 0 && (
        <section className="rounded-card border border-warning bg-surface">
          <h2 className="border-b border-hairline p-card font-heading text-sm font-semibold text-ink">
            Requirement sentences with no row ({open.length})
          </h2>
          <ul className="divide-y divide-hairline">
            {(showAllUnmapped ? open : open.slice(0, UNMAPPED_PREVIEW)).map((u) => (
              <li key={u.id} data-unmapped-sentence className="flex gap-4 p-card text-sm">
                <span className="shrink-0 font-mono text-xs text-muted">
                  {u.page ? `p.${u.page}` : "—"}
                </span>
                <span className="flex-1 text-ink">{u.sentence}</span>
                <button
                  onClick={() => resolve(u.id, "mapped")}
                  disabled={busy}
                  className="shrink-0 text-xs font-medium text-primary hover:underline"
                >
                  Covered elsewhere
                </button>
                <button
                  onClick={() => resolve(u.id, "not_a_requirement")}
                  disabled={busy}
                  className="shrink-0 text-xs font-medium text-muted hover:underline"
                >
                  Not a requirement
                </button>
              </li>
            ))}
          </ul>
          {/* An 81-page RFP really does contain ~175 obligations — measured on a live NABARD
              tender, and that is the finding, not a bug. Rendering all of them at once buries
              the table below, so preview and let the user open the rest. Never truncate the
              COUNT: a silently capped list would read as "only 20 outstanding". */}
          {open.length > UNMAPPED_PREVIEW && (
            <button
              onClick={() => setShowAllUnmapped((v) => !v)}
              className="w-full border-t border-hairline p-3 text-sm font-medium text-primary hover:bg-surface-alt"
            >
              {showAllUnmapped
                ? "Show fewer"
                : `Show all ${open.length} sentences (${open.length - UNMAPPED_PREVIEW} more)`}
            </button>
          )}
        </section>
      )}

      <section className="overflow-x-auto rounded-card border border-hairline bg-surface">
        <table className="w-full min-w-[900px] text-sm">
          <thead className="sticky top-0 bg-surface-alt text-left text-xs uppercase tracking-wide text-muted">
            <tr>
              <th className="p-3 font-medium">Requirement</th>
              <th className="p-3 font-medium">Level</th>
              <th className="p-3 font-medium">Source</th>
              <th className="p-3 font-medium">Evidence</th>
              <th className="p-3 font-medium">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-hairline">
            {matrix.rows.map((row) => (
              <tr key={row.id} data-matrix-row className="align-top">
                <td className="p-3 text-ink">
                  {row.requirement_text}
                  {/* No proposal here on purpose: the matrix is the standalone deliverable for
                      teams drafting in Word, so prior answers are shown to read and copy. */}
                  <div className="mt-1">
                    <ReuseSuggestions
                      suggestionsUrl={`/api/tenders/${tenderId}/criteria/${row.criterion_id}/suggestions`}
                      proposalId={null}
                      targetKind="criterion"
                      target={row.criterion_id}
                      label="Prior answers"
                    />
                  </div>
                </td>
                <td className="p-3">
                  <span className={`rounded-full px-2 py-0.5 text-xs ${LEVEL_STYLE[row.requirement_level]}`}>
                    {LEVEL_LABEL[row.requirement_level]}
                  </span>
                </td>
                <td className="p-3 whitespace-nowrap font-mono text-xs text-muted">
                  {/* A-AC3's UI face: a requirement with no traceable source is not auditable. */}
                  {sourceAnchor(
                    row.anchor_page,
                    row.anchor_clause,
                    multiDocument ? row.anchor_document : null,
                  )}
                </td>
                <td className="p-3 text-muted">{row.evidence_required || "—"}</td>
                <td className="p-3">
                  <select
                    value={row.status}
                    disabled={busy}
                    onChange={(e) => setStatus(row.id, e.target.value as Status)}
                    className="rounded-control border border-hairline bg-surface px-2 py-1 text-xs text-ink"
                  >
                    {STATUSES.map((s) => (
                      <option key={s} value={s}>
                        {STATUS_LABEL[s]}
                      </option>
                    ))}
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

/** Generate-or-refresh, as a real button: a plain form POST would navigate the user onto the
 *  raw JSON envelope whenever the gate refuses (TOM not locked, no criteria). */
export function GenerateMatrixButton({ tenderId }: { tenderId: string }) {
  const [error, setError] = useState<string | null>(null);
  const [showAllUnmapped, setShowAllUnmapped] = useState(false);
  const [busy, setBusy] = useState(false);
  const router = useRouter();

  async function generate() {
    setBusy(true);
    setError(null);
    const res = await fetch(`/api/tenders/${tenderId}/matrix`, { method: "POST" });
    const body = await res.json();
    setBusy(false);
    if (!res.ok || !body.ok) {
      setError(body?.error?.message ?? "could not generate the matrix");
      return;
    }
    router.refresh();
  }

  return (
    <div className="mt-4">
      <button
        onClick={generate}
        disabled={busy}
        className="rounded-control bg-primary px-3 py-1.5 text-sm font-medium text-on-primary hover:bg-primary-hover disabled:opacity-50"
      >
        {busy ? "Generating…" : "Generate matrix"}
      </button>
      {error && (
        <p data-matrix-error className="mt-3 text-sm text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
