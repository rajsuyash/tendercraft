import { redirect } from "next/navigation";

import { Sidebar } from "@/components/design/Sidebar";
import { createClient } from "@/lib/supabase/server";

// Protected shell: C1 sidebar + content. Auth is enforced in middleware; this is the
// defense-in-depth server check (a route should never render for an unauthenticated user).
export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex-1">{children}</div>
    </div>
  );
}
