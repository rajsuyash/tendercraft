"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/** C1 — fixed 280px primary navigation; active item primary-tinted. */
const NAV = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/tenders", label: "Tenders" },
  { href: "/proposals", label: "Proposals" },
  { href: "/library", label: "Knowledge Base" },
  { href: "/profile", label: "Vendor Profile" },
  { href: "/settings", label: "Settings" },
  { href: "/guide", label: "User guide" },
];

/**
 * `switcher` is a slot, not props: resolving which workspaces you can reach costs an engine
 * round trip (~0.9s measured), and inlining it here made every navigation wait for data that
 * the nav links themselves do not need. The layout streams it in through a Suspense boundary.
 */
export function Sidebar({ switcher }: { switcher?: React.ReactNode }) {
  const pathname = usePathname();
  return (
    // Sticky + translucent: this is the one place the app uses glass, because it is chrome
    // sitting over scrolling content — exactly where iOS uses it. Data surfaces stay opaque.
    <nav
      data-nav
      className="chrome-material sticky top-0 hidden h-screen w-sidebar shrink-0 flex-col border-r border-border px-3 py-5 lg:flex"
    >
      <div className="mb-6 flex items-center gap-2.5 px-2">
        <span className="grid h-8 w-8 place-items-center rounded bg-primary text-xs font-bold text-on-primary shadow-sm">
          TC
        </span>
        <span className="font-heading text-base font-semibold tracking-[-0.01em] text-ink">
          TenderCraft
        </span>
      </div>
      {switcher}
      <ul className="flex flex-col gap-0.5">
        {NAV.map((item) => {
          const active = pathname.startsWith(item.href);
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                data-active={active || undefined}
                aria-current={active ? "page" : undefined}
                // min-h-9 keeps every row a comfortable target without breaking the
                // 280px rail's density (skill: touch-target-size).
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
    </nav>
  );
}
