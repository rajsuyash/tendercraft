"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export type Tab = {
  href: string;
  label: string;
  /** done = complete · current = outstanding work · sealed = gated · none = always available */
  state: "done" | "current" | "sealed" | "none";
  title?: string;
  exact?: boolean;
};

const MARK: Record<Tab["state"], string | null> = {
  done: "✓",
  current: "○",
  sealed: "🔒",
  none: null,
};

const MARK_CLS: Record<Tab["state"], string> = {
  done: "text-success",
  current: "text-warning",
  sealed: "text-muted",
  none: "",
};

/** Per-evaluation navigation. Horizontally scrollable so a narrow window never forces the
 *  page itself to scroll sideways (GLB-D2). */
export function EvaluationTabs({ tabs }: { tabs: Tab[] }) {
  const pathname = usePathname();

  return (
    <nav data-eval-tabs aria-label="Evaluation sections" className="-mb-px mt-4 overflow-x-auto">
      <ul className="flex min-w-max gap-1">
        {tabs.map((t) => {
          const active = t.exact ? pathname === t.href : pathname.startsWith(t.href);
          const mark = MARK[t.state];
          return (
            <li key={t.href}>
              <Link
                href={t.href}
                title={t.title}
                data-active={active || undefined}
                data-sealed={t.state === "sealed" || undefined}
                aria-current={active ? "page" : undefined}
                className={`flex min-h-9 items-center gap-1.5 whitespace-nowrap border-b-2 px-3 py-2 text-sm ${
                  active
                    ? "border-primary font-medium text-primary"
                    : "border-transparent text-muted hover:text-ink"
                }`}
              >
                {mark && (
                  <span aria-hidden className={`text-xs ${active ? "" : MARK_CLS[t.state]}`}>
                    {mark}
                  </span>
                )}
                {t.label}
                {t.state === "sealed" && <span className="sr-only"> (sealed)</span>}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
