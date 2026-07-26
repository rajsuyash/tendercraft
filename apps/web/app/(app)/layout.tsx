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
      <div className="flex-1">{children}</div>
    </div>
  );
}
