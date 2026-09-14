# Linux OCR, and a Readiness Screen That Says One Thing — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make scanned tender pages readable in production, and make the readiness screen offer one action and one number instead of four buttons and two progress bars.

**Architecture:** Two independent parts that happen to meet in one place — the readiness screen's heading is a filename *because* page one is a scan nobody can read. Part A gives `app/ocr.py` a Linux adapter and wires it into ingest, behind a measurement that decides whether free Tesseract clears the PRD's accuracy bar or whether a paid provider is actually needed. Part B rewrites the readiness screen's two summary cards into one.

**Tech Stack:** Python 3.12 / FastAPI / pytest via `uv`; Tesseract + poppler in the engine image; Next.js 15 / TypeScript / Vitest via `pnpm`.

---

## What is actually true today — measured, not assumed

**Part A facts.**

| Fact | Evidence |
|---|---|
| `app/ocr.py` is imported by **nothing** but `tests/test_ocr.py` | `grep -rln "from .ocr\|import ocr" services/engine/` |
| The engine image installs neither `pdftoppm` nor `swiftc` | `services/engine/Dockerfile` has no `apt-get` layer at all |
| So `ocr.available()` is `False` in production, by construction | `available()` requires both |
| `OCR_PROVIDER=documentai` in `.env` is read by **no code** | `grep -rn OCR_PROVIDER services/ apps/` finds only a stale build artefact |
| It is not set on Cloud Run either | `gcloud run services describe` env list |
| A page under 20 characters is dropped before extraction | `ingest.py:36` `_MIN_CHARS_PER_PAGE = 20`, used at `:217` |
| On the real customer folder, **52% of pages carried no extractable text** | recorded in `app/ocr.py`'s own docstring, measured 2026-09-09: 480 pages, 48% legible |
| The unreadable half was almost entirely the bidder's own evidence | same docstring — certifications, licences, local-content declarations |
| A measurement corpus exists on disk | `Sample Tender Usha Martin/` — 33 PDFs across 5 tender folders |

The consequence that matters: the unreadable half is exactly the material the answer library, the house style and the citation corpus are built from. It is also why the tender in the screenshot is titled `all_bid_docs_…fcd2.pdf` — `deterministic/tender_meta.display_title` falls back to the filename only when the parser found no title, and it found none because page one is an image.

**Part B facts.** On `/tenders/{id}/readiness`, before analysis has run:

| Control | Destination | State |
|---|---|---|
| `Requirements` | `/tenders/{id}/readiness` | **the page it is on** — a self-link |
| `Proposal` | `/proposals/{id}` | empty; nothing drafted |
| `Technical score` | `/proposals/{id}/score` | empty; nothing to score |
| `Analyze & match my knowledge base` | `POST /api/tenders/{id}/prepare` | the only control that does anything |

`/proposals/{id}` genuinely takes a **tender** id — "one proposal per tender", stated at `apps/web/app/(app)/proposals/[id]/page.tsx:6`. Those two links are correct, not broken. Only `Requirements` is a no-op.

After analysis runs there are **two** progress summaries stacked: `SubmissionMeter`'s five-stage bar, and a P0/P1/P2/covered strip at `ReadinessHub.tsx:206-220`. `SubmissionMeter`'s own docstring says it exists to replace "four counters that described the same bid and disagreed". It replaced some of them and left this one above it.

---

## Part A — make a scan readable

### Task A1: Measure Tesseract before choosing a provider

**No code changes. The deliverable is a number and a decision.**

This task exists because the alternative costs money and the PRD has not picked one: `docs/PRD.md:26` still reads `OCR provider | TODO: pick (Google Document AI vs AWS Textract vs Surya) — PRD A-FR1/A-FR6 needs ≥98% word-accuracy estimation`. Tesseract is free and apt-installable; Document AI is roughly $1.50 per 1,000 pages. Do not spend before measuring, and do not adopt the free one without checking it clears the bar either.

**Files:**
- Create: `tools/measure-ocr.py` (a measurement script, kept — it will be re-run when the provider is revisited)
- Create: `docs/ocr-measurement.md` (the result)

- [ ] **Step 1: Build a throwaway Linux image with both candidates**

Tesseract is not installed on the dev Mac and the production image is Linux, so measure where it will run. Write `tools/ocr-measure.Dockerfile`:

```dockerfile
# Throwaway image for the OCR provider measurement (Task A1). NOT the production image —
# the production Dockerfile change is Task A2 and installs only what the chosen provider needs.
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
      poppler-utils tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir pypdf
WORKDIR /work
```

