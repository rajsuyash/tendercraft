"use client";

/**
 * Where you bid — the countries that feed the opportunity list.
 *
 * Deliberately NOT the same control as the EN/FR toggle, and deliberately not derived from it.
 * A French firm reading English chrome still bids in France; an Indian firm may pursue an
 * EU-wide notice. Language is a preference, this is a business decision, and wiring one to the
 * other would silently change a bidder's pipeline when they changed their reading language.
 *
 * Checkboxes rather than a dropdown because the set is small and multi-valued, and because the
 * consequence of each box has to be visible while choosing it — the count of tenders each
 * country contributes is the thing being decided, not the country's name.
 */

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { translator, type Locale } from "@/lib/i18n";

export type MarketOption = { market: string; sources: string[] };

/** Country codes to their English names, which are then the DICTIONARY KEYS — the same rule
 *  every other string here follows, so a market with no translation renders "Germany" rather
 *  than a bare `country.DE`. */
const COUNTRY: Record<string, string> = { IN: "India", FR: "France" };

/** Portal short names, for saying what a tick actually subscribes you to. */
const PORTAL_LABEL: Record<string, string> = {
  gem_bidplus: "GeM",
  ted: "TED",
};

export function MarketPicker({
  available,
  watched,
  home,
  locale = "en",
}: {
  available: MarketOption[];
  watched: string[];
  home: string;
  locale?: Locale;
}) {
  const router = useRouter();
  const t = translator(locale);
  const [selected, setSelected] = useState<string[]>(watched);
  const [pending, startTransition] = useTransition();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const dirty =
    selected.length !== watched.length || selected.some((m) => !watched.includes(m));

  function toggle(market: string) {
    setError(null);
    setSelected((prev) =>
      prev.includes(market) ? prev.filter((m) => m !== market) : [...prev, market],
    );
  }

  async function save() {
    // The last box is refused HERE as well as by the endpoint and by a database check
    // constraint. Not belt-and-braces theatre: a workspace watching nothing renders a feed
    // identical to "no tenders today", and a tender never seen produces no error anywhere.
    if (selected.length === 0) {
      setError(t("Choose at least one country — an empty feed would look like no tenders."));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/opportunities/markets", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ markets: selected }),
      });
      const body = await res.json().catch(() => null);
      if (!body?.ok) {
        setError(body?.error?.message ?? t("Could not change which countries you watch."));
        return;
      }
      startTransition(() => router.refresh());
    } finally {
      setBusy(false);
    }
  }

  return (
    <div data-market-picker>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {available.map((option) => {
          const on = selected.includes(option.market);
          const portals = option.sources.map((s) => PORTAL_LABEL[s] ?? s).join(", ");
          return (
            <label
              key={option.market}
              data-market-option={option.market}
              data-market-selected={on || undefined}
              className={`flex cursor-pointer items-start gap-2.5 rounded-card border p-3 transition-colors ${
                on ? "border-primary bg-primary-tint" : "border-hairline bg-surface hover:bg-surface-alt"
              }`}
            >
              <input
                type="checkbox"
                checked={on}
                disabled={busy || pending}
                onChange={() => toggle(option.market)}
                className="mt-0.5 h-4 w-4 rounded border-hairline accent-[color:var(--color-primary)]"
              />
              <span className="min-w-0">
                <span className="block text-sm font-medium text-ink">
                  {t(COUNTRY[option.market] ?? option.market)}
                  {option.market === home && (
                    // Naming the home market matters: it is the one that also decides currency
                    // and which statutory registers this profile asks for, and unticking it
                    // does NOT change those.
                    <span className="ml-2 rounded-full border border-hairline px-1.5 py-0.5 text-[10px] font-normal uppercase tracking-wide text-muted">
                      {t("registered here")}
                    </span>
                  )}
                </span>
                <span className="mt-0.5 block text-xs text-muted">{portals}</span>
              </span>
            </label>
          );
        })}
      </div>

      {error && (
        <p data-market-error className="mt-2 text-sm text-danger">
          {error}
        </p>
      )}

      {dirty && (
        <div className="mt-3 flex items-center gap-2">
          <button
            type="button"
            data-save-markets
            onClick={save}
            disabled={busy || pending}
            className="rounded-control bg-primary px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
          >
            {busy || pending ? t("Updating your feed…") : t("Save and re-match")}
          </button>
          <button
            type="button"
            onClick={() => {
              setSelected(watched);
              setError(null);
            }}
            disabled={busy || pending}
            className="rounded-control border border-hairline px-3 py-1.5 text-sm text-ink"
          >
            {t("Cancel")}
          </button>
        </div>
      )}
    </div>
  );
}
