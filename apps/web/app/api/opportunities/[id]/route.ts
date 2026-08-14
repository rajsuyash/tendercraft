import { passthrough } from "@/lib/proxy";

// Routing a swept tender: assign an owner, or star it. The engine validates that the assignee
// is a member of this workspace, so this handler adds nothing but the hop.
type Ctx = { params: Promise<{ id: string }> };

export async function PATCH(req: Request, { params }: Ctx) {
  const { id } = await params;
  return passthrough(req, `/api/opportunities/${id}`);
}
