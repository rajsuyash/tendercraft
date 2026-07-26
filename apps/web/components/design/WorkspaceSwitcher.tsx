"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export type WorkspaceOption = { id: string; name: string | null; role: string };

/** Workspace identity + switcher, at the top of the sidebar.
 *
 * A consultancy runs one workspace per client engagement, so "which client am I looking
 * at" is the single most important piece of context on every screen — and without this it
 * appeared nowhere in the UI at all.
 */
export function WorkspaceSwitcher({
  workspaces,
  activeId,
  canCreate = false,
}: {
  workspaces: WorkspaceOption[];
  activeId: string | null;
  canCreate?: boolean;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const active = workspaces.find((w) => w.id === activeId) ?? workspaces[0];
  // The menu is worth opening if you can switch OR create.
  const canOpen = workspaces.length > 1 || canCreate;

  async function switchTo(id: string) {
    setBusy(true);
    try {
      const res = await fetch(`/api/me/workspace/${id}`, { method: "PUT" });
      if ((await res.json()).ok) {
        setOpen(false);
        // Refresh rather than push: every server component re-renders under the new scope.
        router.refresh();
      }
    } finally {
      setBusy(false);
    }
  }

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/workspaces", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ name }),
      });
      const body = await res.json();
      if (!body.ok) {
        setError(body.error?.message ?? "Could not create workspace");
        return;
      }
      // The engine makes the creator an admin and switches them into it.
      setCreating(false);
      setOpen(false);
      setName("");
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  if (!active) return null;

  return (
    <div className="relative mb-4" data-workspace-switcher>
      <button
        type="button"
        disabled={!canOpen || busy}
        onClick={() => setOpen((v) => !v)}
        data-active-workspace={active.id}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-2 rounded border border-border bg-surface-alt px-2.5 py-2 text-left hover:border-primary disabled:cursor-default"
      >
        <span className="min-w-0">
          <span className="block font-mono text-2xs uppercase tracking-wider text-muted">
            Workspace
          </span>
          <span className="block truncate text-sm font-medium text-ink">
            {active.name ?? "Untitled"}
          </span>
        </span>
        {canOpen ? (
          <span aria-hidden className="shrink-0 text-xs text-muted">
            {open ? "▲" : "▼"}
          </span>
        ) : null}
      </button>

      {open && canOpen ? (
        <ul className="absolute z-20 mt-1 w-full overflow-hidden rounded border border-border bg-surface shadow-lg">
          {workspaces.map((w) => (
            <li key={w.id}>
              <button
                type="button"
                disabled={busy}
                data-switch-workspace={w.id}
                onClick={() => switchTo(w.id)}
                className={`flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm hover:bg-surface-alt disabled:opacity-50 ${
                  w.id === active.id ? "text-primary" : "text-ink"
                }`}
              >
                <span className="truncate">{w.name ?? "Untitled"}</span>
                <span className="shrink-0 font-mono text-2xs uppercase text-muted">
                  {w.role}
                </span>
              </button>
            </li>
          ))}
          {canCreate ? (
            <li className="border-t border-border">
              {creating ? (
                <form onSubmit={create} className="p-2">
                  <input
                    autoFocus
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Client or engagement name"
                    data-new-workspace-name
                    className="w-full rounded border border-border bg-surface px-2 py-1.5 text-sm"
                  />
                  {error ? <p className="mt-1 text-xs text-danger">{error}</p> : null}
                  <div className="mt-2 flex gap-1.5">
                    <button
                      type="submit"
                      disabled={busy || name.trim().length < 2}
                      data-create-workspace-submit
                      className="rounded bg-primary px-2.5 py-1 text-xs font-medium text-white disabled:opacity-50"
                    >
                      {busy ? "Creating…" : "Create"}
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setCreating(false);
                        setError(null);
                      }}
                      className="rounded border border-border px-2.5 py-1 text-xs text-muted"
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              ) : (
                <button
                  type="button"
                  onClick={() => setCreating(true)}
                  data-new-workspace
                  className="w-full px-3 py-2 text-left text-sm font-medium text-primary hover:bg-surface-alt"
                >
                  + New workspace
                </button>
              )}
            </li>
          ) : null}
        </ul>
      ) : null}
    </div>
  );
}
