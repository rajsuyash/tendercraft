import { describe, expect, it } from "vitest";

import { buildPastBidForm } from "./PastBidUpload";

/**
 * The upload lives in two places — the library panel and the reuse panel inside a draft — and
 * both go through this one builder. These tests pin the contract with POST /api/past-bids,
 * because the failure mode of a second copy is silent: a form that posts `files` instead of
 * `file`, or omits `outcome`, uploads "successfully" and mines nothing reusable.
 */
const file = (name: string) => new File(["x"], name, { type: "application/pdf" });

describe("buildPastBidForm", () => {
  it("repeats the `file` field so a package arrives as ONE bid", () => {
    const form = buildPastBidForm([file("nit.pdf"), file("annexure-ii.pdf")], "won");
    expect(form.getAll("file")).toHaveLength(2);
  });

  it("names the bid after the first file, without its extension", () => {
    // A fallback only: the engine prefers the identity the document states about itself.
    const form = buildPastBidForm([file("NIC-2025-eOffice.pdf")], "unknown");
    expect(form.get("name")).toBe("NIC-2025-eOffice");
  });

  it("sends the outcome the user chose, verbatim", () => {
    expect(buildPastBidForm([file("a.pdf")], "lost").get("outcome")).toBe("lost");
    expect(buildPastBidForm([file("a.pdf")], "won").get("outcome")).toBe("won");
  });

  it("defaults nothing — an unset outcome stays unknown rather than becoming a win", () => {
    // A guessed win would quietly rank what every future proposal reuses.
    expect(buildPastBidForm([file("a.pdf")], "unknown").get("outcome")).toBe("unknown");
  });

  it("survives an empty selection without inventing a name", () => {
    expect(buildPastBidForm([], "unknown").get("name")).toBe("");
  });
});
