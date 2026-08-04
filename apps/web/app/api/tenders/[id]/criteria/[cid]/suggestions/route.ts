import { passthrough } from "@/lib/proxy";

export async function GET(
  req: Request,
  { params }: { params: Promise<{ id: string; cid: string }> },
) {
  const { id, cid } = await params;
  return passthrough(req, `/api/tenders/${id}/criteria/${cid}/suggestions`);
}
