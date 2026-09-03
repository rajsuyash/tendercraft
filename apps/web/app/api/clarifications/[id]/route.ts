import { passthrough } from "@/lib/proxy";

// Recording what the bidder did with a question and what the buyer said back. We never post to
// GeM (G-1/G-8) — `status: "sent"` is the bidder telling us they raised it on the portal.
export async function PATCH(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return passthrough(req, `/api/clarifications/${id}`);
}
