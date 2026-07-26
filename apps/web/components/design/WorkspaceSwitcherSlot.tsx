import { WorkspaceSwitcher, type WorkspaceOption } from "./WorkspaceSwitcher";

import { engineFetch } from "@/lib/engine";

/** Placeholder shown while the workspace list resolves — the sidebar's own loading state. */
export function WorkspaceSwitcherSkeleton() {
  return (
    <div
      data-workspace-switcher-loading
      aria-hidden
      className="mb-4 h-[52px] animate-pulse rounded bg-surface-alt"
    />
  );
}

/**
 * Resolves which workspaces this person can reach and which one they are scoped to.
 *
 * A SET is correct here — this is the switcher; every data query stays on the active one.
 *
 * Split out of the layout so it can sit behind Suspense: this call measured ~0.9s in prod and
 * was blocking first paint on EVERY navigation, for a list that most navigations never touch.
 */
export async function WorkspaceSwitcherSlot() {
  // Degrade, never throw. A `fetch` to an unreachable engine REJECTS rather than returning a
  // non-ok response, and an uncaught throw here escapes the Suspense boundary and takes the
  // whole route to the error boundary — the sidebar killing the page it decorates. Every
  // screen still works without the switcher; none works without itself.
  try {
    const res = await engineFetch("/api/workspaces");
    if (!res.ok) return <WorkspaceSwitcher workspaces={[]} activeId={null} />;

    const body = await res.json();
    if (!body.ok) return <WorkspaceSwitcher workspaces={[]} activeId={null} />;

    return (
      <WorkspaceSwitcher
        workspaces={body.data.workspaces as WorkspaceOption[]}
        activeId={body.data.active_workspace_id as string | null}
        canCreate={Boolean(body.data.is_org_admin)}
      />
    );
  } catch {
    return <WorkspaceSwitcher workspaces={[]} activeId={null} />;
  }
}
