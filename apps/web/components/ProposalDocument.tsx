"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { ReuseSuggestions } from "./ReuseSuggestions";
import { StageProgress } from "./StageProgress";
import { useState } from "react";

export type DocSection = {
  edited_at?: string | null;
  key: string;
  heading: string;
  kind: string;
  status: string;
  body_md: string;
  word_count: number;
  flags: { text: string; reason: string }[] | null;
  approved_at: string | null;
};

const STATUS: Record<string, { label: string; cls: string }> = {
  drafted: { label: "Drafted", cls: "bg-success-bg text-success" },
  unverified: { label: "Unverified claims", cls: "bg-warning-bg text-warning" },
  placeholder: { label: "Placeholder", cls: "bg-danger-bg text-danger" },
};

/** Minimal markdown renderer for the subset the engine emits: "### " headings, "| " tables,
 *  "- " bullets, paragraphs. A full parser would be a dependency bought for nothing. */
function Body({ md }: { md: string }) {
  const blocks: React.ReactNode[] = [];
  const lines = md.split("\n");
  let table: string[] = [];

  const flushTable = (k: number) => {
    if (!table.length) return;
    const rows = table
      .filter((l) => !/^\|[\s\-|]+\|$/.test(l.trim()))
      .map((l) => l.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim()));
    table = [];
    const header = rows[0];
    if (!header) return;
    blocks.push(
      <div key={`t${k}`} className="my-3 overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="bg-surface-alt">
              {header.map((c, i) => (
                <th key={i} className="border border-border px-3 py-2 text-left font-medium">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.slice(1).map((r, i) => (
              <tr key={i}>
                {r.map((c, j) => (
                  <td key={j} className="border border-border px-3 py-2 text-ink">
                    {c}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>,
    );
  };

  lines.forEach((raw, k) => {
    const line = raw.trimEnd();
    if (line.trimStart().startsWith("|")) {
      table.push(line);
      return;
    }
    flushTable(k);
    if (!line.trim()) return;
    if (line.startsWith("### ")) {
      blocks.push(
        <h3 key={k} className="mt-4 font-heading text-base font-medium text-ink">
          {line.slice(4)}
        </h3>,
      );
    } else if (line.startsWith("- ")) {
      blocks.push(
        <li key={k} className="ml-5 list-disc text-sm leading-relaxed text-ink">
          {line.slice(2)}
        </li>,
      );
    } else {
      blocks.push(
        <p key={k} className="mt-2 text-sm leading-relaxed text-ink">
          {line.replace(/\*\*(.+?)\*\*/g, "$1").replace(/(?<!\w)_(.+?)_(?!\w)/g, "$1")}
        </p>,
      );
    }
  });
  flushTable(lines.length);
  return <>{blocks}</>;
}

export type ExportDecision = {
  exportable: boolean;
  hard_blockers: string[];
  override_blockers: string[];
};

/** Why this document has the sections it has.
 *
 *  A fixed seventeen-section IT-services packet used to be applied to every tender, wire-rope
 *  supply bids included. The catalogue is now a menu the tender chooses from, and every
 *  choice names the row behind it — so a section the user did not expect is answerable
 *  rather than arbitrary, and one they expected and did not get says which signal was
 *  missing instead of silently not being there. */
export interface Outline {
  source: string;
  derived_at: string;
  signals: Record<string, string>;
  sections: { key: string; heading: string; order: number; because: string }[];
  /** `heading` and `because` are what a person reads; `key` and `missing` are the machine's
   *  names for the same thing and must not reach the screen — a user-facing list rendering
   *  `team_composition` is showing someone a database identifier. */
  absent: { key: string; heading?: string; missing: string; because?: string }[];
}

export function ProposalDocument({
  tenderId,
  proposalId,
  tenderTitle,
  sections,
  outline = null,
  totalWords,
  exportDecision = null,
}: {
  tenderId: string;
  proposalId: string | null;
  tenderTitle: string;
  sections: DocSection[];
  /** `null` on a proposal generated before outlines existed: it keeps every section it has
   *  and behaves exactly as it did. */
  outline?: Outline | null;
  totalWords: number;
  /** The engine's own export decision. `null` when it could not be read, which is treated
   *  as a shut gate — see the note beside `canDownload`. */
  exportDecision?: ExportDecision | null;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");

  async function saveEdit(key: string) {
    if (!proposalId) return;
    setBusy(key);
    setError(null);
    try {
      const res = await fetch(`/api/proposals/${proposalId}/sections/${key}`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ body_md: draft }),
      });
      const body = await res.json();
      if (!body.ok) {
        setError(body.error?.message ?? "Could not save");
        return;
      }
      setEditing(null);
      router.refresh();
    } finally {
      setBusy(null);
    }
  }

  const unapproved = sections.filter((s) => s.kind === "narrative" && !s.approved_at);
  const because = new Map((outline?.sections ?? []).map((e) => [e.key, e.because]));
  // The SERVER's decision, not a local guess at it. Approving every narrative section is a
  // strict subset of the export rule — which also enforces the approval chain, segregation
  // of duties, open placeholders, mandatory-row statuses and the non-overridable financial
  // gate — so this link used to go live while the endpoint returned 409, ejecting the user
  // onto a raw JSON envelope of UUIDs and AC codes. `null` means the decision could not be
  // read, and an unknown gate is treated as shut.
  const canDownload = exportDecision?.exportable === true;
  const downloadBlockers = exportDecision
    ? [...exportDecision.hard_blockers, ...exportDecision.override_blockers]
    : [];

  async function post(path: string, label: string) {
    setBusy(label);
    setError(null);
    try {
      const res = await fetch(path, { method: "POST" });
      const body = await res.json();
      if (!body.ok) setError(body.error?.message ?? "Request failed");
      else router.refresh();
    } finally {
      setBusy(null);
    }
  }

  if (!sections.length) {
    return (
      <main className="mx-auto max-w-4xl p-page">
      <div className="rounded-card border border-border bg-surface p-8 text-center">
        <p className="font-heading text-lg text-ink">No proposal document yet</p>
        <p className="mt-2 text-sm text-muted">
          Generate the full technical bid — MeitY Appendix-I form structure, assembled from
          your profile and content library.
        </p>
        <button
          type="button"
          data-generate-document
          onClick={() => post(`/api/tenders/${tenderId}/sections/generate`, "gen")}
          disabled={busy !== null}
          className="mt-4 rounded bg-primary px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {busy ? "Drafting…" : "Generate proposal document"}
        </button>
        {busy ? (
          <div className="mx-auto mt-5 max-w-md text-left">
            <StageProgress
              stages={[
                "Assembling your compliance tables",
                "Drafting the solution and methodology",
                "Drafting quality, training and support",
                "Drafting risk and the covering letter",
                "Checking every claim against your evidence",
              ]}
              note="17 sections, usually about 2 minutes"
            />
          </div>
        ) : null}
        {error ? <p className="mt-3 text-sm text-danger">{error}</p> : null}
      </div>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-4xl space-y-4 p-page">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-card border border-border bg-surface p-card">
        <div>
          <h1 className="font-heading text-xl font-medium text-ink">{tenderTitle}</h1>
          <p className="mt-1 text-sm text-muted">
            <span data-total-words>{totalWords.toLocaleString("en-IN")}</span> words ·{" "}
            {sections.length} sections ·{" "}
            {unapproved.length === 0 ? (
              <span className="text-success">all sections approved</span>
            ) : (
              <span className="text-warning">
                {unapproved.length} awaiting approval — export blocked
              </span>
            )}
          </p>
          {outline && (
            <details data-outline className="mt-2 text-xs text-muted">
              <summary className="cursor-pointer">
                Why these {outline.sections.length} sections
                {outline.absent.length > 0
                  ? `, and what the tender did not ask for (${outline.absent.length})`
                  : ""}
              </summary>
              <ul className="mt-2 space-y-1">
                {outline.sections.map((e) => (
                  <li key={e.key}>
                    <span className="text-ink">{e.heading}</span>
                    {" — "}
                    {e.because || "in every proposal"}
                  </li>
                ))}
              </ul>
              {outline.absent.length > 0 && (
                <ul className="mt-2 space-y-1">
                  {outline.absent.map((a) => (
                    <li key={a.key} data-outline-absent>
                      <span className="line-through">{a.heading ?? a.key}</span>
                      {" — not included because "}
                      {a.because ?? `this tender raises no ${a.missing} signal`}
                    </li>
                  ))}
                </ul>
              )}
            </details>
          )}
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => post(`/api/tenders/${tenderId}/sections/generate`, "gen")}
            disabled={busy !== null}
            className="rounded border border-border px-3 py-2 text-sm text-ink disabled:opacity-50"
          >
            {busy === "gen" ? "Drafting…" : "Regenerate"}
          </button>
          <Link
            href={`/proposals/${tenderId}/score`}
            data-open-score
            className="rounded border border-border px-3 py-2 text-sm text-ink hover:border-primary"
          >
            Technical score
          </Link>
          <Link
            href={`/proposals/${tenderId}/export`}
            data-open-export
            className="rounded border border-border px-3 py-2 text-sm text-ink hover:border-primary"
          >
            Compliance &amp; export
          </Link>
          {canDownload ? (
            <a
              href={`/api/tenders/${tenderId}/export/docx`}
              data-download-docx
              className="rounded bg-primary px-3 py-2 text-sm font-medium text-white"
            >
              Download .docx
            </a>
          ) : (
            // Never a live primary link while the gate is shut.
            <span
              data-download-blocked
              data-blocker-count={downloadBlockers.length}
              title={
                downloadBlockers.length
                  ? downloadBlockers.join("\n")
                  : "The export gate has not been read — open Compliance & export."
              }
              className="cursor-not-allowed rounded bg-surface-alt px-3 py-2 text-sm font-medium text-muted"
            >
              Download .docx —{" "}
              {downloadBlockers.length
                ? `${downloadBlockers.length} to resolve`
                : "gate not read"}
            </span>
          )}
        </div>
      </div>

      {error ? (
        <p className="rounded-card border border-danger bg-danger-bg p-3 text-sm text-danger">
          {error}
        </p>
      ) : null}

      {sections.map((s) => {
        const st = STATUS[s.status] ?? { label: "Drafted", cls: "bg-success-bg text-success" };
        return (
          <section
            key={s.key}
            data-section={s.key}
            data-section-status={s.status}
            className="rounded-card border border-border bg-surface p-card"
          >
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <h2 className="font-heading text-lg font-medium text-ink">{s.heading}</h2>
                {because.get(s.key) && (
                  <p data-section-because className="mt-0.5 text-xs text-muted">
                    Included because of {because.get(s.key)}
                  </p>
                )}
              </div>
              <div className="flex items-center gap-2">
                <span className={`rounded px-2 py-0.5 text-2xs font-semibold uppercase ${st.cls}`}>
                  {st.label}
                </span>
                {s.edited_at ? (
                  <span
                    data-edited
                    className="rounded bg-primary/10 px-2 py-0.5 text-2xs font-semibold uppercase tracking-wide text-primary"
                  >
                    Your edit
                  </span>
                ) : s.kind === "narrative" && !s.approved_at ? (
                  <span
                    data-ai-watermark
                    className="rounded bg-warning-bg px-2 py-0.5 text-2xs font-semibold uppercase tracking-wide text-warning"
                  >
                    AI Draft
                  </span>
                ) : null}
              </div>
            </div>
            <p className="mt-1 text-xs text-muted">{s.word_count} words</p>

            <div className="mt-3">
              {editing === s.key ? (
                <div>
                  <textarea
                    data-edit-body={s.key}
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    rows={Math.min(30, Math.max(8, draft.split("\n").length + 2))}
                    className="w-full rounded border border-border bg-surface p-3 font-mono text-xs leading-relaxed text-ink focus:border-primary focus:outline-none"
                  />
                  <p className="mt-1 text-xs text-muted">
                    Markdown: <code>### </code> for a sub-heading, <code>| a | b |</code> for
                    a table. Saving clears this section&rsquo;s approval — it will need
                    signing off again.
                  </p>
                  <div className="mt-2 flex gap-2">
                    <button
                      type="button"
                      data-save-edit={s.key}
                      disabled={busy !== null}
                      onClick={() => saveEdit(s.key)}
                      className="rounded bg-primary px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"
                    >
                      {busy === s.key ? "Saving…" : "Save"}
                    </button>
                    <button
                      type="button"
                      onClick={() => setEditing(null)}
                      className="rounded border border-border px-3 py-1.5 text-xs text-muted"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <Body md={s.body_md} />
              )}
            </div>

            {(s.flags ?? []).length > 0 ? (
              <ul className="mt-3 space-y-1 rounded border border-warning bg-warning-bg p-3">
                {(s.flags ?? []).map((f, i) => (
                  <li key={i} data-flag={f.reason} className="text-xs text-warning">
                    <strong className="uppercase">{f.reason.replace("_", " ")}</strong> — {f.text}
                  </li>
                ))}
              </ul>
            ) : null}

            {proposalId && s.kind === "narrative" ? (
              <div className="mt-3">
                <ReuseSuggestions
                  suggestionsUrl={`/api/proposals/${proposalId}/sections/${s.key}/suggestions`}
                  proposalId={proposalId}
                  targetKind="section"
                  target={s.key}
                />
              </div>
            ) : null}

            {proposalId && editing !== s.key ? (
              <div className="mt-3">
                <button
                  type="button"
                  data-edit-section={s.key}
                  onClick={() => {
                    setDraft(s.body_md ?? "");
                    setEditing(s.key);
                  }}
                  className="text-xs font-medium text-primary underline"
                >
                  Edit this section
                </button>
              </div>
            ) : null}

            {s.kind === "narrative" && proposalId ? (
              <div className="mt-3 border-t border-border pt-3">
                {s.approved_at ? (
                  <p className="text-xs text-success">
                    Approved {new Date(s.approved_at).toLocaleDateString("en-IN")}
                  </p>
                ) : (
                  <button
                    type="button"
                    data-approve-section={s.key}
                    onClick={() =>
                      post(`/api/proposals/${proposalId}/sections/${s.key}/approve`, s.key)
                    }
                    disabled={busy !== null}
                    className="rounded border border-primary px-3 py-1.5 text-xs font-medium text-primary disabled:opacity-50"
                  >
                    {busy === s.key ? "Approving…" : "Approve this section"}
                  </button>
                )}
              </div>
            ) : null}
          </section>
        );
      })}
    </main>
  );
}
