import { describe, expect, it } from "vitest";

import { formatCrore, formatDate } from "./format";

/**
 * The first tests in this app. `pnpm test:evaluate` used to exit silently — there was no
 * `test` script and no test file — while the product it covers is the one sold to a government
 * buyer. Money formatting is the right place to start: every figure an evaluation report,
 * ranking table or award letter shows passes through here.
 */
describe("formatCrore", () => {
  it("renders rupees as crore to two places", () => {
    // The live seeded winning bid. If this changes, a figure on the award letter changed.
    expect(formatCrore(38_600_000)).toBe("₹3.86 Cr");
    expect(formatCrore(41_200_000)).toBe("₹4.12 Cr");
  });

  it("accepts the string PostgREST actually returns for a numeric column", () => {
    // amount_inr arrives as a string over PostgREST; passing it straight through must work,
    // because the alternative is every caller remembering to Number() it and one forgetting.
    expect(formatCrore("38600000")).toBe("₹3.86 Cr");
  });

  it("renders an unreadable amount as an em dash, never as a number", () => {
    // "NaN Cr" is ugly; "₹0.00 Cr" on a live bid is a false figure in a procurement record.
    expect(formatCrore(Number.NaN)).toBe("—");
    expect(formatCrore("not a number")).toBe("—");
    expect(formatCrore(Number.POSITIVE_INFINITY)).toBe("—");
  });

  it("treats its argument as rupees, not paise", () => {
    // The signature said `paise` while the maths said rupees. A crore of rupees is 10^7
    // rupees; had the name been right, every figure would have been 100x too small.
    expect(formatCrore(10_000_000)).toBe("₹1.00 Cr");
  });

  it("renders sub-crore amounts to two places, and anything under ₹50,000 as zero", () => {
    // Documented limitation, not a bug to fix today: every caller passes `amount_inr`, a bid
    // price, which is always crore-scale. But an EMD is routinely ₹10,000–₹50,000, so if this
    // helper is ever reused for one it will print "₹0.00 Cr" for a real deposit. This test is
    // here to make that visible to whoever does it, rather than to bless it.
    expect(formatCrore(200_000)).toBe("₹0.02 Cr");
    expect(formatCrore(150_000)).toBe("₹0.01 Cr");
    expect(formatCrore(49_999)).toBe("₹0.00 Cr");
  });
});

describe("formatDate", () => {
  it("renders DD/MM/YYYY, the convention an Indian officer reads", () => {
    expect(formatDate("2026-08-04T09:30:00Z")).toBe("04/08/2026");
  });

  it("renders a missing date as an em dash", () => {
    expect(formatDate(null)).toBe("—");
    expect(formatDate(undefined)).toBe("—");
    expect(formatDate("")).toBe("—");
  });

  it("renders an unparseable date as an em dash rather than NaN/NaN/NaN", () => {
    // A deadline that renders as "NaN/NaN/NaN" on a tender screen is worse than absent.
    expect(formatDate("not a date")).toBe("—");
  });
});
