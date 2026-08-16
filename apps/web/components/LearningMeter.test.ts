import { describe, expect, it } from "vitest";

import { readTrend } from "./LearningMeter";

/**
 * The edit trend is the only number on S21 that can say the system is NOT learning, which
 * makes it the one worth pinning. The failure mode is quiet in both directions: a verdict
 * rendered on too little data, or a real regression averaged away.
 */
const at = (...ratios: number[]) => ratios.map((rewrite_ratio) => ({ rewrite_ratio }));

describe("readTrend", () => {
  it("says nothing until there are enough edits to compare", () => {
    // Below the floor "flat" would be a claim about learning that was never measured.
    expect(readTrend(at(0.9, 0.1, 0.9), 5).direction).toBe("unknown");
    expect(readTrend([], 5).direction).toBe("unknown");
  });

  it("reports falling rewrite as improvement", () => {
    const t = readTrend(at(0.8, 0.9, 0.8, 0.7, 0.2, 0.1, 0.2, 0.1, 0.2, 0.1), 5);
    expect(t.direction).toBe("improving");
    expect(t.late).toBeLessThan(t.early);
  });

  it("reports rising rewrite honestly rather than hiding it", () => {
    expect(readTrend(at(0.1, 0.2, 0.1, 0.2, 0.1, 0.8, 0.9, 0.8, 0.9, 0.8), 5).direction).toBe(
      "worsening",
    );
  });

  it("calls a small wobble flat instead of a trend", () => {
    expect(readTrend(at(0.5, 0.52, 0.48, 0.5, 0.51, 0.49, 0.5, 0.52, 0.48, 0.5), 5).direction).toBe(
      "flat",
    );
  });

  it("is not swung by one section that was scrapped outright", () => {
    // One 100%-rewritten section first and one untouched last, everything else identical.
    // Scrapping a section is normal, and with means it moves a five-sample half by 0.1 —
    // twice the noise floor — so this workspace would be reported as improving. It is flat.
    expect(readTrend(at(1.0, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.0), 5).direction).toBe(
      "flat",
    );
  });

  it("still reports a real improvement that one outlier is hiding", () => {
    // Genuinely falling, with a single total rewrite dropped into the recent half.
    expect(readTrend(at(0.8, 0.9, 0.8, 0.9, 0.8, 0.1, 1.0, 0.2, 0.1, 0.2), 5).direction).toBe(
      "improving",
    );
  });
});
