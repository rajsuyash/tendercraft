import { describe, expect, it } from "vitest";

import { istInputValue } from "./ReadinessHub";

/** The deadline a bid manager types is an IST wall-clock time, and the column is a
 *  timestamptz. Getting the conversion wrong by 5.5 hours is a missed submission, so both
 *  directions are pinned here: what the input shows, and what the save sends. */
describe("istInputValue", () => {
  it("shows the IST wall-clock time, not UTC", () => {
    // 09:30 UTC is 15:00 IST — the hour the portal enforces.
    expect(istInputValue("2026-10-02T09:30:00Z")).toBe("2026-10-02T15:00");
  });

  it("round-trips the string the save handler builds", () => {
    // saveDeadline sends `${value}:00+05:30`; reading it back must give the same value.
    const typed = "2026-10-02T15:00";
    expect(istInputValue(`${typed}:00+05:30`)).toBe(typed);
  });

  it("crosses midnight in the right direction", () => {
    // 21:00 UTC on the 1st is 02:30 IST on the 2nd.
    expect(istInputValue("2026-10-01T21:00:00Z")).toBe("2026-10-02T02:30");
  });

  it("renders nothing rather than a guess when there is no deadline", () => {
    expect(istInputValue(null)).toBe("");
    expect(istInputValue(undefined)).toBe("");
    expect(istInputValue("not a date")).toBe("");
  });
});
