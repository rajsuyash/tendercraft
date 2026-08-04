import { describe, expect, it } from "vitest";

import {
  formatConfidence,
  formatCrore,
  formatDate,
  formatFYRange,
  formatINR,
  formatMoney,
  formatTurnover,
  sourceAnchor,
} from "./format";

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

describe("market-aware money", () => {
  it("keeps Indian grouping and the rupee for the Indian market", () => {
    expect(formatMoney(240000, "IN")).toBe("\u20b92,40,000");
    expect(formatMoney(240000, null)).toBe("\u20b92,40,000");
  });

  it("renders euros for the French market", () => {
    // Non-breaking spaces are what Intl emits for fr-FR; assert on digits and currency
    // rather than on the exact whitespace codepoints.
    const out = formatMoney(240000, "FR");
    expect(out).toContain("240");
    expect(out).toContain("\u20ac");
    expect(out).not.toContain("\u20b9");
  });

  it("labels the large unit per market without converting the number", () => {
    expect(formatTurnover(8.2, "IN")).toBe("\u20b98.2 Cr");
    expect(formatTurnover(8.2, "FR")).toBe("8,2 M\u20ac");
  });
});

describe("sourceAnchor", () => {
  it("names the document only when the caller passes one", () => {
    expect(sourceAnchor(4, "3.1")).toBe("p.4 · Cl. 3.1");
    expect(sourceAnchor(4, "3.1", "Annexure-II.pdf")).toBe("Annexure-II.pdf · p.4 · Cl. 3.1");
  });

  it("never doubles a prefix the extractor already supplied", () => {
    expect(sourceAnchor(22, "Annexure-VII")).toBe("p.22 · Annexure-VII");
  });

  it("renders an em dash rather than a page-less anchor", () => {
    expect(sourceAnchor(null, "4.1")).toBe("—");
  });
});
