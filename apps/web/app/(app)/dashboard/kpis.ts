/**
 * Dashboard KPI values.
 *
 * Extracted from the page so the zero-versus-unknown rule is testable. Two of the four tiles
 * were literal `value: 0` rendered identically to the one real measurement; verified against
 * production on 2026-09-09, the workspace showing "Awaiting verification 0" had 861
 * unconfirmed criteria.
 *
 * That matters more here than it would in most products. This one's whole position is that it
 * does not assert what it has not checked: NOT ASSESSED rather than a guess, needs_review
 * rather than a coerced verdict, "Published means recorded here by you". A front-page tile
 * inventing a measurement contradicts the thing being sold, and it does it first.
 */

/** A count that could not be read. Rendered as an em dash, never as a number. */
export const UNKNOWN = null;

export type KpiValue = number | typeof UNKNOWN;

/**
 * How a KPI count renders.
 *
 * `null` means "we could not read this", which is a different claim from "this is zero" and
 * must not be shown as one. A failed count that renders 0 is exactly the bug this file exists
 * to prevent, arriving through the fallback instead of through a literal.
 */
export function formatKpi(value: KpiValue): string {
  return value === null || value === undefined ? "—" : String(value);
}

/**
 * Supabase head-only counts return `count: number | null`. Null means the request failed or
 * returned no count header — not a zero.
 */
export function countOrUnknown(count: number | null | undefined): KpiValue {
  return typeof count === "number" ? count : UNKNOWN;
}
