/**
 * Indian-format display helpers (docs/DESIGN_SPEC.md §C, docs/conventions.md).
 *
 * The design contract requires currency in Indian format (₹10 Cr, ₹2,40,000),
 * dates as DD/MM/YYYY, and financial years as FY23–FY25 — everywhere, never ad-hoc.
 * These are pure functions so they unit-test without a browser.
 */

const EN_DASH = "–";

/** Indian digit grouping with a ₹ prefix, e.g. 240000 → "₹2,40,000". */
export function formatINR(rupees: number): string {
  if (!Number.isFinite(rupees)) throw new RangeError("formatINR: value must be finite");
  const grouped = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 }).format(
    Math.round(rupees),
  );
  return `₹${grouped}`;
}

/** Crore amounts, trailing zeros trimmed: 10 → "₹10 Cr", 8.2 → "₹8.2 Cr". */
export function formatCrore(valueInCr: number): string {
  if (!Number.isFinite(valueInCr)) throw new RangeError("formatCrore: value must be finite");
  const rounded = Math.round(valueInCr * 100) / 100;
  const text = rounded
    .toFixed(2)
    .replace(/\.00$/, "")
    .replace(/(\.\d)0$/, "$1");
  return `₹${text} Cr`;
}

/** Zero-padded DD/MM/YYYY. */
export function formatDate(d: Date): string {
  if (Number.isNaN(d.getTime())) throw new RangeError("formatDate: invalid Date");
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  return `${dd}/${mm}/${d.getFullYear()}`;
}

/** Financial-year range label, e.g. ("FY23","FY25") → "FY23–FY25"; equal → "FY23". */
export function formatFYRange(startLabel: string, endLabel: string): string {
  return startLabel === endLabel ? startLabel : `${startLabel}${EN_DASH}${endLabel}`;
}

/** AI confidence as a fixed 2-decimal badge value, e.g. 0.8 → "0.80". */
export function formatConfidence(confidence: number): string {
  if (confidence < 0 || confidence > 1) {
    throw new RangeError("formatConfidence: confidence must be within [0, 1]");
  }
  return confidence.toFixed(2);
}
