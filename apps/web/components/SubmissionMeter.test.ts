import { describe, expect, test } from "vitest";
import { navFor } from "./SubmissionMeter";

describe("the readiness meter's links", () => {
  test("it never links to the page it is on", () => {
    // 'Requirements' pointed at /tenders/{id}/readiness — the readiness page itself.
    expect(navFor("t1", { drafted: false, scored: false }).map((l) => l.href))
      .not.toContain("/tenders/t1/readiness");
  });

  test("a destination with nothing in it is offered as disabled, with the reason", () => {
    const [proposal, score] = navFor("t1", { drafted: false, scored: false });
    expect(proposal).toMatchObject({ href: "/proposals/t1", enabled: false });
    expect(proposal.reason).toBeTruthy();
    expect(score).toMatchObject({ enabled: false });
  });

  test("a drafted proposal is reachable; its score still is not", () => {
    const [proposal, score] = navFor("t1", { drafted: true, scored: false });
    expect(proposal.enabled).toBe(true);
    expect(proposal.reason).toBeUndefined();
    expect(score.enabled).toBe(false);
  });

  test("both open once both exist", () => {
    expect(navFor("t1", { drafted: true, scored: true }).every((l) => l.enabled)).toBe(true);
  });
});