- [ ] **Step 2: Write the measurement script**

`tools/measure-ocr.py` must report, per PDF and in total:

- pages total, pages with an extractable text layer (`len(text) >= 20`, the same threshold `ingest.py` uses — do not invent a second definition)
- of the pages WITHOUT a text layer: how many Tesseract recovered to `>= 20` characters
- wall-clock seconds per OCR'd page, and total
- a sample of recovered text per document, so a human can judge quality rather than trust a character count

```python
#!/usr/bin/env python3
"""How much of a real tender folder can Tesseract actually read, and how fast?

Run inside the measurement image (tools/ocr-measure.Dockerfile), because the production
engine is Linux and a number measured on a Mac says nothing about it.

    docker build -f tools/ocr-measure.Dockerfile -t tc-ocr-measure .
    docker run --rm -v "$PWD/Sample Tender Usha Martin:/work/corpus:ro" \
      -v "$PWD/tools:/work/tools:ro" tc-ocr-measure \
      python /work/tools/measure-ocr.py /work/corpus

A character count is NOT quality. The samples exist so a human reads them before anyone
decides this clears A-FR6's accuracy bar.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import time

from pypdf import PdfReader

MIN_CHARS = 20  # ingest.py:_MIN_CHARS_PER_PAGE — one definition of "legible", not two
DPI = 200       # ocr.py:DPI


def text_layer(pdf: pathlib.Path) -> list[str]:
    try:
        return [(p.extract_text() or "").replace("\x00", "") for p in PdfReader(pdf).pages]
    except Exception as exc:  # noqa: BLE001 — a corrupt file is a result, not a crash
        print(f"  !! unreadable PDF: {exc}")
        return []


def ocr_page(pdf: pathlib.Path, page: int, work: pathlib.Path) -> tuple[str, float]:
    stem = work / f"p{page}"
    t0 = time.monotonic()
    subprocess.run(["pdftoppm", "-png", "-r", str(DPI), "-f", str(page), "-l", str(page),
                    str(pdf), str(stem)], check=True, capture_output=True, timeout=120)
    img = sorted(work.glob(f"p{page}-*.png"))
    if not img:
        return "", time.monotonic() - t0
    out = subprocess.run(["tesseract", str(img[0]), "stdout"],
                         check=True, capture_output=True, timeout=120, text=True)
    return out.stdout, time.monotonic() - t0


def main(root: str) -> None:
    pdfs = sorted(pathlib.Path(root).rglob("*.pdf"))
    tot_pages = tot_blank = tot_recovered = 0
    tot_secs = 0.0
    for pdf in pdfs:
        layers = text_layer(pdf)
        if not layers:
            continue
        blank = [i for i, t in enumerate(layers, 1) if len(t.strip()) < MIN_CHARS]
        recovered, secs, sample = 0, 0.0, ""
        with tempfile.TemporaryDirectory() as tmp:
            for page in blank:
                try:
                    text, dt = ocr_page(pdf, page, pathlib.Path(tmp))
                except Exception as exc:  # noqa: BLE001
                    print(f"  !! page {page}: {exc}")
                    continue
                secs += dt
                if len(text.strip()) >= MIN_CHARS:
                    recovered += 1
                    if not sample:
                        sample = " ".join(text.split())[:240]
        tot_pages += len(layers); tot_blank += len(blank)
        tot_recovered += recovered; tot_secs += secs
        print(f"\n{pdf.relative_to(root)}")
        print(f"  pages {len(layers)} · no text layer {len(blank)} · recovered {recovered}"
              f" · {secs:.1f}s ({secs/max(1,len(blank)):.1f}s/page)")
        if sample:
            print(f"  sample: {sample}")

    print("\n" + "=" * 72)
    print(f"PDFs {len(pdfs)} · pages {tot_pages}")
    print(f"no text layer      {tot_blank} ({tot_blank/max(1,tot_pages):.0%})")
    print(f"recovered by OCR   {tot_recovered} ({tot_recovered/max(1,tot_blank):.0%} of those)")
    print(f"still unreadable   {tot_blank - tot_recovered}")
    print(f"OCR time           {tot_secs:.0f}s total · {tot_secs/max(1,tot_blank):.1f}s/page")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "corpus")
```

- [ ] **Step 3: Run it and read the samples**

