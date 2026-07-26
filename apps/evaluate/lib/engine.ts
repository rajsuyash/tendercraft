import { createClient } from "@/lib/supabase/server";

/** Server-side proxy to the evaluate engine, forwarding the user's JWT.
 *  The engine derives the authority from that token — never from anything we send. */
export async function engineFetch(path: string, init?: RequestInit): Promise<Response> {
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) {
    return new Response(
      JSON.stringify({ ok: false, data: null, error: { code: "NO_SESSION", message: "not signed in" } }),
      { status: 401 },
    );
  }
  return fetch(`${process.env.EVAL_ENGINE_URL}${path}`, {
    ...init,
    headers: { ...init?.headers, Authorization: `Bearer ${session.access_token}` },
    cache: "no-store",
  });
}

export async function engineJson<T>(path: string): Promise<{ ok: boolean; data: T | null; code?: string; message?: string }> {
  const res = await engineFetch(path);
  const body = await res.json().catch(() => null);
  if (!body) return { ok: false, data: null, code: "BAD_RESPONSE" };
  return { ok: body.ok, data: body.data, code: body.error?.code, message: body.error?.message };
}
