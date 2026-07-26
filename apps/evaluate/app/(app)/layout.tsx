import { redirect } from "next/navigation";
import Link from "next/link";

import { engineJson } from "@/lib/engine";
import { createClient } from "@/lib/supabase/server";

type Me = { authority_name: string | null; role: string };

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const me = await engineJson<Me>("/api/me");
  const authority = me.data?.authority_name ?? "Authority";
  const role = me.data?.role ?? "";

  return (
    <div className="min-h-screen">
      <header className="chrome-material sticky top-0 z-10 border-b border-border">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-page py-3">
          <Link href="/evaluations" className="flex items-center gap-2.5">
            <span className="grid h-8 w-8 place-items-center rounded bg-primary text-xs font-bold text-on-primary shadow-sm">
              TE
            </span>
            <span className="font-heading text-base font-semibold tracking-[-0.01em] text-ink">
              TenderCraft Evaluate
            </span>
          </Link>
          <div className="text-right">
            <p className="text-sm font-medium text-ink">{authority}</p>
            <p className="text-xs capitalize text-muted">{role.replace("_", " ")}</p>
          </div>
        </div>
      </header>
      {children}
    </div>
  );
}
