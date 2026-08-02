import { describe, expect, it } from "vitest";

import { splitKeywords, unlikelyKeywords } from "./ProfileForm";

/**
 * Regression tests for a live incident: USHA MARTIN INDIA entered two capability "keywords"
 * that were prose, switched on the opt-in keyword gate, and their feed went to zero. All 335
 * swept tenders were hidden by a rule they had authored, and the screen told them to sweep GeM
 * again — the one action that could not help.
 */
describe("splitKeywords", () => {
  it("splits on slashes, which is how the live workspace listed its terms", () => {
    // Entered as ONE keyword; matching is per whole term, so it matched nothing at all.
    expect(
      splitKeywords("expertise in elevator / crane / oil indutry/ mines / general engineering"),
    ).toEqual([
      "expertise in elevator",
      "crane",
      "oil indutry",
      "mines",
      "general engineering",
    ]);
  });

  it("still splits on commas, and on newlines and semicolons", () => {
    expect(splitKeywords("cctv, surveillance\nnetworking; amc")).toEqual([
      "cctv",
      "surveillance",
      "networking",
      "amc",
    ]);
  });

  it("keeps genuine multi-word terms intact", () => {
    // Only the separators changed. "wire rope" and "structured cabling" are real keywords and
    // must survive — a tender title does contain them.
    expect(splitKeywords("wire rope, structured cabling")).toEqual([
      "wire rope",
      "structured cabling",
    ]);
  });

  it("lower-cases and de-duplicates", () => {
    expect(splitKeywords("CCTV, cctv,  Cctv ")).toEqual(["cctv"]);
  });

  it("ignores empty fragments rather than storing blanks", () => {
    // A blank keyword would match every tender, which is the opposite failure and worse.
    expect(splitKeywords(",, /  ;\n")).toEqual([]);
    expect(splitKeywords("")).toEqual([]);
  });
});

describe("unlikelyKeywords", () => {
  it("flags a sentence, so the form can warn before the feed empties", () => {
    expect(unlikelyKeywords(["steel wire rope manufacturing and supply services"])).toEqual([
      "steel wire rope manufacturing and supply services",
    ]);
  });

  it("does not flag ordinary terms", () => {
    expect(unlikelyKeywords(["cctv", "wire rope", "structured cabling", "amc"])).toEqual([]);
  });

  it("does not flag a four-word term — the boundary is inclusive", () => {
    // "steel wire rope manufacturing" is borderline and legitimate; warn above it, not at it.
    expect(unlikelyKeywords(["steel wire rope manufacturing"])).toEqual([]);
  });
});