```bash
docker build -f tools/ocr-measure.Dockerfile -t tc-ocr-measure .
docker run --rm -v "$PWD/Sample Tender Usha Martin:/work/corpus:ro" \
  -v "$PWD/tools:/work/tools:ro" tc-ocr-measure \
  python /work/tools/measure-ocr.py /work/corpus
```

**Read at least five recovered samples yourself.** A recovery rate is a character count, and a character count cannot tell a clean certificate from confident gibberish. This is the step the PRD's "≥98% word-accuracy estimation" actually means, and no number substitutes for looking.

- [ ] **Step 4: Write the decision down**

Create `docs/ocr-measurement.md` recording: the date, the corpus (33 PDFs, 5 tenders), the table above, the samples you read, and a one-line verdict.

**Decision rule, fixed in advance so the result cannot be rationalised:**
- Recovery **≥ 90%** of no-text-layer pages AND the samples are clean prose → adopt Tesseract, continue to A2.
- Recovery **< 70%**, or samples are garbled on the bidder's own certificates → Tesseract does not clear the bar; **stop and escalate to the human with the numbers.** Do not silently adopt a paid provider — that is a spend decision with an owner.
- Between the two → escalate with the samples and let a human decide. Do not pick for them.

Also record seconds per page. Task A3 needs it: ingest is synchronous in the request, so a per-page cost above ~2s makes a 60-page scan a two-minute upload and changes the design.

**Gate: do not start A2 until A1's verdict is written down and, if it escalated, answered.**

### Task A2: A Linux adapter behind the existing seam

Only if A1 chose Tesseract. If it chose a hosted provider, this task is rewritten around that provider's client and the cost ceiling moves with it — escalate rather than improvising.

**Files:**
- Modify: `services/engine/Dockerfile`
- Modify: `services/engine/app/ocr.py`
- Modify: `services/engine/tests/test_ocr.py`

- [ ] **Step 1: Write the failing test**

Append to `services/engine/tests/test_ocr.py`:

```python
class TestTheLinuxAdapter:
    """`app/ocr.py` shipped macOS-only and was wired to nothing, so production read no scans
    at all. The seam it already exposes — `available()` and `ocr_pdf_pages` — is unchanged;
    only what sits behind it is new.
    """

    def test_tesseract_makes_ocr_available_without_swift(self, monkeypatch):
        from app import ocr

        monkeypatch.setattr(ocr.shutil, "which",
                            lambda name: f"/usr/bin/{name}" if name in
                            ("pdftoppm", "tesseract") else None)
        assert ocr.available() is True, "a Linux box with poppler+tesseract can OCR"

    def test_no_tesseract_means_unavailable_not_an_error(self, monkeypatch):
        # "No OCR here" is an ordinary deployment fact. Callers check; they never catch.
        from app import ocr

        monkeypatch.setattr(ocr.shutil, "which",
                            lambda name: "/usr/bin/pdftoppm" if name == "pdftoppm" else None)
        assert ocr.available() is False

    def test_each_page_is_read_independently(self, monkeypatch, tmp_path):
        """One subprocess per page, so a single unreadable page cannot desynchronise the rest.

        The macOS adapter batched pages and split on a record separator, then discarded the
        WHOLE batch when the block count disagreed — correct, but it meant one bad page cost
        sixty. Per-page removes the protocol entirely.
        """
        from app import ocr

        calls: list[list[str]] = []

        def fake_run(argv, **kw):
            calls.append(argv)
            if argv[0] == "pdftoppm":
                page = argv[argv.index("-f") + 1]
                (tmp_path / f"p{page}-1.png").write_bytes(b"png")
                return subprocess.CompletedProcess(argv, 0, b"", b"")
            if "2" in argv[1]:  # page 2's image fails to read
                raise subprocess.CalledProcessError(1, argv)
            return subprocess.CompletedProcess(argv, 0, "RECOVERED TEXT WELL OVER THE FLOOR", "")

        monkeypatch.setattr(ocr.tempfile, "mkdtemp", lambda **kw: str(tmp_path))
        monkeypatch.setattr(ocr.subprocess, "run", fake_run)
        monkeypatch.setattr(ocr, "available", lambda: True)

        out = ocr.ocr_pdf_pages(b"%PDF-", [1, 2, 3])

        assert set(out) == {1, 3}, "page 2 failing must not take 1 and 3 with it"
        assert all("RECOVERED" in t for t in out.values())
```

Add `import subprocess` at the top of that test file if absent.

- [ ] **Step 2: Run to verify it fails**

`cd services/engine && uv run pytest tests/test_ocr.py -v` — expect the three new tests to fail.

