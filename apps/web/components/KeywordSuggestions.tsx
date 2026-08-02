"use client";

/**
 * Proposed keywords, for a human to accept.
 *
 * **Nothing here saves.** Terms land in the input the vendor was already editing; the ordinary
 * profile save is what writes them. That boundary is the guardrail, not the number of clicks:
 * capability keywords feed `keyword_match_required`, the one rule that HIDES tenders, so a model
 * writing them straight to the profile would be model-driven exclusion (G-9) by a longer route.
 * With the field editable and a save in between, a person is still the author of every term that
 * ends up gating a feed.
 *
 * Given that, auto-fill is safe and it is what makes the feature useful — a vendor should not
 * have to know this button exists. Two limits keep it honest:
 *
 *   * it runs ONLY into an empty box, so terms a vendor typed are never overwritten by a
 *     reading of their website, and
 *   * it says it happened, and says the terms are editable, rather than quietly appearing.
 *
 * Every suggestion still quotes the words it came from, so a vendor reviewing the filled box can
 * check any term against the page it was taken from.
 */

import { useEffect, useRef, useState } from "react";

import { translator, type Locale } from "@/lib/i18n";

type Suggestion = { keyword: string; source: string; evidence: string };
type Sources = {
  capability_statement: boolean;
  existing_keywords: number;
  website: boolean;
  website_url: string | null;
  website_error: string | null;
  annual_report: boolean;
  pages_read?: string[];
};

const SOURCE_LABEL: Record<string, string> = {
  statement: "your capability statement",
  existing: "your existing keywords",
  website: "your website or annual report",
};

export function KeywordSuggestions({
  websiteUrl,
  currentKeywords,
  onAccept,
  onAcceptMany,
  locale = "en",
}: {
  websiteUrl: string;
  /** What is in the keywords box right now. Auto-fill only ever happens when this is empty. */
  currentKeywords: string;
  /** Called with one accepted term; the parent appends it to the keywords input. */
  onAccept: (keyword: string) => void;
  onAcceptMany: (keywords: string[]) => void;
  locale?: Locale;
}) {
  const t = translator(locale);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<Suggestion[] | null>(null);
  const [sources, setSources] = useState<Sources | null>(null);
  const [taken, setTaken] = useState<string[]>([]);
  const [deterministicOnly, setDeterministicOnly] = useState(false);
  const [autoFilled, setAutoFilled] = useState(false);
  // Auto-fill fires once per mount, and only into an empty box. A ref rather than state so a
  // re-render from the fill itself cannot retrigger it.
  const autoRan = useRef(false);

  async function run(autoFill = false) {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/profile/keyword-suggestions", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ website_url: websiteUrl.trim() || null }),
      });
      const body = await res.json().catch(() => null);
      if (!body?.ok) {
        setError(body?.error?.message ?? t("Could not read your profile for suggestions."));
        return;
      }
      const found: Suggestion[] = body.data.suggestions ?? [];
      setSuggestions(found);
      setSources(body.data.sources ?? null);
      setDeterministicOnly(Boolean(body.data.deterministic_only));

      // Auto-populate — but ONLY into an empty box, and only with terms that are still sitting
      // in an editable input the vendor has to save. Never an overwrite: a vendor who typed
      // their own terms must not have them replaced by a reading of their website.
      if (autoFill && found.length) {
        onAcceptMany(found.map((f) => f.keyword));
        setTaken(found.map((f) => f.keyword));
        setAutoFilled(true);
      }
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (autoRan.current) return;
    // Nothing to read from, or the vendor already has terms — either way, do not act.
    if (!websiteUrl.trim() || currentKeywords.trim()) return;
    autoRan.current = true;
    void run(true);
    // Deliberately mount-only: this is a first-run convenience, not a live sync. Re-running it
    // as the vendor types their website would fight the person editing the field.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div data-keyword-suggestions className="mt-2">
      <button
        type="button"
        data-suggest-keywords
        onClick={() => run(false)}
        disabled={busy}
        className="rounded-control border border-hairline bg-surface px-2.5 py-1 text-xs font-medium text-ink hover:bg-surface-alt disabled:opacity-50"
      >
        {busy ? t("Reading your profile…") : t("Suggest keywords from my profile")}
      </button>

      {error && <p className="mt-1 text-xs text-danger">{error}</p>}

      {autoFilled && (
        <p data-auto-filled className="mt-1.5 text-xs text-success">
          {t(
            "Filled in from your website — edit or delete any of them in the box above before saving.",
          )}
        </p>
      )}

      {sources && (
        <p className="mt-1.5 text-xs text-muted">
          {/* Naming what was actually read. A vendor who supplied a website and got nothing from
              it must be told, not left to assume it counted. */}
          {t("Read")}: {sources.capability_statement ? t("your capability statement") : null}
          {sources.capability_statement && sources.existing_keywords > 0 ? ", " : ""}
          {sources.existing_keywords > 0
            ? `${sources.existing_keywords} ${t("existing keywords")}`
            : null}
          {sources.website ? `, ${t("your website")}` : ""}
          {sources.annual_report ? `, ${t("your annual report")}` : ""}
          {sources.website_error ? (
            <span className="text-warning">
              {" · "}
              {t("could not read the website")}: {sources.website_error}
            </span>
          ) : null}
          {deterministicOnly && (
            <span className="text-warning">
              {" · "}
              {t("suggestions came from splitting your existing terms only — the model was unavailable")}
            </span>
          )}
        </p>
      )}

      {suggestions?.length === 0 && (
        <p className="mt-1.5 text-xs text-muted">
          {t("Nothing to suggest — add a capability statement or a website first.")}
        </p>
      )}

      {suggestions && suggestions.length > 0 && suggestions.some((s) => !taken.includes(s.keyword)) && (
        <button
          type="button"
          data-accept-all
          onClick={() => {
            const rest = suggestions.filter((s) => !taken.includes(s.keyword));
            onAcceptMany(rest.map((s) => s.keyword));
            setTaken((prev) => [...prev, ...rest.map((s) => s.keyword)]);
          }}
          className="mt-2 text-xs font-medium text-primary hover:underline"
        >
          {t("Add all")}
        </button>
      )}

      {suggestions && suggestions.length > 0 && (
        <ul className="mt-2 flex flex-wrap gap-1.5">
          {suggestions.map((s) => {
            const used = taken.includes(s.keyword);
            return (
              <li key={s.keyword}>
                <button
                  type="button"
                  data-suggestion={s.keyword}
                  disabled={used}
                  onClick={() => {
                    onAccept(s.keyword);
                    setTaken((prev) => [...prev, s.keyword]);
                  }}
                  // The evidence is the point: accepting a term you cannot trace is how a
                  // keyword nobody chose ends up gating the feed.
                  title={`${SOURCE_LABEL[s.source] ?? s.source} — “${s.evidence}”`}
                  className={`rounded-full border px-2 py-0.5 text-xs transition-colors ${
                    used
                      ? "border-hairline bg-surface-alt text-muted"
                      : "border-primary bg-primary-tint text-primary hover:bg-primary hover:text-white"
                  }`}
                >
                  {used ? `✓ ${s.keyword}` : `+ ${s.keyword}`}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
