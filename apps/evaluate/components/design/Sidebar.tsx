"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

/**
 * C1 — fixed 280px primary navigation, ported from the bidder app.
 *
 * Role-aware by design. A `member` has no business on Settings and the engine would 403 them
 * anyway; rendering a link that rejects its own user is the "non-disabled control pointing at
 * an endpoint that refuses it" pitfall from docs/known-pitfalls.md. Filter, don't disable.
 */
type Role = "officer" | "chair" | "member" | "auditor";

const NAV: { href: string; label: string; roles: Role[] }[] = [
  { href: "/tenders", label: "Tenders", roles: ["officer", "chair", "member", "auditor"] },
  // Before a tender exists there is a draft. Officers only — a TEC member evaluates what was
  // published and has no business in the authoring of it.
  { href: "/drafts", label: "Drafts", roles: ["officer"] },
  { href: "/my-scoring", label: "My scoring", roles: ["chair", "member"] },
  { href: "/settings", label: "Settings", roles: ["officer", "chair"] },
  { href: "/guide", label: "How evaluation works", roles: ["officer", "chair", "member", "auditor"] },
];

const ROLE_LABEL: Record<string, string> = {
  officer: "Procurement Officer",
  chair: "TEC Chair",
  member: "TEC Member",
  auditor: "Audit / Vigilance",
};

export function Sidebar({
  authority,
  role,
}: {
  authority: string;
  role: string;
}) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const items = NAV.filter((n) => n.roles.includes(role as Role));

  return (
    <>
      {/* Below lg the rail collapses behind this button (GLB-D2). The bidder app still fails
          that AC — it hides the rail with `lg:flex` and offers no way to open it. */}
      <button
        type="button"
        data-nav-toggle
        aria-expanded={open}
        aria-controls="primary-nav"
        aria-label={open ? "Close navigation" : "Open navigation"}
        onClick={() => setOpen((v) => !v)}
        className="chrome-material fixed left-3 top-3 z-30 grid h-10 w-10 place-items-center rounded border border-border text-ink shadow-sm lg:hidden"
      >
        <span aria-hidden className="text-base leading-none">{open ? "✕" : "☰"}</span>
      </button>

      {/* Scrim, so a tap outside closes the rail rather than trapping the user. */}
      {open && (
        <button
          type="button"
          aria-hidden
          tabIndex={-1}
          onClick={() => setOpen(false)}
          className="fixed inset-0 z-10 bg-ink/20 lg:hidden"
        />
      )}

      <nav
        id="primary-nav"
        data-nav
        data-open={open || undefined}
        // Position classes are mutually exclusive by breakpoint, deliberately.
        //
        // Below lg the open rail is an OVERLAY: `fixed`, so it is out of flow and cannot widen
        // the document. The first version applied `sticky` and `fixed` together, which left the
        // rail taking 280px of layout inside the flex row — the page then scrolled sideways at
        // 900px, exactly what GLB-D2 forbids.
        //
        // At lg and above it is in-flow and sticky. Translucent throughout: the one place this
        // app uses glass, because it is chrome over scrolling content.
        className={`chrome-material z-20 h-screen w-sidebar shrink-0 flex-col border-r border-border px-3 py-5 lg:sticky lg:top-0 lg:flex ${
          open ? "fixed inset-y-0 left-0 flex" : "hidden"
        }`}
      >
        <Link href="/tenders" className="mb-6 flex items-center gap-2.5 px-2">
          <span className="grid h-8 w-8 place-items-center rounded bg-primary text-xs font-bold text-on-primary shadow-sm">
            TE
          </span>
          <span className="font-heading text-base font-semibold tracking-[-0.01em] text-ink">
            TenderCraft Evaluate
          </span>
        </Link>

        <ul className="flex flex-col gap-0.5">
          {items.map((item) => {
            const active = pathname.startsWith(item.href);
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  onClick={() => setOpen(false)}
                  data-active={active || undefined}
                  aria-current={active ? "page" : undefined}
                  // min-h-9 keeps a comfortable target without breaking the rail's density.
                  className={`flex min-h-9 items-center rounded px-3 py-2 text-sm ${
                    active
                      ? "bg-primary-tint font-medium text-primary"
                      : "text-muted hover:bg-surface-alt hover:text-ink"
                  }`}
                >
                  {item.label}
                </Link>
              </li>
            );
          })}
        </ul>

        {/* Identity lives at the foot of the rail now that the top header is gone. Which
            authority you are acting for is the most consequential context on every screen. */}
        <div className="mt-auto rounded border border-border bg-surface-alt p-3">
          <p className="text-2xs uppercase tracking-wider text-muted">Authority</p>
          <p className="mt-0.5 text-sm font-medium leading-snug text-ink">{authority}</p>
          <p className="mt-1 text-xs text-muted">{ROLE_LABEL[role] ?? role}</p>
        </div>
      </nav>
    </>
  );
}
