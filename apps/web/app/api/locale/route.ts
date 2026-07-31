/**
 * Persist the EN/FR choice: cookie for this browser, profile row for every other one.
 *
 * A route handler rather than a server action, per docs/conventions.md — one auditable mutation
 * path. Failing to persist to the profile is not an error the user should see: the cookie has
 * already taken effect, and the worst case is another device opening in the old language.
 */
import { NextResponse } from "next/server";

import { isLocale } from "@/lib/i18n";
import { LOCALE_COOKIE } from "@/lib/locale";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const { locale } = await request.json().catch(() => ({ locale: null }));
  if (!isLocale(locale)) {
    return NextResponse.json(
      {
        ok: false,
        data: null,
        error: { code: "UNSUPPORTED_LOCALE", message: "locale must be en or fr" },
      },
      { status: 422 },
    );
  }

  const response = NextResponse.json({ ok: true, data: { locale }, error: null });
  response.cookies.set(LOCALE_COOKIE, locale, {
    path: "/",
    maxAge: 60 * 60 * 24 * 365,
    sameSite: "lax",
  });

  try {
    const supabase = await createClient();
    const {
      data: { user },
    } = await supabase.auth.getUser();
    if (user) {
      await supabase.from("profiles").update({ locale }).eq("user_id", user.id);
    }
  } catch {
    // Cookie is already set; the preference simply will not follow them to another device.
  }
  return response;
}
