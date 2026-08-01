import { notFound } from "next/navigation";

import { TenderTabs, type Tab } from "@/components/design/TenderTabs";
import { getTender, getTechnical } from "@/lib/engine";

/**
 * Per-evaluation navigation.
 *
 * A nested layout, unlike the (app) layout, receives `params` — so the tab state is resolved
 * server-side with no client fetch and no loading flicker in the chrome. Both reads are
 * cache()-deduped, so the page below re-using them costs nothing.
 *
 * DESIGN_SPEC §E S5 already establishes tabs as this product family's per-entity navigation
 * ("Criteria · Forms & Annexures · Corrigenda (n) · Handoffs"). Following that beats inventing
 * a second 280px rail beside C1.
 */
export default async function TenderLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const [det, tech] = await Promise.all([getTender(id), getTechnical(id)]);
  if (!det.ok || !det.data) notFound();

  const { tender: ev, bids, members, coi, unconfirmed } = det.data;
  const screened = bids.filter((b) => b.responsive !== null).length;
  const undeclared = members.filter(
    (m) => m.role !== "auditor" && !coi.some((c) => c.user_id === m.user_id),
  ).length;
  const sealed = !ev.technical_locked_at;

  const base = `/tenders/${id}`;
  const tabs: Tab[] = [
    { href: base, label: "Overview", state: "none", exact: true },
    {
      href: `${base}/framework`,
      label: "Framework",
      state: ev.framework_locked_at ? "done" : "current",
    },
    {
      href: `${base}/bids`,
      label: "Bids",
      state: bids.length > 0 ? "done" : "current",
    },
    {
      // Sits between intake and screening because that is the order the work happens in:
      // what arrived, then whether it satisfies the checklist, then whether the bid qualifies.
      href: `${base}/documents`,
      label: "Documents",
      state: bids.length > 0 ? "current" : "none",
    },
    {
      href: `${base}/screening`,
      label: "Screening",
      state: bids.length > 0 && screened === bids.length ? "done" : "current",
    },
    {
      // Read before scoring: it is what turns "read every bid end to end" into "read the
      // requirements that need you".
      href: `${base}/compliance`,
      label: "Compliance",
      state: bids.length > 0 ? "current" : "none",
    },
    {
      href: `${base}/technical`,
      label: "Technical",
      state: ev.technical_locked_at ? "done" : "current",
    },
    {
      // Deliberately NOT hidden and NOT disabled. The sealed screen is the explanation, and a
      // padlock in the navigation makes the strongest guarantee in the product visible at a
      // glance instead of invisible.
      href: `${base}/financial`,
      label: "Financial",
      state: sealed ? "sealed" : "done",
      title: sealed
        ? "Sealed until technical scores are locked — every endpoint that could reach a price refuses"
        : undefined,
    },
    { href: `${base}/result`, label: "Result", state: sealed ? "sealed" : "done" },
    // Sealed alongside Result: an outcome letter states an accepted price, so it cannot exist
    // any earlier than the price can be read.
    { href: `${base}/award`, label: "Outcome", state: sealed ? "sealed" : "done" },
    { href: `${base}/audit`, label: "Audit trail", state: "none" },
    { href: `${base}/report`, label: "Report", state: sealed ? "sealed" : "done" },
  ];

  const outstanding =
    unconfirmed + undeclared + (bids.length - screened) + (tech.data?.blockers.length ?? 0);

  return (
    <div>
      <header className="border-b border-border bg-surface">
        <div className="px-page pb-0 pt-page">
          <p className="text-xs text-muted">{ev.tender_number ?? "—"}</p>
          <h1 className="mt-1 font-heading text-2xl font-semibold text-ink">{ev.title}</h1>
          <p className="mt-1.5 text-sm text-muted">
            Two-bid QCBS {ev.technical_weight}:{ev.financial_weight} · qualifying{" "}
            {ev.qualifying_marks} · quorum {ev.quorum}
            {outstanding > 0 && (
              <>
                {" · "}
                <span className="text-warning">
                  {outstanding} outstanding item{outstanding === 1 ? "" : "s"}
                </span>
              </>
            )}
          </p>
          <TenderTabs tabs={tabs} />
        </div>
      </header>
      {children}
    </div>
  );
}
