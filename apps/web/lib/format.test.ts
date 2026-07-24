import { describe, expect, it } from "vitest";

import { formatConfidence, formatCrore, formatDate, formatFYRange, formatINR } from "./format";

describe("formatINR", () => {
  it("groups in the Indian system (lakh/crore)", () => {
    expect(formatINR(240000)).toBe("₹2,40,000");
    expect(formatINR(5900)).toBe("₹5,900");
    expect(formatINR(12500000)).toBe("₹1,25,00,000");
  });
  it("rounds to whole rupees", () => {
    expect(formatINR(240000.4)).toBe("₹2,40,000");
  });
  it("rejects non-finite input", () => {
    expect(() => formatINR(Infinity)).toThrow(RangeError);
  });
});

describe("formatCrore", () => {
  it("trims trailing zeros", () => {
    expect(formatCrore(10)).toBe("₹10 Cr");
    expect(formatCrore(8.2)).toBe("₹8.2 Cr");
    expect(formatCrore(1.8)).toBe("₹1.8 Cr");
  });
  it("keeps two significant decimals when present", () => {
    expect(formatCrore(3.45)).toBe("₹3.45 Cr");
  });
  it("rejects non-finite input", () => {
    expect(() => formatCrore(NaN)).toThrow(RangeError);
  });
});

describe("formatDate", () => {
  it("zero-pads to DD/MM/YYYY", () => {
    expect(formatDate(new Date(2026, 7, 14))).toBe("14/08/2026");
    expect(formatDate(new Date(2026, 0, 3))).toBe("03/01/2026");
  });
  it("rejects an invalid Date", () => {
    expect(() => formatDate(new Date("nope"))).toThrow(RangeError);
  });
});

describe("formatFYRange", () => {
  it("joins distinct years with an en-dash", () => {
    expect(formatFYRange("FY23", "FY25")).toBe("FY23–FY25");
  });
  it("collapses an equal range to one label", () => {
    expect(formatFYRange("FY24", "FY24")).toBe("FY24");
  });
});

describe("formatConfidence", () => {
  it("renders two decimals", () => {
    expect(formatConfidence(0.8)).toBe("0.80");
    expect(formatConfidence(0.615)).toBe("0.61");
  });
  it("rejects out-of-range confidence", () => {
    expect(() => formatConfidence(1.2)).toThrow(RangeError);
    expect(() => formatConfidence(-0.1)).toThrow(RangeError);
  });
});