- [ ] **Step 3: Replace the adapter**

In `services/engine/app/ocr.py`, delete `_ADAPTER_SRC`, `_BUILT`, `_binary()` and `_PAGE_BREAK`, and replace `available()` and the text-reading half of `ocr_pdf_pages`:

```python
#: The OCR engine. Tesseract because A1 measured it against the real corpus and it cleared
#: the bar at zero marginal cost; `docs/ocr-measurement.md` carries the numbers and the
#: samples a human read. Revisit with that script, not with an opinion.
_TESSERACT = "tesseract"


def available() -> bool:
    """Can this process OCR at all?

    Callers must check rather than catch: "no OCR here" is an ordinary deployment fact, not
    an error, and a page that could not be read must look the same as it does today.
    """
    return bool(shutil.which("pdftoppm")) and bool(shutil.which(_TESSERACT))
```

and, inside `ocr_pdf_pages`, replace the batched adapter call with a per-page read:

```python
        out: dict[int, str] = {}
        for page, image in rendered:
            try:
                proc = subprocess.run(
                    [_TESSERACT, str(image), "stdout"],
                    check=True, capture_output=True, timeout=TIMEOUT_S, text=True,
                )
            except (subprocess.SubprocessError, OSError) as exc:
                # One page, one failure. The batched adapter discarded all sixty when its
                # page-break protocol disagreed; per-page has no protocol to disagree with.
                log.warning("OCR failed on page %d: %s", page, exc)
                continue
            # NUL bytes: Postgres text cannot store one (app/ingest.parse_pdf_pages).
            text = proc.stdout.replace("\x00", "").strip()
            if text:
                out[page] = text
        return out
```

Keep the module docstring's WHY, SAFETY and COST sections, updating them: the safety argument (fixed argv, no shell, paths this module owns, bounded by pages/DPI/timeout) is unchanged and still true; the cost is still zero; the "macOS-only, Linux is M2" paragraph is now wrong and must go.

- [ ] **Step 4: Install the toolchain in the image**

In `services/engine/Dockerfile`, after the `FROM` and before the dependency layer:

```dockerfile
# OCR. Measured against the real customer corpus before being chosen — docs/ocr-measurement.md.
# Without these two binaries `ocr.available()` is False and every scanned page stays unread,
# which was production's behaviour until this line existed: 52% of one real tender folder.
# `--no-install-recommends` keeps this to roughly 60 MB rather than pulling X11.
RUN apt-get update && apt-get install -y --no-install-recommends \
      poppler-utils tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*
```

Put it before `COPY pyproject.toml` so it caches independently of dependency changes.

- [ ] **Step 5: Verify the image can actually OCR**

Building is not evidence. Run it:

```bash
cd services/engine && docker build -t tc-engine-ocr .
docker run --rm tc-engine-ocr python -c "from app import ocr; print('available:', ocr.available())"
```

Expected: `available: True`. If it prints False, the packages did not land and every later step is theatre.

- [ ] **Step 6: Run the suite and commit**

`cd services/engine && uv run pytest -q && uv run ruff check`

```bash
git add services/engine/Dockerfile services/engine/app/ocr.py services/engine/tests/test_ocr.py
git commit -m "feat(ocr): a Linux adapter, so production can read a scan at all

app/ocr.py shipped macOS-only and was imported by nothing but its own test, so
every scanned page in production was dropped before extraction — 52% of one real
customer folder, almost all of it the bidder's own certificates and licences.

Tesseract chosen on measurement, not preference (docs/ocr-measurement.md).
Per-page reads replace the batched page-break protocol: one unreadable page
cost all sixty under the old shape."
```

End every commit body in this plan with:

```
Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01MuWov4KGAatEytGg87MJJg
```

### Task A3: Wire OCR into ingest — and decide where it runs

**The constraint that shapes this task.** `POST /api/tenders/ingest` runs `_process_ingest` in a threadpool and the uploader waits for it. A1 measured seconds per OCR page. Multiply by the scans in a real package before choosing:

- **under ~2s/page** → OCR inline during ingest. A 20-page package with 10 scans adds ~20s to an upload that already runs tens of seconds. Acceptable, and it keeps criteria extraction correct on the first pass.
- **above that** → inline is wrong. Escalate to the human with the number rather than shipping a two-minute upload. The fallback shape is a `jobs` table and a re-extract pass, which is a bigger change than this task and should not be smuggled in.

State which branch you took and the number behind it.

