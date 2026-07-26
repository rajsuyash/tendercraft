import { redirect } from "next/navigation";

import { Sidebar } from "@/components/design/Sidebar";
import type { WorkspaceOption } from "@/components/design/WorkspaceSwitcher";
import { engineFetch } from "@/lib/engine";
import { createClient } from "@/lib/supabase/server";

// Protected shell: C1 sidebar + content. Auth is enforced in middleware; this is the
// defense-in-depth server check (a route should never render for an unauthenticated user).
export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  // Which workspaces this person can reach, and which one they are currently scoped to.
  // A SET is correct here — this is the switcher; every data query stays on the active one.
  let workspaces: WorkspaceOption[] = [];
  let activeWorkspaceId: string | null = null;
  const res = await engineFetch("/api/workspaces");
  if (res.ok) {
    const body = await res.json();
    if (body.ok) {
      workspaces = body.data.workspaces as WorkspaceOption[];
      activeWorkspaceId = body.data.active_workspace_id as string | null;
    }
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar workspaces={workspaces} activeWorkspaceId={activeWorkspaceId} />
      <div className="flex-1">{children}</div>
    </div>
  );
}
