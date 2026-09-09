"use client";

import { LocaleToggle } from "@/components/LocaleToggle";
import { translator, type Locale } from "@/lib/i18n";
import Link from "next/link";
import { usePathname } from "next/navigation";

/**
 * C1 — fixed 280px primary navigation; active item primary-tinted.
 *
 * Grouped rather than flat. Eleven equal-weight items gave a new workspace no idea which were
 * jobs, which were inputs other screens depend on, and which only say anything after several
 * bids. A customer with five tenders and eighteen documents still opened on a list where six
 * entries read "nothing yet", with nothing to indicate that was the expected order of events.
 *
 * The three groups answer three different questions:
 *   Work        — what am I doing now
 *   Your company — what does the system know about us (all of these FEED the work)
 *   Insight     — what has it noticed, which is empty until there is history to notice
 *
 * ROUTES ARE UNCHANGED, deliberately. Every href here is the same one it was; only order and
 * grouping moved, so nothing bookmarked breaks and `docs/DESIGN_SPEC.md` §I's route contract
 * still holds. Labels are unchanged for the same reason: the in-app user guide lists these
 * features by name and the page headers match them, so a rename here desyncs three places at
 * once. That is a separate change with its own diff.
 */
const NAV_GROUPS: { label: string | null; items: { href: string; label: string }[] }[] = [
  {
    label: null, // The work itself needs no heading; it is what the app is for.
    items: [
      { href: "/dashboard", label: "Dashboard" },
      { href: "/opportunities", label: "Opportunities" },
      { href: "/tenders", label: "Tenders" },
      { href: "/proposals", label: "Proposals" },
    ],
  },
  {
    // These three are INPUTS. Capability feeds schedule fit, the profile feeds eligibility,
    // the library feeds every citation. Kept visible even when empty: hiding the editor that
    // collects an input is how a user never discovers the input exists.
    label: "Your company",
    items: [
      { href: "/library", label: "Knowledge Base" },
      { href: "/profile", label: "Vendor Profile" },
      { href: "/capability", label: "Capability" },
    ],
  },
  {
    // Retrospective. Both are honestly empty until there is history, and grouping them says
    // so structurally instead of leaving each screen to apologise for itself.
    label: "Insight",
    items: [
      { href: "/prices", label: "Price history" },
      { href: "/knowledge", label: "Learning" },
    ],
  },
];

/** Bottom of the rail: administration and reference, not destinations in the workflow. */
const NAV_FOOTER = [
  { href: "/settings", label: "Settings" },
  { href: "/guide", label: "User guide" },
];

/**
 * `switcher` is a slot, not props: resolving which workspaces you can reach costs an engine
 * round trip (~0.9s measured), and inlining it here made every navigation wait for data that
 * the nav links themselves do not need. The layout streams it in through a Suspense boundary.
 */
export function Sidebar({ switcher, locale = "en" }: { switcher?: React.ReactNode; locale?: Locale }) {
  const pathname = usePathname();
  const t = translator(locale);
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
      {NAV_GROUPS.map((group, i) => (
        <div key={group.label ?? "primary"} className={i === 0 ? "" : "mt-5"}>
          {group.label && (
            <p className="px-3 pb-1.5 text-[11px] font-medium uppercase tracking-wide text-muted">
              {t(group.label)}
            </p>
          )}
          <ul className="flex flex-col gap-0.5">
            {group.items.map((item) => (
              <li key={item.href}>
                <Link
                  href={item.href}
                  data-active={pathname.startsWith(item.href) || undefined}
                  aria-current={pathname.startsWith(item.href) ? "page" : undefined}
                  // min-h-9 keeps every row a comfortable target without breaking the
                  // 280px rail's density (skill: touch-target-size).
                  className={`flex min-h-9 items-center rounded px-3 py-2 text-sm ${
                    pathname.startsWith(item.href)
                      ? "bg-primary-tint font-medium text-primary"
                      : "text-muted hover:bg-surface-alt hover:text-ink"
                  }`}
                >
                  {t(item.label)}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      ))}

      {/* Bottom of the rail: administration, reference, and a preference — none of them
          steps in the workflow, so they sit below it rather than competing with it. */}
      <div className="mt-auto pt-4">
        <ul className="flex flex-col gap-0.5">
          {NAV_FOOTER.map((item) => (
            <li key={item.href}>
              <Link
                href={item.href}
                data-active={pathname.startsWith(item.href) || undefined}
                aria-current={pathname.startsWith(item.href) ? "page" : undefined}
                className={`flex min-h-9 items-center rounded px-3 py-2 text-sm ${
                  pathname.startsWith(item.href)
                    ? "bg-primary-tint font-medium text-primary"
                    : "text-muted hover:bg-surface-alt hover:text-ink"
                }`}
              >
                {t(item.label)}
              </Link>
            </li>
          ))}
        </ul>
        <div className="px-2 pt-3">
          <LocaleToggle locale={locale} />
        </div>
      </div>
    </nav>
  );
}
