import { passthrough } from "@/lib/proxy";

// Reading the specifications out of a schedule's descriptions — the one model call in Module H,
// and the reason it is a POST the user presses rather than something the fit screen does on load.
export const maxDuration = 300;

export async function POST(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  // Forward `?force=1` verbatim — the engine's double-spend guard reads it, not this route.
  const qs = new URL(req.url).search;
  return passthrough(req, `/api/tenders/${id}/schedule/extract${qs}`);
}
