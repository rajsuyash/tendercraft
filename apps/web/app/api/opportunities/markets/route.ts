/**
 * Which countries feed this workspace's opportunity list.
 *
 * A PUT rather than a PATCH: the watched set is replaced wholesale, and a partial update of a
 * scope is how a country ends up silently dropped. The engine re-runs the match computation
 * before returning, so narrowing takes effect on the next render rather than on the next sweep.
 */
import { engineFetch } from "@/lib/engine";

export const dynamic = "force-dynamic";
// Changing the set re-scopes and re-ranks the whole corpus for this workspace.
export const maxDuration = 300;

export async function PUT(request: Request) {
  const res = await engineFetch("/api/opportunities/markets", {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(await request.json()),
  });
  return new Response(await res.text(), {
    status: res.status,
    headers: { "content-type": "application/json" },
  });
}
