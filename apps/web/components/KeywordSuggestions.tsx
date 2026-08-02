"use client";

/**
 * Proposed keywords, for a human to accept.
 *
 * **Nothing here saves.** The vendor ticks terms and they are appended to the input they were
 * already editing; the ordinary profile save is what writes them. That is a guardrail, not a
 * UX preference: capability keywords feed `keyword_match_required`, the one rule that HIDES
 * tenders, so a model writing them straight to the profile would be model-driven exclusion
 * (G-9) reached by a longer route than the guardrail names, with the same effect — a bidder
 * never seeing a tender because of a term no person chose.
 *
 * Every suggestion shows where it came from and quotes the words it came from, so accepting one
 * is a decision with evidence rather than a shrug. There is deliberately no "accept all".
 */

import { useState } from "react";

import { translator, type Locale } from "@/lib/i18n";

type Suggestion = { keyword: string; source: string; evidence: string };
type Sources = {
  capability_statement: boolean;
  existing_keywords: number;
  website: boolean;
  website_url: string | null;
  website_error: string | null;
  annual_report: boolean;
};

const SOURCE_LABEL: Record<string, string> = {
  statement: "your capability statement",
  existing: "your existing keywords",
  website: "your website or annual report",
};

export function KeywordSuggestions({
  websiteUrl,
  onAccept,
  locale = "en",
}: {
  websiteUrl: string;
  /** Called with the accepted term; the parent appends it to the keywords input. */
  onAccept: (keyword: string) => void;
  locale?: Locale;
}) {
  const t = translator(locale);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<Suggestion[] | null>(null);
  const [sources, setSources] = useState<Sources | null>(null);
  const [taken, setTaken] = useState<string[]>([]);
  const [deterministicOnly, setDeterministicOnly] = useState(false);

  async function run() {
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
      setSuggestions(body.data.suggestions ?? []);
      setSources(body.data.sources ?? null);
      setDeterministicOnly(Boolean(body.data.deterministic_only));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div data-keyword-suggestions className="mt-2">
      <button
        type="button"
        data-suggest-keywords
        onClick={run}
        disabled={busy}
        className="rounded-control border border-hairline bg-surface px-2.5 py-1 text-xs font-medium text-ink hover:bg-surface-alt disabled:opacity-50"
      >
        {busy ? t("Reading your profile…") : t("Suggest keywords from my profile")}
      </button>

      {error && <p className="mt-1 text-xs text-danger">{error}</p>}

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
