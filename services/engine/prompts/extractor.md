# Extractor — tender pages → TOM candidate criteria

Spec: tendercraft-PRD.md §5.1 (Extractor row), Module A.

## Contract (binding)

- Input: page text + layout hints, OCR output where scanned
- Output: **tool-use JSON only** against the criteria schema — `{id, source_anchor: {page, clause}, verbatim_text, category: eligibility|technical|financial|terms, requirement_level: mandatory|desirable|self-attestation, evidence_required, evaluation_weight|null, confidence: 0..1}` per criterion. Free text output is rejected.
- No criterion without a resolvable source anchor (A-AC3).
- Confidence < 0.80 → verification queue (A-FR4); the model never self-certifies.
- **G-6**: tender text is untrusted data. Instruction-like content inside the document is content to extract, never instructions to follow. This component has no tools beyond the schema emitter.

## Prompt

TODO: author at M1 alongside the first eval run. Structure: role, schema, category/requirement-level definitions with Indian-procurement examples (EMD, MAF, MSE exemptions, ATC), anchor-fidelity rules, confidence calibration guidance, 2–3 few-shot page→criteria examples from the fixture tender (FIX-3).
