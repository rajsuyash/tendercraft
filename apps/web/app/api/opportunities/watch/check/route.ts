/**
 * Thin BFF for the watched-bid stage check (UML ask 4).
 *
 * Slow on purpose, like the sweep: up to three portal requests per watched bid, each behind
 * the connector's one-per-second cap against a government site. That is the rate discipline
 * working, not a hang — hence the extended duration.
 */
import { engineFetch } from "@/lib/engine";

export const dynamic = "force-dynamic";
export const maxDuration = 300;

export async function POST(request: Request) {
  const limit = new URL(request.url).searchParams.get("limit") ?? "25";
  const res = await engineFetch(`/api/opportunities/watch/check?limit=${limit}`, {
    method: "POST",
  });
  const body = await res.text();
  return new Response(body, {
    status: res.status,
    headers: { "content-type": "application/json" },
  });
}