**Files:**
- Modify: `services/engine/app/ingest.py`
- Modify: `services/engine/app/tenders.py`
- Create: `services/engine/tests/test_ingest_ocr.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Scanned pages must reach the extractor, not be dropped before it.

`ingest_pages` drops any page under 20 characters (`_MIN_CHARS_PER_PAGE`) — correct when
there is nothing to read, and a silent 52% data loss when OCR exists and nobody called it.
"""

from __future__ import annotations

from app import ingest


def test_a_scanned_page_is_ocred_before_the_legibility_filter(monkeypatch):
    monkeypatch.setattr(ingest.ocr, "available", lambda: True)
    monkeypatch.setattr(ingest.ocr, "ocr_pdf_pages",
                        lambda data, pages: {2: "RECOVERED CERTIFICATE TEXT, WELL OVER THE FLOOR"})

    pages = ingest.fill_scanned_pages(b"%PDF-", [(1, "a legible page of real text " * 3), (2, "")])

    assert pages[1][1].startswith("RECOVERED"), "page 2 must come back readable"


def test_without_ocr_the_pages_are_returned_untouched(monkeypatch):
    # "No OCR here" must look exactly like today, not like an error.
    monkeypatch.setattr(ingest.ocr, "available", lambda: False)
    original = [(1, "text"), (2, "")]

    assert ingest.fill_scanned_pages(b"%PDF-", original) == original


def test_a_page_ocr_could_not_read_stays_illegible(monkeypatch):
    # Recovering nothing is a real answer. It must not become an empty string that reads as
    # "read successfully, said nothing".
    monkeypatch.setattr(ingest.ocr, "available", lambda: True)
    monkeypatch.setattr(ingest.ocr, "ocr_pdf_pages", lambda data, pages: {})

    pages = ingest.fill_scanned_pages(b"%PDF-", [(1, "text"), (2, "")])

    assert pages[1] == (2, "")
    assert ingest.ingest_pages(pages)["illegible_pages"] == [2]


def test_ocr_is_only_asked_about_pages_that_need_it(monkeypatch):
    # Every page costs a render plus a read. Asking about legible pages is money for nothing.
    asked: list[list[int]] = []
    monkeypatch.setattr(ingest.ocr, "available", lambda: True)
    monkeypatch.setattr(ingest.ocr, "ocr_pdf_pages",
                        lambda data, pages: asked.append(list(pages)) or {})

    ingest.fill_scanned_pages(b"%PDF-", [(1, "a legible page " * 5), (2, ""), (3, "  ")])

    assert asked == [[2, 3]]
```

- [ ] **Step 2: Run to verify it fails**

`cd services/engine && uv run pytest tests/test_ingest_ocr.py -v` — `AttributeError: module 'app.ingest' has no attribute 'fill_scanned_pages'`.

- [ ] **Step 3: Implement**

In `services/engine/app/ingest.py`, add `from . import ocr` to the imports and:

```python
def fill_scanned_pages(
    data: bytes, pages: list[tuple[int, str]]
) -> list[tuple[int, str]]:
    """Read the pages that carry no text layer, and leave every other page alone.

    `ingest_pages` drops anything under `_MIN_CHARS_PER_PAGE` before the extractor ever sees
    it. That is right when a page genuinely holds nothing and was a silent 52% data loss for
    as long as OCR existed and nothing called it — and the lost half was the bidder's own
    certificates, which is the only material an answer library can be built from.

    Only the blank pages are sent: each one costs a render and a read, and asking about a page
    that already has text is money for nothing. A page OCR cannot read comes back exactly as
    illegible as it was, so the quality gate still reports it.
    """
    if not ocr.available():
        return pages
    blank = [p for p, t in pages if len(t.strip()) < _MIN_CHARS_PER_PAGE]
    if not blank:
        return pages
    recovered = ocr.ocr_pdf_pages(data, blank)
    if recovered:
        log.info("OCR recovered %d of %d unreadable pages", len(recovered), len(blank))
    return [(p, recovered.get(p, t)) for p, t in pages]
```

Then call it from the PDF branch of `parse_document_pages`, which is the one place that has both the bytes and the pages:

```python
    if ext == "pdf":
        pages = fill_scanned_pages(data, parse_pdf_pages(data))
        return [SourcePage(filename, page, text) for page, text in pages]
```

- [ ] **Step 4: Run the suite**

`cd services/engine && uv run pytest -q && uv run ruff check`

Existing ingest tests must pass unchanged — `ocr.available()` is False in the test environment, so `fill_scanned_pages` returns its input and behaviour is identical. If any existing test breaks, that is a real behaviour change and must be reported, not patched.

