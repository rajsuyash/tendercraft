import { describe, expect, test } from "vitest";
import { readinessDestinations } from "./SubmissionMeter";

describe("the readiness meter's links", () => {
  test("it never links to the page it is on", () => {
    // 'Requirements' pointed at /tenders/{id}/readiness — the readiness page itself.
    expect(readinessDestinations("t1", { drafted: false }).map((l) => l.href))
      .not.toContain("/tenders/t1/readiness");
  });

  test("a destination with nothing in it is offered as disabled, with the reason", () => {
    const [proposal, score] = readinessDestinations("t1", { drafted: false });
    expect(proposal).toMatchObject({ href: "/proposals/t1", enabled: false });
    expect(proposal.reason).toBeTruthy();
    expect(score).toMatchObject({ enabled: false });
  });

  // Corrected from an earlier version of this test that gated the score link on a separate
  // `scored`/score_estimates flag. That was wrong: RubricCard on /proposals/[id]/score calls
  // POST /api/tenders/:id/rubric on every load and renders real content from the proposal's
  // sections alone — no estimate row required. Gating on a missing estimate made the disabled
  // reason ("Available once a proposal exists") false exactly when a proposal DID exist. Both
  // links share one signal: whether a proposal has been drafted.
  test("both open together as soon as a proposal is drafted", () => {
    expect(readinessDestinations("t1", { drafted: true }).every((l) => l.enabled)).toBe(true);
  });

  test("identifies the score destination by key, not by its label", () => {
    // The `data-open-score-meter` hook used to be selected with
    // `link.label === "Technical score"`. Renaming that button is exactly what happened when
    // the qualification verdict was removed, and a copy change would have silently dropped a
    // hook a design AC asserts on. The key is the identity; the label is copy.
    const [proposal, score] = readinessDestinations("t1", { drafted: true });
    expect(proposal.key).toBe("proposal");
    expect(score.key).toBe("score");
    expect(score.href).toBe("/proposals/t1/score");
  });

  test("no longer names the completeness measure a score", () => {
    // The engine stopped rendering a qualification verdict; the nav label pointing at the
    // same concept kept saying "Technical score" until the guide's own copy was fixed and
    // this one was found one file behind it.
    const labels = readinessDestinations("t1", { drafted: true }).map((l) => l.label);
    expect(labels).not.toContain("Technical score");
    expect(labels).toContain("Document completeness");
  });
});
