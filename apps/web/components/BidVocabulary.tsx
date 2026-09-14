"use client";

/**
 * What you bid on — moved from `/profile` to `/capability`, 2026-09-14.
 *
 * Three screens each held a THIRD of one vocabulary: `/profile` had the typed keyword box,
 * `/prices` holds GeM category names, this screen holds product-envelope standard references.
 * The gate (`keyword_match_required`) has run on all three merged since the fix that shipped
 * `GET /api/capability/vocabulary` — but until this moved, the only editable box still showed
 * 16 of 31 terms, so an excluded tender could be explained by a term the user had never seen
 * and had no way to find (docs/feedback/usha-martin.md). Moving the editor here puts the typed
 * third beside the other two-thirds instead of two doors away from them.
 *
 * `vendor_profiles` and `product_specs` stay two tables — one answers "are we eligible to bid",
 * the other "can we make this" — this only moves where the keyword TEXT is edited.
 *
 * Derived terms (category names, standard refs) are shown READ-ONLY rather than silently
 * merged into the typed list: they are recorded elsewhere (`/prices`, the envelope above), and
 * a term a user cannot find the source of is a term they cannot fix when it goes stale.
 *
 * Reach ships on every row — typed or derived — because a dead term and a quiet market read
 * identical with no other signal (`app/spec_routes.py::capability_vocabulary`). A typo in this
 * workspace's keywords once matched 0 of 581 tenders with nothing anywhere saying so.
 */

import { useRouter } from "next/navigation";
import { useState } from "react";

import { translator, type Locale } from "@/lib/i18n";

import { KeywordSuggestions } from "./KeywordSuggestions";
import { splitKeywords, unlikelyKeywords } from "./ProfileForm";

export type VocabTerm = {
  term: string;
  source: "typed" | "category" | "standard";
  /** Which recorded row a derived term came from ("" for typed). */
  origin: string;
  /** How many open tenders this term alone would keep — deterministic, out of `corpus_open`. */
  reach: number;
};

/** Typed terms are the only ones this screen can edit; derived ones live on another screen.
 *  `dead` cuts across both — a term matching nothing is worth flagging regardless of where it
 *  was recorded. */
export function groupBySource(
  terms: VocabTerm[],
): { typed: VocabTerm[]; derived: VocabTerm[]; dead: VocabTerm[] } {
  return {
    typed: terms.filter((t) => t.source === "typed"),
    derived: terms.filter((t) => t.source !== "typed"),
    dead: terms.filter((t) => t.reach === 0),
  };
}

const INPUT =
  "w-full rounded border border-border bg-surface px-2.5 py-1.5 text-sm text-ink " +
  "focus:border-primary focus:outline-none";

/** Turns a `/api/profile` response into the message to show, or `null` on success.
 *
 * Extracted so the failure path is testable with no rendering harness (this repo has no
 * React Testing Library wired up) — a 500 answering with an HTML error page makes `res.json()`
 * itself reject, which is exactly the case a naive `body.ok` read misses, and is where the
 * "a failed save says nothing" bug actually lived.
 */
export async function saveErrorMessage(
  res: Pick<Response, "json">,
  fallback: string,
): Promise<string | null> {
  const body = await res.json().catch(() => null);
  if (body?.ok) return null;
  return body?.error?.message ?? fallback;
}

