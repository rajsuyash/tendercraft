/**
 * The opt-in narrow feed.
 *
 * This handler did not exist: `OpportunityFeed` has been POSTing to it since the toggle was
 * built, so every click 404'd and surfaced as "Could not change the feed" — a control that
 * looked implemented and was not. Reachable only from the feed's own checkbox, which is why
 * nothing else caught it.
 */
import { engineFetch } from "@/lib/engine";

export const dynamic = "force-dynamic";
export const maxDuration = 300;

export async function POST(request: Request) {
  const on = new URL(request.url).searchParams.get("on") === "true";
  const res = await engineFetch(`/api/opportunities/keyword-gate?on=${on}`, { method: "POST" });
  return new Response(await res.text(), {
    status: res.status,
    headers: { "content-type": "application/json" },
  });
}
