import { createServerClient, type CookieOptions } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

type CookieToSet = { name: string; value: string; options: CookieOptions };
// Prefix-matched: everything under these paths is public.
const PUBLIC_PREFIX = ["/login"];
// EXACT-matched, and it must stay that way. "/" under a startsWith() check matches every path
// in the application and would make the entire product public — including the sealed financial
// routes. If you add an entry here, add it to the exact list, not the prefix list.
const PUBLIC_EXACT = ["/", "/landing.html"];

export async function updateSession(request: NextRequest) {
  let response = NextResponse.next({ request });
  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_EVAL_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_EVAL_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll: () => request.cookies.getAll(),
        setAll(list: CookieToSet[]) {
          list.forEach(({ name, value }) => request.cookies.set(name, value));
          response = NextResponse.next({ request });
          list.forEach(({ name, value, options }) => response.cookies.set(name, value, options));
        },
      },
    },
  );
  const { data: { user } } = await supabase.auth.getUser();
  const path = request.nextUrl.pathname;
  const isPublic =
    PUBLIC_EXACT.includes(path) || PUBLIC_PREFIX.some((p) => path.startsWith(p));

  if (!user && !isPublic) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    return NextResponse.redirect(url);
  }

  // A signed-in officer landing on the marketing page wants their work, not the pitch.
  if (user && path === "/") {
    const url = request.nextUrl.clone();
    url.pathname = "/tenders";
    return NextResponse.redirect(url);
  }
  return response;
}