export function BidVocabulary({
  terms,
  keywordsRaw,
  statement,
  corpusOpen,
  gateEnabled,
  websiteUrl,
  locale = "en",
}: {
  terms: VocabTerm[];
  keywordsRaw: string;
  statement: string;
  corpusOpen: number;
  gateEnabled: boolean;
  websiteUrl: string;
  locale?: Locale;
}) {
  const router = useRouter();
  const t = translator(locale);
  const { derived, dead } = groupBySource(terms);

  const [raw, setRaw] = useState(keywordsRaw);
  const [text, setText] = useState(statement);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /** Append rather than replace — a suggestion must not discard what the vendor typed. */
  const append = (fresh: string[]) =>
    setRaw((current) => {
      const have = splitKeywords(current);
      const additions = fresh.map((k) => k.trim().toLowerCase()).filter((k) => k && !have.includes(k));
      if (!additions.length) return current;
      const trimmed = current.trim();
      return trimmed ? `${trimmed}, ${additions.join(", ")}` : additions.join(", ");
    });

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/profile", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          // "" rather than null — the engine drops nulls (exclude_none=True) instead of
          // writing them, so a null could never clear the field once set.
          capability_statement: text ?? "",
          capability_keywords: splitKeywords(raw),
        }),
      });
      const message = await saveErrorMessage(res, t("Could not save your vocabulary"));
      if (message) {
        setError(message);
        return;
      }
      // The server trims/dedupes/lower-cases; resync the box so it cannot keep showing raw
      // typing that no longer matches what was actually stored — router.refresh() re-renders
      // this client component's PARENT with fresh props, but preserves this instance, so the
      // new props never reach local state on their own.
      setRaw(splitKeywords(raw).join(", "));
      router.refresh();
    } catch {
      // fetch() itself rejecting (offline, network error) must not fail silently — save() is
      // called as `onClick={() => void save()}`, so a thrown/rejected promise with no catch
      // here would vanish with the user told nothing.
      setError(t("Could not save your vocabulary"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section data-bid-vocabulary className="mb-8 rounded-card border border-border bg-surface p-card">
      <h2 className="mb-1 font-heading text-base font-medium text-ink">{t("What you bid on")}</h2>
      <p className="mb-3 max-w-prose text-xs text-muted">
        {gateEnabled
          ? t(
              "A tender matching none of these terms is excluded from your feed. Reach is out of {n} open tenders.",
            ).replace("{n}", String(corpusOpen))
          : t(
              "Nothing is hidden because of these terms unless you switch on the narrow feed yourself. Reach is out of {n} open tenders.",
            ).replace("{n}", String(corpusOpen))}
      </p>

      {error ? (
        <p className="mb-3 rounded border border-danger bg-danger-bg p-3 text-sm text-danger">
          {error}
        </p>
      ) : null}

      <div className="grid grid-cols-1 gap-3">
        <label className="block">
          <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-muted">
            {t("Capability and expertise")}
          </span>
          <textarea
            data-field-capability
            rows={4}
            className={INPUT}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-muted">
            {t("Keywords you bid on (comma separated)")}
          </span>
          <input
            data-field-capability-keywords
            className={INPUT}
            value={raw}
            onChange={(e) => setRaw(e.target.value)}
          />
          <KeywordSuggestions
            websiteUrl={websiteUrl}
            currentKeywords={raw}
            locale={locale}
            onAccept={(kw) => append([kw])}
            onAcceptMany={append}
          />
          {(() => {
            // Live, as the user types — not just after a save+refresh round trip via `dead`.
            // This is the guard built after USHA MARTIN INDIA typed prose as keywords,
            // switched on the opt-in gate, and hid all 335 swept tenders with the screen
            // telling them to sweep GeM again, the one action that could not help
            // (ProfileForm.test.ts). It moved here with the rest of the editor; it must not
            // have stopped being called along the way.
            const unlikely = unlikelyKeywords(splitKeywords(raw));
            if (!unlikely.length) return null;
            return (
              <p data-keyword-warning className="mt-1 text-xs text-warning">
                {t(
                  "These are sentences rather than keywords and will match almost nothing — a term is matched whole against a tender's title:",
                )}{" "}
                <span className="font-medium">{unlikely.map((k) => `“${k}”`).join(", ")}</span>
              </p>
            );
          })()}
        </label>
      </div>

      <button
        type="button"
        onClick={() => void save()}
        disabled={busy}
        className="mt-4 rounded bg-primary px-4 py-2 text-sm font-medium text-on-primary disabled:opacity-50"
      >
        {busy ? t("Saving…") : t("Save")}
      </button>

      {derived.length > 0 ? (
        <div data-derived-terms className="mt-5 border-t border-border pt-4">
          <p className="mb-2 text-xs text-muted">
            {t(
              "Also gating your feed — read only here, changed where each is recorded (price-history categories, or the standard above):",
            )}
          </p>
          <ul className="flex flex-wrap gap-2">
            {derived.map((term) => (
              <li
                key={`${term.source}:${term.term}`}
                title={`${term.source}${term.origin ? ` · ${term.origin}` : ""}`}
                className="rounded border border-border bg-surface-alt px-2 py-1 text-xs text-ink"
              >
                {term.term} <span className="text-muted">· {term.reach}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {dead.length > 0 ? (
        <p data-dead-terms className="mt-3 text-xs text-warning">
          {t("These match none of your {n} open tenders and cannot affect your feed:").replace(
            "{n}",
            String(corpusOpen),
          )}{" "}
          <span className="font-medium">{dead.map((d) => `"${d.term}"`).join(", ")}</span>
        </p>
      ) : null}
    </section>
  );
}
