import { describe, expect, test } from "vitest";

import { groupBySource, type VocabTerm } from "./BidVocabulary";

const terms: VocabTerm[] = [
  { term: "wire rope", source: "typed", origin: "", reach: 61 },
  { term: "oil indutry", source: "typed", origin: "", reach: 0 },
  { term: "IS 2266", source: "standard", origin: "Wire Rope (ONGC)", reach: 1 },
  { term: "Wire Rope Sling", source: "category", origin: "", reach: 4 },
];

describe("the bid vocabulary", () => {
  test("typed terms are editable and derived ones are not", () => {
    const g = groupBySource(terms);
    expect(g.typed.map((t) => t.term)).toEqual(["wire rope", "oil indutry"]);
    expect(g.derived.map((t) => t.term)).toEqual(["IS 2266", "Wire Rope Sling"]);
  });

  test("a term reaching nothing is surfaced, whatever its source", () => {
    // The whole reason reach is on this screen: a dead term and a quiet market look
    // identical. A typo matched 0 of 581 tenders here once and nothing said so.
    expect(groupBySource(terms).dead.map((t) => t.term)).toEqual(["oil indutry"]);
  });

  test("an empty vocabulary reports no dead terms rather than throwing", () => {
    const g = groupBySource([]);
    expect(g.typed).toEqual([]);
    expect(g.derived).toEqual([]);
    expect(g.dead).toEqual([]);
  });
});
