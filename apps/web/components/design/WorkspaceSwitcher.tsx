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
}: {
  workspaces: WorkspaceOption[];
  activeId: string | null;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const active = workspaces.find((w) => w.id === activeId) ?? workspaces[0];
  const canSwitch = workspaces.length > 1;

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

  if (!active) return null;

  return (
    <div className="relative mb-4" data-workspace-switcher>
      <button
        type="button"
        disabled={!canSwitch || busy}
        onClick={() => setOpen((v) => !v)}
        data-active-workspace={active.id}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-2 rounded border border-border bg-surface-alt px-2.5 py-2 text-left hover:border-primary disabled:cursor-default"
      >
        <span className="min-w-0">
          <span className="block font-mono text-[10px] uppercase tracking-wider text-muted">
            Workspace
          </span>
          <span className="block truncate text-sm font-medium text-ink">
            {active.name ?? "Untitled"}
          </span>
        </span>
        {canSwitch ? (
          <span aria-hidden className="shrink-0 text-xs text-muted">
            {open ? "▲" : "▼"}
          </span>
        ) : null}
      </button>

      {open && canSwitch ? (
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
                <span className="shrink-0 font-mono text-[10px] uppercase text-muted">
                  {w.role}
                </span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
