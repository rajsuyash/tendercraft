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
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <nav
      data-nav
      className="hidden w-sidebar shrink-0 flex-col border-r border-border bg-surface px-3 py-5 lg:flex"
    >
      <div className="mb-6 flex items-center gap-2 px-2">
        <span className="grid h-8 w-8 place-items-center rounded bg-primary text-xs font-bold text-on-primary">
          TC
        </span>
        <span className="font-heading text-lg font-semibold text-ink">TenderCraft</span>
      </div>
      <ul className="flex flex-col gap-1">
        {NAV.map((item) => {
          const active = pathname.startsWith(item.href);
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                data-active={active || undefined}
                className={`block rounded px-3 py-2 text-sm ${
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
