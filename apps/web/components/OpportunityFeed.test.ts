import { describe, expect, test } from "vitest";

import { hasClosed } from "./OpportunityFeed";

/** A fixed instant, so these never depend on when they are run. */
const NOW = new Date("2026-08-25T12:00:00Z").getTime();

describe("hasClosed", () => {
  test("a deadline in the past has closed", () => {
    expect(hasClosed("2026-08-10T09:30:00Z", NOW)).toBe(true);
  });

  test("a deadline in the future has not", () => {
    expect(hasClosed("2026-09-30T09:30:00Z", NOW)).toBe(false);
  });

  test("a tender with no stated deadline is NOT treated as closed", () => {
    // The case the filter exists to get right. GeM does not always publish a closing date, and
    // hiding those would drop live opportunities on the strength of a missing field — the
    // silent-miss failure arriving through a convenience filter.
    expect(hasClosed(null, NOW)).toBe(false);
  });

  test("an unparseable date is not treated as closed either", () => {
    expect(hasClosed("not a date", NOW)).toBe(false);
  });

  test("a deadline later today is still open", () => {
    // Deadlines are time-of-day sensitive — GeM closes at 15:00 IST — so "today" must never
    // round down into "closed" and hide a tender someone could still bid on.
    expect(hasClosed("2026-08-25T18:00:00Z", NOW)).toBe(false);
  });
});
