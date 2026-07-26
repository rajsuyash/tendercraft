import { createBrowserClient } from "@supabase/ssr";

export const createClient = () =>
  createBrowserClient(
    process.env.NEXT_PUBLIC_EVAL_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_EVAL_SUPABASE_ANON_KEY!,
  );
