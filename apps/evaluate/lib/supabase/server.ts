import { createServerClient, type CookieOptions } from "@supabase/ssr";
import { cookies } from "next/headers";

type CookieToSet = { name: string; value: string; options: CookieOptions };

/** Server client bound to request cookies. Points at the EVALUATE project — never the bidder's. */
export async function createClient() {
  const cookieStore = await cookies();
  return createServerClient(
    process.env.NEXT_PUBLIC_EVAL_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_EVAL_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll: () => cookieStore.getAll(),
        setAll(list: CookieToSet[]) {
          try {
            list.forEach(({ name, value, options }) => cookieStore.set(name, value, options));
          } catch {
            // Server Component — middleware refreshes the session.
          }
        },
      },
    },
  );
}
