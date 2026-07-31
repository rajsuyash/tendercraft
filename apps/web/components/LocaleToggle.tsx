"use client";

/**
 * EN | FR.
 *
 * Deliberately a visible two-state control rather than a dropdown: there are two locales, and a
 * bid manager should be able to see which one they are in without opening anything.
 */
import { useRouter } from "next/navigation";
import { useTransition } from "react";

import type { Locale } from "@/lib/i18n";

export function LocaleToggle({ locale }: { locale: Locale }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();

  async function choose(next: Locale) {
    if (next === locale) return;
    await fetch("/api/locale", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ locale: next }),
    });
    startTransition(() => router.refresh());
  }

  return (
    <div
      data-locale-toggle={locale}
      className="inline-flex overflow-hidden rounded-control border border-hairline"
      role="group"
      aria-label="Language / Langue"
    >
      {(["en", "fr"] as const).map((code) => (
        <button
          key={code}
          type="button"
          onClick={() => choose(code)}
          disabled={pending}
          aria-pressed={locale === code}
          className={`px-2 py-1 text-[11px] font-semibold uppercase tracking-wide transition-colors disabled:opacity-50 ${
            locale === code
              ? "bg-primary text-white"
              : "bg-surface text-muted hover:bg-surface-alt hover:text-ink"
          }`}
        >
          {code}
        </button>
      ))}
    </div>
  );
}
