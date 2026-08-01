/** Indian currency. ₹4.88 Cr reads to an Indian officer; ₹48,750,000 does not.
 *
 * The argument is **rupees**, and the name says so. It was `paise` while the maths divided by
 * 10^7 — which is the rupee-to-crore conversion, not the paise one (a crore of rupees is 10^9
 * paise). The figures on screen were right and the signature was inviting the next caller to
 * pass paise and be wrong by a factor of a hundred. Money-unit mismatch is a named entry in
 * docs/evaluate/known-pitfalls.md; this is where it would have started.
 *
 * `bid_financials.amount_inr` is rupees, which is what every caller here passes.
 */
export function formatCrore(rupees: number | string): string {
  const n = typeof rupees === "string" ? Number(rupees) : rupees;
  // A non-finite amount renders as an em dash rather than "NaN Cr" or, worse, 0 — on a
  // procurement screen an unreadable figure must never be shown as a real one.
  if (!Number.isFinite(n)) return "—";
  const cr = n / 10_000_000;
  return `₹${cr.toFixed(2)} Cr`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}/${d.getFullYear()}`;
}
