/** Indian currency. ₹4.88 Cr reads to an Indian officer; ₹48,750,000 does not. */
export function formatCrore(paise: number | string): string {
  const n = typeof paise === "string" ? Number(paise) : paise;
  if (!Number.isFinite(n)) return "—";
  const cr = n / 10_000_000;
  return `₹${cr.toFixed(2)} Cr`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}/${d.getFullYear()}`;
}
