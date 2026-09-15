import { describe, expect, test } from "vitest";
import { ocrNote, type Readiness } from "./ReadinessHub";

const base = { summary: {}, items: [] } as unknown as Readiness;

describe("what the readiness screen says about the scanned pages", () => {
  test("an unfinished pass claims nothing", () => {
    // NULL covers three cases at once — still running, never ran (no toolchain in this
    // deployment), and raised. None of them is something to tell a user, and "being read
    // now" would be a promise this screen cannot keep.
    expect(ocrNote({ ...base, ocr_completed_at: null, ocr_pages_recovered: null })).toBeNull();
  });

  test("pages that were read are reported, and never as something to re-upload", () => {
    const note = ocrNote({ ...base, ocr_completed_at: "2026-09-15T10:00:00Z", ocr_pages_recovered: 77 });
    expect(note?.text).toContain("77");
    // The whole point of task A4: the upload screen listed these pages as unreadable and told
    // the user to re-upload them. They have since been read.
    expect(note?.reupload).toBe(false);
  });

  test("one page reads as one page", () => {
    const note = ocrNote({ ...base, ocr_completed_at: "2026-09-15T10:00:00Z", ocr_pages_recovered: 1 });
    expect(note?.text).toContain("1 scanned page ");
    expect(note?.text).not.toContain("pages");
  });

  test("a pass that recovered nothing keeps the re-upload advice", () => {
    // 0 is an answer, not an absence: the pass ran and the scans were unreadable. This is the
    // one state where telling the user to re-upload is honest.
    const note = ocrNote({ ...base, ocr_completed_at: "2026-09-15T10:00:00Z", ocr_pages_recovered: 0 });
    expect(note?.reupload).toBe(true);
    expect(note?.text).toContain("could not be read");
  });
});
