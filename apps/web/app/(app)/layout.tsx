import { redirect } from "next/navigation";
import { Suspense } from "react";

import { Sidebar } from "@/components/design/Sidebar";
import {
  WorkspaceSwitcherSkeleton,
  WorkspaceSwitcherSlot,
} from "@/components/design/WorkspaceSwitcherSlot";
import { createClient } from "@/lib/supabase/server";

// Protected shell: C1 sidebar + content. Auth is enforced in middleware; this is the
// defense-in-depth server check (a route should never render for an unauthenticated user).
//
// That check is now the ONLY await on the critical path. The workspace list used to be
// fetched here too — an engine round trip measured at ~0.9s in prod that EVERY navigation
// paid before anything reached the browser, for a switcher most navigations never touch. It
// streams in through Suspense instead, so the shell and the page skeleton paint immediately.
export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  return (
    <div className="flex min-h-screen">
      <Sidebar
        switcher={
          <Suspense fallback={<WorkspaceSwitcherSkeleton />}>
            <WorkspaceSwitcherSlot />
          </Suspense>
        }
      />
      {/* min-w-0: a flex child defaults to min-width:auto, so any wide C2 table inside its own
          overflow-x-auto container still forces THIS element wider than the viewport and the
          whole page scrolls sideways (DESIGN_SPEC §F says it never may). Fixed here rather than
          per page — every dense table on every route inherits the same bug otherwise. */}
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}
