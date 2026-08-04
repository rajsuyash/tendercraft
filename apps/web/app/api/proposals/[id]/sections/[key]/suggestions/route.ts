import { passthrough } from "@/lib/proxy";

export async function GET(
  req: Request,
  { params }: { params: Promise<{ id: string; key: string }> },
) {
  const { id, key } = await params;
  return passthrough(req, `/api/proposals/${id}/sections/${key}/suggestions`);
}
