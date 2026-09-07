import { passthrough } from "@/lib/proxy";

// The pursuit's context for the upload screen: reference, authority, closing date and the
// portal's own document links. Read from the row rather than carried in the URL, so a tender
// reference the user sees as authoritative cannot be edited into the address bar.
type Ctx = { params: Promise<{ id: string }> };

export async function GET(req: Request, { params }: Ctx) {
  const { id } = await params;
  return passthrough(req, `/api/pursuits/${id}`);
}
