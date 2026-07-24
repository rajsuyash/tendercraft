import { createClient } from "@/lib/supabase/server";

/**
 * Server-side proxy to the FastAPI engine, forwarding the user's Supabase access token.
 * Deterministic operations (lock, ingest) live in the engine; the web never re-implements them.
 */
export async function engineFetch(path: string, init?: RequestInit): Promise<Response> {
  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session) {
    return new Response(JSON.stringify({ ok: false, error: { code: "NO_SESSION", message: "not signed in" } }), {
      status: 401,
    });
  }
  return fetch(`${process.env.ENGINE_URL}${path}`, {
    ...init,
    headers: { ...init?.headers, Authorization: `Bearer ${session.access_token}` },
    cache: "no-store",
  });
}