- [ ] **Step 5: Prove it end to end on a real scan**

Unit tests with a stubbed OCR prove the wiring, not the outcome. Inside the measurement image, ingest one real scanned PDF from `Sample Tender Usha Martin/` and show pages moving from illegible to legible. Paste the before/after counts into your report.

- [ ] **Step 6: Commit**

```bash
git add services/engine/app/ingest.py services/engine/tests/test_ingest_ocr.py
git commit -m "feat(ingest): send scanned pages through OCR before the legibility filter

A page under 20 characters was dropped before the extractor saw it. With OCR
wired to nothing that silently discarded 52% of one real customer folder, and
the discarded half was the bidder's own certificates and licences.

Only blank pages are sent — a render plus a read each. A page OCR cannot read
stays illegible and the quality gate still names it."
```

### Task A4: Say what OCR did, on the upload screen

The gate currently says pages "appear to be scans with little extractable text — re-upload a clearer copy". Once OCR runs, that sentence is wrong for the pages it recovered and still right for the rest. A screen that keeps saying "re-upload" after the system has just read the page teaches users to distrust it.

**Files:**
- Modify: `services/engine/app/ingest.py` (count what OCR recovered)
- Modify: `services/engine/app/tenders.py` (carry it in the ingest response)
- Modify: `apps/web/app/(app)/tenders/upload/page.tsx` — the gate lives at `:222-240`, not in `components/`
- Modify: `services/engine/tests/test_ingest_ocr.py`

**This task deliberately changes A3's signature.** A3 left `fill_scanned_pages(data, pages) -> list[tuple[int, str]]`, which cannot report what it recovered. Change it to return `tuple[list[tuple[int, str]], int]` — the pages and the count — and update A3's four tests in the same commit. Doing it here rather than in A3 keeps A3's diff about wiring and this one about honesty; do not leave the two out of step.

- [ ] **Step 1: Read the surface first**

`apps/web/app/(app)/tenders/upload/page.tsx:222-240`. It reads `body.data.illegible_pages` into state at `:86` and renders the warning at `:224`. `docs/DESIGN_SPEC.md` S3-D1 requires `[data-ocr-gate-warning]` to exist with a re-upload affordance whenever the gate fires — the selector and the affordance stay, the copy changes.

- [ ] **Step 2: Count the recovery and carry it**

`fill_scanned_pages` returns the count alongside the pages. Thread it through `parse_document_pages` and `_process_ingest` so the ingest response carries `pages_ocred` next to the existing `illegible_pages` — which now means what it says: pages still unreadable *after* OCR ran.

- [ ] **Step 3: Change the copy to match what happened**

Three states, three sentences. Currently there is one:

| Recovered | Still unreadable | What the screen should say |
|---|---|---|
| 0 | 0 | render nothing |
| N > 0 | 0 | "N scanned pages were read by OCR." No warning, no re-upload prompt — nothing is wrong. |
| any | M > 0 | name the M pages, and if N > 0 lead with "N scanned pages were read; M could not be read even so" |

Only the still-unreadable list keeps the re-upload affordance. A screen that says "re-upload a clearer copy" about a page the system has just read successfully teaches users to distrust it.

- [ ] **Step 4: Verify and commit**

`cd services/engine && uv run pytest -q && uv run ruff check`; `cd apps/web && pnpm typecheck && pnpm lint && pnpm test`. Then `/verify` on `/tenders/upload`, uploading one genuinely scanned PDF from `Sample Tender Usha Martin/`, and assert all three states you can reach. Attach the screenshot.

**Part A gate:** `uv run pytest` green, `ruff` clean, the Docker `available: True` check passed, real-scan evidence pasted, `docs/ocr-measurement.md` written. Deploy needs no migration. Wait for approval.

---

## Part B — one number, one action

### Task B1: Delete the duplicate progress strip

`SubmissionMeter`'s docstring says it replaced "four counters that described the same bid and disagreed". The P0/P1/P2/covered strip at `ReadinessHub.tsx:206-220` is one of those counters, still on screen, directly under the meter that replaced it.

The strip does carry one thing the meter does not: the **Re-match** and **Generate proposal** buttons. Those are actions, and they stay — it is the duplicated counting that goes.

**Files:**
- Modify: `apps/web/components/ReadinessHub.tsx`
- Modify: `apps/web/components/ReadinessHub.test.ts` if one exists; create coverage if the counts are computed rather than passed through

