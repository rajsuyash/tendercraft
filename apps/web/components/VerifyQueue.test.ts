import { describe, expect, test } from "vitest";

import { blocksLock, type Criterion } from "./VerifyQueue";

/** This rule must agree with the SERVER's, which is `deterministic/lock.py::evaluate_lock`
 *  plus `types.SourceAnchor.is_resolvable` (`page > 0`). It did not, nothing tested it on
 *  either side of the wire, and the disagreement disabled the Lock button permanently on any
 *  tender whose requirements sit in unnumbered prose. `tests/test_lock_gate.py::
 *  test_a_page_without_a_clause_number_is_still_resolvable` is this test's opposite number. */
const base: Criterion = {
  id: "c-1",
  verbatim_text: "Average annual turnover of ₹10 Cr",
  category: "financial",
  requirement_level: "mandatory",
  confidence: 0.95,
  confirmed: false,
  anchor_page: 12,
  anchor_clause: "4.1(a)",
  anchor_document: null,
};

describe("blocksLock", () => {
  test("a page with no clause number is still a resolvable anchor", () => {
    // The whole defect. Real tenders state obligations in prose with no clause number.
    expect(blocksLock({ ...base, anchor_clause: null })).toBe(false);
    expect(blocksLock({ ...base, anchor_clause: "" })).toBe(false);
  });

  test("no page at all does block", () => {
    expect(blocksLock({ ...base, anchor_page: null })).toBe(true);
  });

  test("an unconfirmed sub-0.80 extraction blocks", () => {
    expect(blocksLock({ ...base, confidence: 0.61 })).toBe(true);
  });

  test("confirming a low-confidence extraction clears it", () => {
    expect(blocksLock({ ...base, confidence: 0.61, confirmed: true })).toBe(false);
  });

  test("exactly 0.80 needs no confirmation — the threshold is not inclusive", () => {
    // Mirrors tests/test_lock_gate.py's boundary case exactly.
    expect(blocksLock({ ...base, confidence: 0.8 })).toBe(false);
    expect(blocksLock({ ...base, confidence: 0.79 })).toBe(true);
  });

  test("a high-confidence anchored criterion never blocks", () => {
    expect(blocksLock(base)).toBe(false);
  });
});
