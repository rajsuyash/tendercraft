import { passthrough } from "@/lib/proxy";

// Claiming an opportunity from the feed. The engine checks that the opportunity is in this
// workspace's feed and makes the write idempotent on (workspace_id, opportunity_id), so this
// handler adds nothing but the hop.
type Ctx = { params: Promise<{ id: string }> };

export async function POST(req: Request, { params }: Ctx) {
  const { id } = await params;
  return passthrough(req, `/api/opportunities/${id}/pursue`);
}
