# OCR provider measurement — Tesseract against a real tender folder

**Measured 2026-09-14.** Corpus: `Sample Tender Usha Martin/` — 33 PDFs, 478 pages, across
the five tenders this customer actually sent. Script: `tools/measure-ocr.py` (re-run it rather
than reasoning about it). Tesseract 5.5.3 / leptonica 1.87.0, rendered at 200 DPI by
`pdftoppm`, matching `app/ocr.py`'s `DPI`.

**Platform caveat, stated first because it changes one of the two numbers.** This ran on
macOS / Apple silicon, not in the Linux engine image — Docker Desktop was installed but its
daemon would not accept connections on this machine. The **recovery rate is portable**: same
Tesseract engine, same page images, same `_MIN_CHARS_PER_PAGE = 20` threshold the ingest path
uses. The **seconds per page is a floor, not the production number** — a Cloud Run vCPU is
slower than an M-series core, so the real figure is worse than the one below, not better.

## Result

| | |
|---|---|
| Pages | 478 |
| No text layer | 248 — **52% of all pages** |
| Recovered by OCR to ≥20 chars | 242 — **98% of those** |
| Still unreadable after OCR | 6 |
| OCR wall clock | 858s total · **3.5s/page (macOS floor)** |

The 52% independently reproduces the figure recorded in `app/ocr.py`'s docstring from
2026-09-09 ("480 pages, and only 48% carried extractable text"), measured then by a different
route. Two independent measurements agreeing is worth more than either alone.

## Verdict on accuracy: adopt Tesseract

The plan's rule was: ≥90% recovery **and** clean samples → adopt. 98% clears the rate. Nine
samples were read rather than trusted, and seven are directly usable:

- **`Oil India/Local Content.pdf`** — clean. "UNDERTAKING FOR LOCAL CONTENT We, USHA MARTIN
  LTD. (Name of the bidder) have submitted Bid against Tender No. GEM/2026/B/7431083 dated
  10-04-2026" — the tender number and date survive exactly.
- **`Oil India/Tender Docsorganized.pdf`** — clean, including engineering detail:
  "B- Length: 59.13 Mtrs ( 194'-0"), Mast Raising Drg. No. 3-96532-1-6160".
- **`UCIL/Technical specification.pdf`** — clean, and it is precisely the spec table Module H
  wants: "Diameter Construction Applied Standard Tensile Grade of the Wires Wire Finish Lay
  Length Total length Lubrication Reel Size Unit Mass Nominal Breaking Load".
- **`UCIL/ATC Doc.pdf`**, **`UCIL/Local Content.pdf`**, **`UCIL/Provenness Final.pdf`**,
  **`Oil India/Provenness.pdf`** — clean.

Two are partly garbled, and the pattern is worth naming:

- **`NMDC/ts___….pdf`** — the decorative header comes through as "ewer ef a ter … Mmm Sree",
  but the substance is intact: "Technical Specification", "Dia. - 18 mm; Steel Core",
  "1960 N/mm2".
- **`Oil India/UML DOCS.pdf`** — a scanned, stamped PAN card. The company name survives
  ("NAME : USHA: MARTIN LIMITED") and **the PAN number does not**: it reads
  "eRCUZSOM ATA". 

**The rule that follows from that second one: OCR text is evidence, never an identifier.**
A stamped or overprinted document garbles exactly the short alphanumeric strings — PAN, GST,
licence numbers — that are most damaging to get wrong. The product's existing rules already
cover this and must not be relaxed for OCR'd pages: financial and identity values render only
via transclusion from structured profile data (B-FR3), never from prose in a retrieved chunk,
and `known-pitfalls.md` already records that identity facts come from the profile rather than
from an evidence chunk. OCR makes that rule more load-bearing, not less.

The 6 pages OCR could not read at all stay illegible and keep routing to the quality gate,
which is the correct outcome and unchanged.

## Verdict on latency: it cannot run inside the upload request

**This is the finding that changes the plan.** `POST /api/tenders/ingest` awaits
`_process_ingest` in a threadpool — the uploader waits for it. The plan's own gate said above
~2s/page, inline is the wrong design. Measured 3.5s/page, on hardware faster than production.

What one real package costs, from the per-file numbers:

| Oil India package | scanned pages | OCR seconds (macOS floor) |
|---|---:|---:|
| `Local Content.pdf` | 1 | 1.5 |
| `Provenness.pdf` | 17 | 33.8 |
| `Tender Docsorganized.pdf` | 38 | 83.3 |
| `UML DOCS.pdf` | 21 | 38.3 |
| **total** | **77** | **157s, and slower in production** |

That is a two-and-a-half-minute upload at best, likely four or five on Cloud Run, for one
tender. `ocr.MAX_PAGES = 60` does not save it either: the cap is per call and the call is per
PDF, so a four-file package can legitimately reach 240 pages.

**Escalated to the decision owner rather than shipped.** Three options, with the recommendation:

1. **Background the OCR pass and re-extract the recovered pages.** The repo already has this
   exact pattern, shipped and verified today: `tenders._extract_quietly` runs as a
   `BackgroundTask` after the response, with `specs_extracted_at` marking completion.
   The upload stays fast, scanned pages arrive a minute or two later, and the screen can say
   so. **Recommended.** The cost is that criteria extraction has to run a second time over the
   recovered pages and merge, which is more than the original A3 assumed and deserves its own
   task rather than being smuggled into a wiring change.
2. **Make ingest fully asynchronous** — a `jobs` table, per `docs/conventions.md`'s noted
   ceiling. Correct long-term, materially bigger, and it changes the upload UX for everyone
   including packages with no scans at all.
3. **Cap OCR hard inline** — say the first 10 scanned pages, background the rest. Gets page
   one readable (which is what fixes the filename heading) at ~35s added. A compromise that
   leaves a partial state to explain.

Option 1 is recommended because the pattern is already in production here and was verified
end to end today, so it carries the least new risk.

## Cost

Zero marginal. Tesseract and poppler are apt packages in the engine image, roughly 60 MB with
`--no-install-recommends`, and no page leaves the container — which also keeps the DPDP and
residency question out of the way, unlike a hosted OCR API.

For contrast, the alternative the PRD left open: Google Document AI is roughly $1.50 per
1,000 pages. On this corpus alone (248 scanned pages) that is about $0.37; at any real
customer volume it is a recurring line item for accuracy this measurement says is not needed.
**No paid provider is warranted on this evidence.**

## Re-run it

```bash
brew install tesseract   # or: apt-get install tesseract-ocr tesseract-ocr-eng poppler-utils
services/engine/.venv/bin/python tools/measure-ocr.py "Sample Tender Usha Martin"
```

Prefer the Linux image (`tools/ocr-measure.Dockerfile`, Task A1 of the plan) when Docker is
available, so the timing is the production one rather than a floor.
