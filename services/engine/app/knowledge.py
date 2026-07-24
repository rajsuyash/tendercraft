"""Knowledge-base ingestion — add company documents (PDF/DOCX/PPTX) or a website to the library.

Extract text per format, let Gemini classify it (doc_type, validity, structured fields), and
hand back a library_documents row. Untrusted input throughout: the extracted text is data for
the classifier only; URL fetch is guarded against SSRF and bounded in size.
"""

from __future__ import annotations

import io
import ipaddress
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import httpx

from pipeline.client import ModelError, generate_json
from pipeline.schemas import KB_DOC_SCHEMA

from .envelope import ApiError

_MAX_FETCH_BYTES = 5 * 1024 * 1024
_PROMPT = (Path(__file__).resolve().parents[1] / "prompts" / "kb_classifier.md").read_text()


# ---------- text extraction ----------
def extract_text(filename: str, data: bytes) -> str:
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext == "pdf":
        from .ingest import parse_pdf_pages

        return "\n".join(t for _, t in parse_pdf_pages(data)).strip()
    if ext in ("docx",):
        return _extract_docx(data)
    if ext in ("pptx",):
        return _extract_pptx(data)
    # plain text / unknown: best-effort decode
    return data.decode("utf-8", errors="ignore").strip()


def _extract_docx(data: bytes) -> str:
    from docx import Document

    try:
        doc = Document(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001 — bad upload -> 400
        raise ApiError(400, "BAD_DOCUMENT", f"could not read DOCX: {exc}") from exc
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip()).strip()


def _extract_pptx(data: bytes) -> str:
    from pptx import Presentation

    try:
        prs = Presentation(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001 — bad upload -> 400
        raise ApiError(400, "BAD_DOCUMENT", f"could not read PPTX: {exc}") from exc
    parts = [
        shape.text
        for slide in prs.slides
        for shape in slide.shapes
        if shape.has_text_frame and shape.text.strip()
    ]
    return "\n".join(parts).strip()


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip = False
        self.chunks: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = False

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.chunks.append(data.strip())


def fetch_url_text(url: str) -> str:
    """Fetch a public webpage and strip it to text. Guards against SSRF + oversize responses."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ApiError(400, "BAD_URL", "only http(s) URLs are allowed")
    host = parsed.hostname or ""
    if _is_private_host(host):
        raise ApiError(400, "BLOCKED_URL", "internal/private hosts are not allowed")
    try:
        resp = httpx.get(
            url, timeout=15, follow_redirects=True,
            headers={"User-Agent": "TenderCraft/0.1"},
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise ApiError(400, "FETCH_FAILED", f"could not fetch URL: {exc}") from exc
    body = resp.content[:_MAX_FETCH_BYTES].decode("utf-8", errors="ignore")
    p = _TextExtractor()
    p.feed(body)
    return re.sub(r"\s+\n", "\n", " ".join(p.chunks)).strip()


def _is_private_host(host: str) -> bool:
    if host in ("localhost", "", "metadata.google.internal"):
        return True
    try:
        return ipaddress.ip_address(host).is_private or ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False  # a DNS name — resolution/egress control is a deployment concern


# ---------- classification ----------
def classify(text: str) -> dict:
    """Derive {name, doc_type, valid_to, structured_fields(dict)} from text. Never raises."""
    empty = {
        "name": "Empty document", "doc_type": "other",
        "valid_to": None, "structured_fields": {},
    }
    if not text.strip():
        return empty
    prompt = _PROMPT.replace("{{TEXT}}", text[:6000])
    try:
        r = generate_json(prompt, KB_DOC_SCHEMA)
    except ModelError:
        return {**empty, "name": "Uploaded document"}
    fields = {f["key"]: f["value"] for f in r.get("structured_fields", []) if f.get("key")}
    return {
        "name": r.get("name") or "Uploaded document",
        "doc_type": r.get("doc_type", "other"),
        "valid_to": r.get("valid_to") or None,
        "structured_fields": fields,
    }


def build_document(text: str) -> dict:
    """Classify extracted text into a library_documents row payload (minus tenant/actor)."""
    meta = classify(text)
    return {
        "name": meta["name"],
        "doc_type": meta["doc_type"],
        "valid_to": meta["valid_to"],
        "text_content": text[:20000],
        "structured_fields": meta["structured_fields"],
    }
