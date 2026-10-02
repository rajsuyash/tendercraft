"""Load the tender-response golden corpus from $TC_GOLDEN_DIR.

The golden set (`tender_analysis/`) is customer data (Usha Martin's own tender archive). It is
gitignored and NEVER copied into this repo — every file here reads it by path from an env var.
See docs/tender-response/ARCHITECTURE.md §7 and docs/tender-response/IMPLEMENTATION_PLAN.md
§M-j for the schema and the harness contract.

Shapes (schema v1.1, `/private/tmp/claude-501/tc-shared/PHASE2_BRIEF.md`):
  requirements/<slug>.json, submission_documents/<slug>.json, mapping/<slug>.json  — one list
    of objects per tender, keyed by slug.
  template_candidates.json, missing_information_patterns.json, evidence_library.json,
    company_facts.json, tenders.json — shared across all tenders.
  _text/<slug>/manifest.json — [{file, page, method, chars}, ...] OR {"tender":..., "entries":
    [...]} (SAIL uses the dict shape; everything else is a bare list — both are handled).
  _text/<slug>/<bundle-dir>/p<NNN>.txt — page text. The bundle-dir name is NOT derived from
    `file` by any single deterministic rule (different analysis sessions named them
    differently) — see `candidate_dirs_for_document` for the resolution heuristic.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import dataclass
from functools import cache
from pathlib import Path

ENV_VAR = "TC_GOLDEN_DIR"

# ARCHITECTURE §7: only these origins count as "the UML side must have produced this" for
# submission-document recall — buyer-supplied, post-award and unresolved rows are not something
# a drafting pipeline is scored on producing.
RECALLABLE_DOC_ORIGINS = frozenset({
    "Usha Martin generated",
    "Usha Martin reusable company evidence",
    "Usha Martin tender-specific evidence",
    "Buyer format filled by UML",
})

# ARCHITECTURE §7 / known-pitfalls "A cache hit that erases the cache": a mapping status counts
# as "the system flagged this as missing/needs-attention" for the missing-information metric.
MISSING_INFO_STATUSES = frozenset({"NOT_FOUND_IN_ARCHIVE", "NEEDS_REVIEW", "PARTIALLY_ADDRESSED"})


class GoldenError(RuntimeError):
    """$TC_GOLDEN_DIR is unset/missing, or a golden file failed to parse. Always named — never
    a silent empty result (CLAUDE.md "forced verification" / "what actually counts")."""


def golden_dir() -> Path:
    raw = os.environ.get(ENV_VAR)
    if not raw:
        raise GoldenError(
            f"{ENV_VAR} is not set. Point it at the tender_analysis/ directory "
            "(customer data — never copied into this repo, see docs/tender-response/"
            "ARCHITECTURE.md §7)."
        )
    p = Path(raw).expanduser()
    if not p.is_dir():
        raise GoldenError(f"{ENV_VAR}={raw!r} is not a directory")
    if not (p / "requirements").is_dir():
        raise GoldenError(f"{ENV_VAR}={raw!r} has no requirements/ subdirectory — wrong path?")
    return p


def _load_json(path: Path):
    if not path.is_file():
        raise GoldenError(f"missing golden file: {path}")
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise GoldenError(f"failed to parse {path}: {e}") from e


def list_tenders(gdir: Path) -> list[str]:
    return sorted(p.stem for p in (gdir / "requirements").glob("*.json"))


@dataclass(frozen=True)
class GoldenTender:
    slug: str
    requirements: list[dict]
    submission_documents: list[dict]
    mapping: list[dict]


def load_tender(gdir: Path, slug: str) -> GoldenTender:
    return GoldenTender(
        slug=slug,
        requirements=_load_json(gdir / "requirements" / f"{slug}.json"),
        submission_documents=_load_json(gdir / "submission_documents" / f"{slug}.json"),
        mapping=_load_json(gdir / "mapping" / f"{slug}.json"),
    )


def load_all_tenders(gdir: Path, only: list[str] | None = None) -> dict[str, GoldenTender]:
    slugs = only if only is not None else list_tenders(gdir)
    return {slug: load_tender(gdir, slug) for slug in slugs}


@dataclass(frozen=True)
class SharedGolden:
    template_candidates: list[dict]
    missing_information_patterns: list[dict]
    evidence_library: dict  # {"evidence": [...], "expiry_incidents": [...]}
    company_facts: list[dict]
    tenders: list[dict]


def load_shared(gdir: Path) -> SharedGolden:
    return SharedGolden(
        template_candidates=_load_json(gdir / "template_candidates.json"),
        missing_information_patterns=_load_json(gdir / "missing_information_patterns.json"),
        evidence_library=_load_json(gdir / "evidence_library.json"),
        company_facts=_load_json(gdir / "company_facts.json"),
        tenders=_load_json(gdir / "tenders.json"),
    )


def mip_occurrences_for_tender(shared: SharedGolden, slug: str, kind: str = "information_request"
                                ) -> list[dict]:
    """Flatten missing_information_patterns.json occurrences for one tender, filtered to a
    pattern_kind. ARCHITECTURE §7's missing-info metric is scored only against
    `pattern_kind == "information_request"` rows — `compliance_check` rows are a different
    thing (M-g1's job, not the missing-information queue's)."""
    out = []
    for pattern in shared.missing_information_patterns:
        if pattern.get("pattern_kind") != kind:
            continue
        for occ in pattern.get("occurrences", []):
            if occ.get("tender_slug") == slug:
                out.append(occ)
    return out


# --------------------------------------------------------------------------------------------
# Date handling — DD-MM-YYYY or DD.MM.YYYY, trailing time/words ignored (tenders.json carries
# both "22-04-2024 11:00:00" and "25.02.2026 upto 11:00 AM"). Returns an ISO YYYY-MM-DD string,
# or None when unparseable (e.g. ONGC's bid_end is null in the corpus).
_DATE_RE = re.compile(r"^\s*(\d{2})[-.](\d{2})[-.](\d{4})")


def parse_ddmmyyyy(value: str | None) -> str | None:
    if not value:
        return None
    m = _DATE_RE.match(value)
    if not m:
        return None
    dd, mm, yyyy = m.groups()
    return f"{yyyy}-{mm}-{dd}"


@dataclass(frozen=True)
class TenderDates:
    folder_to_slug: dict[str, str]
    slug_to_bid_end: dict[str, str | None]


def tender_dates(shared: SharedGolden) -> TenderDates:
    folder_to_slug = {t["folder"]: t["slug"] for t in shared.tenders if t.get("folder")}
    slug_to_bid_end = {
        t["slug"]: parse_ddmmyyyy((t.get("bid_end") or {}).get("value"))
        for t in shared.tenders
    }
    return TenderDates(folder_to_slug, slug_to_bid_end)


def _folder_of(path: str) -> str:
    return path.split("/", 1)[0]


def first_seen_date(primary_path: str, other_paths: list[str], dates: TenderDates) -> str | None:
    """Earliest bid_end among every tender folder this item (a company_facts fact, or an
    evidence_library entry) is known to have come from.

    This is the vault_as_of definition: a fact/evidence item is "first seen" the moment ANY
    tender it appears in (primary source or a later-reused copy) was bid — because that is the
    earliest point at which this product's archive could plausibly have held the document. A
    document's own print date is not recorded anywhere in the corpus, so the earliest BIDDING
    tender it is attached to is the only dated anchor available.

    Decision — undated items (no resolvable folder on any path) are treated as NOT visible at
    any as_of date (fail closed), never as always-visible: showing an undated fact to an
    earlier vault snapshot is exactly the leak this filter exists to prevent (ARCHITECTURE §7:
    "otherwise facts learned from later tenders leak into earlier ones"), and a fact nobody can
    date is the least safe case, not the most permissive one.
    """
    dated = []
    for path in [primary_path, *other_paths]:
        slug = dates.folder_to_slug.get(_folder_of(path))
        if slug is None:
            continue
        d = dates.slug_to_bid_end.get(slug)
        if d is not None:
            dated.append(d)
    return min(dated) if dated else None


def _also_seen_folders(entries: list[dict]) -> list[str]:
    # also_seen_in[].tender_slug is, despite the name, the FOLDER string (spaces, not
    # underscores) — verified against tenders.json across all 12 real tenders.
    return [e["tender_slug"] for e in entries if e.get("tender_slug")]


@dataclass(frozen=True)
class VaultSnapshot:
    as_of: str
    company_facts: list[dict]
    evidence: list[dict]
    excluded_undated_facts: int
    excluded_undated_evidence: int


def vault_as_of(shared: SharedGolden, as_of: str) -> VaultSnapshot:
    """Facts/evidence visible to a vault snapshot taken at `as_of` (an ISO YYYY-MM-DD string,
    or a DD-MM-YYYY one — both accepted). Comparison is lexical on ISO dates, which sorts
    correctly for same-length YYYY-MM-DD strings."""
    as_of_iso = as_of if re.match(r"^\d{4}-\d{2}-\d{2}$", as_of) else parse_ddmmyyyy(as_of)
    if as_of_iso is None:
        raise GoldenError(f"vault_as_of: unparseable date {as_of!r}")
    dates = tender_dates(shared)

    facts, excluded_facts = [], 0
    for f in shared.company_facts:
        seen = first_seen_date(f["source_document"], _also_seen_folders(f.get("also_seen_in", [])),
                                dates)
        if seen is None:
            excluded_facts += 1
        elif seen <= as_of_iso:
            facts.append(f)

    evidence, excluded_evidence = [], 0
    for e in shared.evidence_library.get("evidence", []):
        seen = first_seen_date(e["canonical_path"], e.get("other_copies", []), dates)
        if seen is None:
            excluded_evidence += 1
        elif seen <= as_of_iso:
            evidence.append(e)

    return VaultSnapshot(as_of_iso, facts, evidence, excluded_facts, excluded_evidence)


# --------------------------------------------------------------------------------------------
# Page-text resolution: source_document -> the _text/<slug>/<bundle-dir>/p<NNN>.txt files that
# hold it. verify_tender.py's reference checker globs p<NNN>.txt across EVERY doc directory in
# the tender for the cited page numbers, which is "known looseness" (PHASE2_BRIEF /
# IMPLEMENTATION_PLAN §M-j task brief) — it can credit a quote against the wrong document's
# page 3. We narrow the search to the directories that plausibly ARE `source_document`,
# resolved via manifest.json, before falling back to the loose per-page-number behaviour.

def _manifest_entries(gdir: Path, slug: str) -> list[dict]:
    raw = _load_json(gdir / "_text" / slug / "manifest.json")
    return raw["entries"] if isinstance(raw, dict) else raw


_WORD_RE = re.compile(r"[a-z0-9]+")


def _name_tokens(name: str) -> set[str]:
    return set(_WORD_RE.findall(name.lower()))


@cache
def _resolution_index(gdir_str: str, slug: str) -> tuple[dict[str, int], dict[str, int]]:
    """(per-file page count from the manifest, per-dir page-file count on disk)."""
    gdir = Path(gdir_str)
    entries = _manifest_entries(gdir, slug)
    file_counts: dict[str, int] = {}
    for e in entries:
        file_counts[e["file"]] = file_counts.get(e["file"], 0) + 1
    base = gdir / "_text" / slug
    dir_counts = {
        d.name: len(list(d.glob("p[0-9][0-9][0-9].txt")))
        for d in base.iterdir() if d.is_dir()
    } if base.is_dir() else {}
    return file_counts, dir_counts


def candidate_dirs_for_document(gdir: Path, slug: str, source_document: str) -> list[str]:
    """Best-effort set of _text/<slug>/ subdirectory names that hold `source_document`'s pages.

    Resolution: filter directories whose page-file count matches the manifest's page count for
    this exact `file` entry, then rank the survivors by filename/dirname token overlap. Ties
    (including the "no directory shares a token" case — short generic filenames like
    "local.pdf") are returned as a GROUP, not arbitrarily broken: callers union the candidate
    group's text rather than guess, which can only make the resolution looser than a correct
    unique answer, never wrong in a way a unique (but mistaken) pick could be. When nothing
    matches by page count at all (a manifest/dir mismatch), every directory in the tender is
    returned — i.e. verify_tender.py's original behaviour, as the final fallback.
    """
    file_counts, dir_counts = _resolution_index(str(gdir), slug)
    if not dir_counts:
        return []
    count = file_counts.get(source_document)
    candidates = [d for d, n in dir_counts.items() if n == count] if count is not None else []
    if not candidates:
        candidates = list(dir_counts)  # fallback: loose, matches verify_tender.py

    toks = _name_tokens(Path(source_document).stem)
    scored = sorted(((len(toks & _name_tokens(d)), d) for d in candidates), reverse=True)
    best = scored[0][0]
    return [d for score, d in scored if score == best]


def page_text(gdir: Path, slug: str, source_document: str, page_start: int,
              page_end: int | None = None) -> str:
    """NFKC-normalised union of page text for [page_start, page_end] across the resolved
    candidate directories for `source_document`."""
    p0, p1 = page_start, page_end or page_start
    base = gdir / "_text" / slug
    dirs = candidate_dirs_for_document(gdir, slug, source_document)
    chunks = []
    for d in dirs:
        for p in range(p0, p1 + 1):
            f = base / d / f"p{p:03d}.txt"
            if f.is_file():
                chunks.append(f.read_text(errors="ignore"))
    return unicodedata.normalize("NFKC", " ".join(chunks))


# --------------------------------------------------------------------------------------------
# Document-type normalisation for submission_document_recall. Collapses superficial formatting
# differences only (case, punctuation, parenthetical asides) — it does NOT merge semantic
# synonyms ("GST Certificate" vs "GST Registration Certificate", "Declaration" vs "Statutory
# Declaration"): that needs a curated taxonomy, which is M-d/M-f's job, not this harness's.

_PAREN_RE = re.compile(r"\([^)]*\)")
_SEP_RE = re.compile(r"[/\-—&]+")
_SPACE_RE = re.compile(r"\s+")


def normalize_document_type(document_type: str) -> str:
    s = _PAREN_RE.sub(" ", document_type or "")
    s = _SEP_RE.sub(" ", s)
    s = s.lower().replace("licence", "license")
    return _SPACE_RE.sub(" ", s).strip()
