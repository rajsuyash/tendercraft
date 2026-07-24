# /design-review — verify the built UI against docs/DESIGN_SPEC.md

Usage: `/design-review [S<k> | all]` (default: screens touched by the current milestone's diff; `all` for the whole-app pass).

You are reviewing implementation against an **approved design contract**, not offering opinions. The spec is `docs/DESIGN_SPEC.md`; reference renders are in `design/reference/`; tokens in `design/tokens.json`. If the spec's §I `prd.sha256` doesn't match the PRD on disk (`tendercraft-PRD.md`), STOP and report the spec is stale — never review against a moved contract.

## Per screen in scope

1. Read the screen's §E spec and its `S#-D#` ACs (+ the global `GLB-D#` set from §F/§H).
2. Navigate to the screen's route with the browser tooling this repo has (gstack /browse preferred; Playwright MCP fallback; sign in as the seeded fixture user where the route requires auth). Dev server per CLAUDE.md.
3. **Capture evidence**: screenshot at the default viewport AND at each breakpoint a design AC names. Save to `.claude/verify-artifacts/design/S<k>-<state>-<width>.png`.
4. **Check each design AC by its stated method**:
   - *DOM assertion* → assert the selector/attribute (e.g. `[data-empty-state]`, `[data-ai-watermark]`, `[data-lock-blocked-count]`) exists/behaves as written. Drive the state honestly: clear/seed fixtures for empty, block or fail the named network call for error, throttle for loading — never fake a state by editing the DOM.
   - *Screenshot* → compare capture vs `design/reference/S<k>-*.png` for the properties the AC names (layout collapse, region order, truncation). This is a structural comparison against the AC's words, not a pixel diff — token-true color/spacing shifts are fine; a missing region or broken breakpoint is not.
5. **Token conformance (sampled)**: computed styles of the primary action, headings, and surfaces resolve to §C token values (via the CSS variables / Tailwind theme the scaffold wired). Verdict chips must resolve to the reserved semantic tokens (success/danger/warning). Hardcoded off-token hexes or font stacks = FAIL with file:line.
6. **States exist**: every state marked designed/specified in §D is reachable and non-blank. An unhandled error case rendering a white screen is an automatic FAIL against its screen.

## Report format

```
DESIGN REVIEW — <scope> · spec sha ok
 S7 /tenders/:id/analysis  S7-D1 PASS · S7-D2 PASS · S7-D3 FAIL (0.61-confidence row renders Pass chip — violates C-AC5 UI face)
 S9 /proposals/:id         S9-D1 PASS · S9-D2 FAIL (₹8.2 Cr rendered as editable text, no [data-transclusion])
 GLB-D1 (contrast, sampled)  PASS
 VERDICT: n/m design ACs pass · artifacts: .claude/verify-artifacts/design/
```

FAILs route into the standard failure playbook (they are verification failures like any other layer). Never resolve a FAIL by weakening the design AC or editing the reference render — spec changes are stitch-ux-designer re-design mode, a human decision.
