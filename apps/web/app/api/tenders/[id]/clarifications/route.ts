import { passthrough } from "@/lib/proxy";

// Persisting the derived pre-bid pack (UML ask 2). Deliberately a POST the user presses: the GET
// that derives these questions is side-effect-free and is read server-side by the page, so
// saving is the point at which a derived list becomes a record someone is accountable for.
export async function POST(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return passthrough(req, `/api/tenders/${id}/clarifications`);
}
