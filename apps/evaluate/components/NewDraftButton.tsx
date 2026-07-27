"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

/** Minimal start: a title and a category. Everything else is entered in the workspace, where
 *  the rule findings can react to it as it is typed. */
export function NewDraftButton() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [number, setNumber] = useState("");
  const [category, setCategory] = useState("goods");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function create() {
    setBusy(true);
    setError(null);
    const res = await fetch("/api/drafts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: title.trim(),
        tender_number: number.trim() || null,
        category,
      }),
    });
    const b = await res.json();
    setBusy(false);
    if (!b.ok) {
      setError(b.error?.message ?? "Could not start the draft");
      return;
    }
    router.push(`/drafts/${b.data.draft.id}`);
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="rounded bg-primary px-4 py-2 text-sm font-medium text-white"
      >
        New draft
      </button>
    );
  }

  return (
    <div className="w-full max-w-md rounded-card border border-border bg-surface p-card text-left">
      <label className="text-sm font-medium text-ink">
        Tender title
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Supply of Networking Equipment, Zone 3"
          className="mt-1.5 block min-h-11 w-full rounded border border-border bg-surface-alt px-3.5 text-sm text-ink outline-none placeholder:text-muted focus:border-primary focus:bg-surface"
        />
      </label>
      <label className="mt-3 block text-sm font-medium text-ink">
        Tender number (optional)
        <input
          value={number}
          onChange={(e) => setNumber(e.target.value)}
          placeholder="PMC/2026/IT/0091"
          className="mt-1.5 block min-h-11 w-full rounded border border-border bg-surface-alt px-3.5 text-sm text-ink outline-none placeholder:text-muted focus:border-primary focus:bg-surface"
        />
      </label>
      <label className="mt-3 block text-sm font-medium text-ink">
        Category
        <select
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className="mt-1.5 block min-h-11 w-full rounded border border-border bg-surface-alt px-3 text-sm text-ink"
        >
          <option value="goods">Goods</option>
          <option value="works">Works</option>
          <option value="services">Consultancy &amp; other services</option>
        </select>
        <span className="mt-1 block text-xs text-muted">
          Decides which rules apply — works tenders carry checks goods tenders do not.
        </span>
      </label>
      <div className="mt-4 flex gap-2">
        <button
          onClick={create}
          disabled={busy || title.trim().length < 3}
          className="rounded bg-primary px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {busy ? "Starting…" : "Start drafting"}
        </button>
        <button
          onClick={() => setOpen(false)}
          className="rounded border border-border px-4 py-2 text-sm text-ink"
        >
          Cancel
        </button>
      </div>
      {error && <p role="alert" className="mt-2 text-sm text-danger">{error}</p>}
    </div>
  );
}
