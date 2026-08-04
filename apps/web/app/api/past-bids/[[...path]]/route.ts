import { passthrough } from "@/lib/proxy";

// Past bids: upload + mine (POST), list (GET), outcome correction (PATCH /:id).
type Ctx = { params: Promise<{ path?: string[] }> };

const target = async (params: Ctx["params"]) => {
  const { path } = await params;
  return `/api/past-bids${path?.length ? `/${path.join("/")}` : ""}`;
};

export async function GET(req: Request, { params }: Ctx) {
  return passthrough(req, await target(params));
}

export async function POST(req: Request, { params }: Ctx) {
  return passthrough(req, await target(params));
}

export async function PATCH(req: Request, { params }: Ctx) {
  return passthrough(req, await target(params));
}
