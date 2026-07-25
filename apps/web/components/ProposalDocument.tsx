"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export type DocSection = {
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

export function ProposalDocument({
  tenderId,
  proposalId,
  tenderTitle,
  sections,
  totalWords,
}: {
  tenderId: string;
  proposalId: string | null;
  tenderTitle: string;
  sections: DocSection[];
  totalWords: number;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const unapproved = sections.filter((s) => s.kind === "narrative" && !s.approved_at);

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
          <a
            href={`/api/tenders/${tenderId}/export/docx`}
            data-download-docx
            className="rounded bg-primary px-3 py-2 text-sm font-medium text-white"
          >
            Download .docx
          </a>
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
              <h2 className="font-heading text-lg font-medium text-ink">{s.heading}</h2>
              <div className="flex items-center gap-2">
                <span className={`rounded px-2 py-0.5 text-[10px] font-semibold uppercase ${st.cls}`}>
                  {st.label}
                </span>
                {s.kind === "narrative" && !s.approved_at ? (
                  <span
                    data-ai-watermark
                    className="rounded bg-warning-bg px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-warning"
                  >
                    AI Draft
                  </span>
                ) : null}
              </div>
            </div>
            <p className="mt-1 text-xs text-muted">{s.word_count} words</p>

            <div className="mt-3">
              <Body md={s.body_md} />
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
