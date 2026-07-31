/**
 * Where the active locale comes from, on the server.
 *
 * Cookie first, then the user's stored preference. The cookie exists so the toggle feels
 * instant and so an unauthenticated page can still render in the right language; the profile
 * row is what survives a new device. `profiles.locale` is per USER, never per workspace — two
 * people in the same French workspace may read different chrome, and neither choice changes a
 * character of what a tender says.
 */
import { cookies } from "next/headers";

import { DEFAULT_LOCALE, isLocale, type Locale } from "@/lib/i18n";
import { createClient } from "@/lib/supabase/server";

export const LOCALE_COOKIE = "tc_locale";

export async function getLocale(): Promise<Locale> {
  const jar = await cookies();
  const fromCookie = jar.get(LOCALE_COOKIE)?.value;
  if (isLocale(fromCookie)) return fromCookie;

  try {
    const supabase = await createClient();
    const {
      data: { user },
    } = await supabase.auth.getUser();
    if (!user) return DEFAULT_LOCALE;
    const { data } = await supabase
      .from("profiles")
      .select("locale")
      .eq("user_id", user.id)
      .maybeSingle();
    return isLocale(data?.locale) ? data.locale : DEFAULT_LOCALE;
  } catch {
    // A locale lookup must never be able to break a page render.
    return DEFAULT_LOCALE;
  }
}
