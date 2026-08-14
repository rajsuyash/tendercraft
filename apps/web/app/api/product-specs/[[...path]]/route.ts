import { passthrough } from "@/lib/proxy";

// Module H: the manufacturing envelope and the catalogue the bidder has recorded.
// Reads happen in the server component; only the mutations come through here (conventions.md).
type Ctx = { params: Promise<{ path?: string[] }> };

const target = async (params: Ctx["params"]) => {
  const { path } = await params;
  return `/api/product-specs${path?.length ? `/${path.join("/")}` : ""}`;
};

export async function POST(req: Request, { params }: Ctx) {
  return passthrough(req, await target(params));
}

export async function DELETE(req: Request, { params }: Ctx) {
  return passthrough(req, await target(params));
}
