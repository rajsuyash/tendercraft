import { redirect } from "next/navigation";

import { Sidebar } from "@/components/design/Sidebar";
import { getMe } from "@/lib/engine";
import { createClient } from "@/lib/supabase/server";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  // One engine call, deduped by React cache() so a nested layout or page asking for the same
  // thing inside this render pass does not repeat it.
  const me = await getMe();

  return (
    <div className="flex min-h-screen">
      <Sidebar authority={me.data?.authority_name ?? "Authority"} role={me.data?.role ?? ""} />
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}
