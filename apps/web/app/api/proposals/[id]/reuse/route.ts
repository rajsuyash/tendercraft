import { passthrough } from "@/lib/proxy";

// The only path that puts a prior answer into a draft (G-AC6) — it writes a usage receipt.
export async function POST(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return passthrough(req, `/api/proposals/${id}/reuse`);
}