- [ ] **Step 1: Read both surfaces together**

Read `SubmissionMeter.tsx` in full and `ReadinessHub.tsx:200-240`. Confirm the two describe the same bid — the meter's blockers come from `/api/tenders/{id}/submission`, the strip's counts from `/api/tenders/{id}/readiness`. Note in your report whether they can disagree, and if they can, that is a finding worth stating even though this task removes one of them.

- [ ] **Step 2: Keep the actions, drop the counts**

Remove the counts `div` (`p0_blocking`, `p0_overridden`, `p1_open`, `p2_open`, `covered`). Keep the buttons. `data-p0-progress` is a contractual selector — `grep -rn "data-p0-progress" apps/web services` first, and if anything asserts on it, move the attribute rather than deleting it, or change the assertion deliberately and say so.

- [ ] **Step 3: Verify and commit**

`pnpm typecheck && pnpm lint && pnpm test`.

### Task B2: Four buttons become one action and two honest links

**Files:**
- Modify: `apps/web/components/SubmissionMeter.tsx`
- Modify: `apps/web/components/SubmissionMeter.test.ts` (create if absent)

- [ ] **Step 1: Write the failing test**

Create `apps/web/components/SubmissionMeter.test.ts`, testing a small exported helper rather than rendering (this repo has no React Testing Library — `BidVocabulary.tsx` documents that):

```ts
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
```

- [ ] **Step 2: Run it, watch it fail, then implement**

Export from `SubmissionMeter.tsx`:

```tsx
export type NavLink = { label: string; href: string; enabled: boolean; reason?: string };

/** Where this screen can usefully send you, and why it cannot yet.
 *
 * 'Requirements' used to be here and pointed at `/tenders/{id}/readiness` — the page the
 * meter is rendered on. A link to the current page is not navigation.
 *
 * The other two are offered disabled rather than hidden: a bidder should be able to see that
 * a proposal and a score exist as steps, without being sent to an empty page to find out they
 * are not ready. Hiding them would answer the wrong question.
 */
export function navFor(
  tenderId: string,
  state: { drafted: boolean; scored: boolean },
): NavLink[] {
  return [
    {
      label: "Proposal",
      href: `/proposals/${tenderId}`,
      enabled: state.drafted,
      ...(state.drafted ? {} : { reason: "Nothing drafted yet" }),
    },
    {
      label: "Technical score",
      href: `/proposals/${tenderId}/score`,
      enabled: state.scored,
      ...(state.scored ? {} : { reason: "Available once a proposal exists" }),
    },
  ];
}
```

Render an enabled link as a `Link` and a disabled one as a `span` carrying its reason in `title`, so it is visible but not clickable. `aria-disabled` on a real link still navigates; a span does not.

- [ ] **Step 3: Supply the state**

`SubmissionMeter` needs `drafted` and `scored`. The readiness page already reads `analyses`; add the equivalent reads for a proposal and a score estimate, **inside the existing `Promise.all`** — that page's comment records that serial awaits measured 6.8s of blank screen in production.

- [ ] **Step 4: Drop the redundant "Next:" label**

The header's `Next: {stage}` repeats the first blocker listed immediately below it. Remove the label and keep the ready/not-ready colour. Keep either `40%` or `2/5 stages`, not both — the percentage is derived from the stages and showing both asks the reader to check the arithmetic.

- [ ] **Step 5: Verify and commit**

`pnpm typecheck && pnpm lint && pnpm test`.

### Task B3: Give the tender an honest name

The heading renders `all_bid_docs_2026-09-05-…fcd2.pdf`. `deterministic/tender_meta.display_title` falls back to the filename when the parser found no title, and it found none because page one is a scan. Part A fixes the cause for future uploads; this task stops the symptom being a hash, including for the tenders already ingested.

**Files:**
- Modify: `services/engine/app/deterministic/tender_meta.py`
- Modify: `services/engine/tests/` — the matching test file for `display_title`
- Modify: `apps/web/components/ReadinessHub.tsx` (header)

- [ ] **Step 1: Write the failing test**

