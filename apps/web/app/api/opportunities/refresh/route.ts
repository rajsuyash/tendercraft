/**
 * Thin BFF for the feed refresh. Mutations go through a route handler rather than a server
 * action so there is one auditable mutation path (docs/conventions.md).
 *
 * The sweep is slow on purpose: the connector honours a one-request-per-second cap against a
 * government portal, so a wide refresh takes tens of seconds. That is the rate discipline
 * working, not a hang.
 */
import { engineFetch } from "@/lib/engine";

export const dynamic = "force-dynamic";
export const maxDuration = 300;

export async function POST(request: Request) {
  const url = new URL(request.url);
  const maxPages = url.searchParams.get("max_pages") ?? "8";

  const res = await engineFetch(`/api/opportunities/refresh?max_pages=${maxPages}`, {
    method: "POST",
  });
  const body = await res.text();
  return new Response(body, {
    status: res.status,
    headers: { "content-type": "application/json" },
  });
}
