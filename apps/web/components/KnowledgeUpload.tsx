"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

// Add a document to the knowledge base: a file (PDF/DOCX/PPTX) or a website URL.
// Reused on the Library page and inline on the Readiness hub. When criterionId + tenderId are
// passed, the uploaded doc is linked to that specific readiness item.
export function KnowledgeUpload({
  compact = false,
  criterionId,
  tenderId,
}: {
  compact?: boolean;
  criterionId?: string;
  tenderId?: string;
}) {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  async function send(body: FormData) {
    if (criterionId && tenderId) {
      body.append("criterion_id", criterionId);
      body.append("tender_id", tenderId);
    }
    setBusy(true);
    setMsg(null);
    const res = await fetch("/api/knowledge/ingest", { method: "POST", body });
    const data = await res.json().catch(() => null);
    if (res.ok) {
      setMsg({ ok: true, text: `Added "${data.data.name}" (${data.data.doc_type}).` });
      setUrl("");
      router.refresh();
    } else {
      setMsg({ ok: false, text: data?.error?.message ?? "Ingest failed" });
    }
    setBusy(false);
  }

  function onFile(file: File) {
    const fd = new FormData();
    fd.append("file", file);
    void send(fd);
  }
  function onUrl() {
    if (!url.trim()) return;
    const fd = new FormData();
    fd.append("url", url.trim());
    void send(fd);
  }

  return (
    <div data-kb-upload className={compact ? "" : "rounded-card border border-border bg-surface p-card"}>
      {!compact && (
        <h2 className="mb-3 font-heading text-sm font-semibold text-ink">Add to knowledge base</h2>
      )}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <label className="inline-flex cursor-pointer items-center rounded border border-primary px-3 py-1.5 text-sm font-medium text-primary hover:bg-primary-tint">
          <input
            type="file"
            accept=".pdf,.docx,.pptx,.txt"
            className="hidden"
            disabled={busy}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) onFile(f);
            }}
          />
          {busy ? "Uploading…" : "Upload file (PDF / DOCX / PPTX)"}
        </label>
        <span className="text-xs text-muted">or</span>
        <div className="flex flex-1 gap-2">
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://your-company.com/about"
            className="flex-1 rounded border border-border px-3 py-1.5 text-sm outline-none focus:border-primary"
          />
          <button
            onClick={onUrl}
            disabled={busy || !url.trim()}
            className="rounded bg-primary px-3 py-1.5 text-sm font-medium text-on-primary hover:bg-primary-hover disabled:opacity-50"
          >
            Fetch
          </button>
        </div>
      </div>
      {msg && (
        <p className={`mt-2 text-xs ${msg.ok ? "text-success" : "text-danger"}`}>{msg.text}</p>
      )}
    </div>
  );
}
