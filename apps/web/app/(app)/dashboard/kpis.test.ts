import { describe, expect, test } from "vitest";

import { countOrUnknown, formatKpi } from "./kpis";

/**
 * The bug these pin: `dashboard/page.tsx` shipped
 *
 *   { label: "Awaiting verification", value: 0 },
 *   { label: "Drafts in review",      value: 0 },
 *
 * as literals, next to a tile that was genuinely measured, styled identically. Verified against
 * production 2026-09-09: the workspace displaying "Awaiting verification 0" held 861
 * unconfirmed criteria.
 */

describe("a KPI never presents an unknown as a zero", () => {
  test("a real zero renders as zero", () => {
    expect(formatKpi(0)).toBe("0");
  });

  test("a real count renders as itself", () => {
    expect(formatKpi(861)).toBe("861");
  });

  test("an unreadable count renders as an em dash, not 0", () => {
    expect(formatKpi(null)).toBe("—");
    expect(formatKpi(undefined as never)).toBe("—");
  });

  test("zero and unknown do not render the same", () => {
    // The whole point. If these ever match, a failed count is indistinguishable from
    // "nothing to do" — which is how the original bug read to a user with 861 open items.
    expect(formatKpi(0)).not.toBe(formatKpi(null));
  });
});

describe("countOrUnknown maps a head-only count honestly", () => {
  test("a number is kept, including zero", () => {
    expect(countOrUnknown(0)).toBe(0);
    expect(countOrUnknown(42)).toBe(42);
  });

  test("null from a failed count is unknown, not zero", () => {
    // Supabase returns `count: null` when the request failed or sent no count header.
    // Coercing that to 0 would reintroduce the bug through the fallback rather than a literal.
    expect(countOrUnknown(null)).toBe(null);
    expect(countOrUnknown(undefined)).toBe(null);
  });
});