```python
def test_a_tender_number_beats_a_filename():
    # A filename is not a name. "GEM/2026/B/7431083 · Oil India" tells a bid team which
    # pursuit this is; "all_bid_docs_…fcd2.pdf" does not, and twelve of them are identical.
    meta = TenderMeta(title=None, tender_number="GEM/2026/B/7431083", authority="Oil India")
    assert display_title(meta, "all_bid_docs_2026-09-05-15-10-07_191e018c70c0.pdf") == \
        "GEM/2026/B/7431083 · Oil India"


def test_an_unreadable_package_says_so_rather_than_printing_a_hash():
    meta = TenderMeta(title=None, tender_number=None, authority=None)
    assert display_title(meta, "all_bid_docs_2026-09-05-15-10-07_191e018c70c0.pdf") == \
        "Untitled tender"


def test_a_real_filename_is_still_better_than_nothing():
    # A human-named file is a real answer; only machine-generated noise is worth replacing.
    meta = TenderMeta(title=None, tender_number=None, authority=None)
    assert display_title(meta, "Oil India wire rope NIT.pdf") == "Oil India wire rope NIT"
```

Adjust the `TenderMeta` construction to that dataclass's real shape — read it first.

- [ ] **Step 2: Implement**

```python
#: A filename that is machine-generated noise rather than something a person chose. Long,
#: and carrying a hex run no human types. Deliberately narrow: "Oil India wire rope NIT.pdf"
#: is a real answer and must survive.
_NOISY_FILENAME = re.compile(r"[0-9a-f]{16,}|_\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}_")


def display_title(meta: TenderMeta, fallback: str) -> str:
    """What a human should see.

    The filename is the LAST resort, not the second. A bid team running twelve pursuits gets
    twelve identical "all_bid_docs_….pdf" headings, and the tender number they actually use
    to talk about the bid was sitting in the metadata unused. When even that is missing —
    which happens when page one is a scan nobody could read — say so, because a hex hash
    tells the reader nothing and hides the real problem.
    """
    if meta.title:
        return meta.title
    named = " · ".join(x for x in (meta.tender_number, meta.authority) if x)
    if named:
        return named
    stem = fallback.rsplit(".", 1)[0]
    return "Untitled tender" if _NOISY_FILENAME.search(stem) else stem
```

- [ ] **Step 3: Say why on the screen**

A bare "Untitled tender" is honest but not actionable. In `ReadinessHub.tsx`'s header (around `:137`), when the title is exactly `"Untitled tender"`, render one muted line beneath it:

```tsx
{tenderTitle === "Untitled tender" && (
  // Not decoration: this is the OCR gap surfacing on a second screen. The heading is a
  // placeholder because page one is an image nobody could read, and a user who is not told
  // that will assume the upload half-failed.
  <p data-untitled-reason className="text-xs text-muted">
    No tender number or issuing authority could be read from this package — its first pages
    are scans.{" "}
    <Link href="/tenders/upload" className="underline">
      Upload a clearer copy
    </Link>
  </p>
)}
```

Compare on the exact string rather than adding a second prop: `display_title` is the single place that decides this, and a boolean threaded alongside it would be a second source of the same truth.

- [ ] **Step 4: Verify and commit**

`uv run pytest -q && uv run ruff check`, `pnpm typecheck && pnpm lint && pnpm test`.

**Part B gate:** all checks green, plus `/verify` on `/tenders/{id}/readiness` in both states — before analysis (the screenshot's state) and after. Assert the self-link is gone, disabled destinations show their reason, and only one progress figure renders.

---

## Sequencing

Part A first. It fixes the cause of B3's symptom, and it is the one with a decision gate in it — if A1 says Tesseract is not good enough, the shape of everything after it changes and there is no point having rewritten a screen in the meantime.

Within Part A the order is fixed: A1 (measure and decide) → A2 (adapter) → A3 (wire) → A4 (say so). Part B's three tasks are independent of each other and can be done in any order once A is settled.

## Out of scope, deliberately

- **Making ingest asynchronous.** A3 may discover it is needed. If it does, that is a jobs table and a re-extract pass, which is its own plan with its own review — not something to smuggle into a wiring task.
- **A paid OCR provider.** Only if A1's measurement says Tesseract misses the bar, and then only as a human's spend decision with the numbers in front of them.
- **Non-English OCR.** `tesseract-ocr-eng` only. Hindi and the other Devanagari-script packs are a PH2 question alongside the Hindi UI strings, and adding language packs speculatively is weight in the image for a case nobody has hit.
- **Redesigning the readiness item checklist.** Part B touches the two summary cards and the heading. The P0/P1/P2 item list below them is a separate surface with its own behaviour, and changing both at once makes the verification useless.
- **The `border-hairline` / `rounded-control` / `bg-ground` dead token classes.** Confirmed to resolve to nothing across 15 files and predating all of this. A real defect, a separate fix, and not something to entangle with either part here.
