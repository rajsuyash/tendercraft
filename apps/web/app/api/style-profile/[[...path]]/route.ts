import { passthrough } from "@/lib/proxy";

// House style: read the current profile (GET), re-measure it from past bids (POST /rebuild).
type Ctx = { params: Promise<{ path?: string[] }> };

const target = async (params: Ctx["params"]) => {
  const { path } = await params;
  return `/api/style-profile${path?.length ? `/${path.join("/")}` : ""}`;
};

export async function GET(req: Request, { params }: Ctx) {
  return passthrough(req, await target(params));
}

export async function POST(req: Request, { params }: Ctx) {
  return passthrough(req, await target(params));
}
