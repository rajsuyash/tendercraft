import { passthrough } from "@/lib/proxy";

// Award price history (GET) and its explicit portal refresh (POST). Forwarded, not
// reimplemented — the engine owns the corpus and the connector call.
type Ctx = { params: Promise<{ path?: string[] }> };

const target = async (params: Ctx["params"], req: Request) => {
  const { path } = await params;
  const qs = new URL(req.url).search;
  return `/api/price-history${path?.length ? `/${path.join("/")}` : ""}${qs}`;
};

export async function GET(req: Request, { params }: Ctx) {
  return passthrough(req, await target(params, req));
}

export async function POST(req: Request, { params }: Ctx) {
  return passthrough(req, await target(params, req));
}
