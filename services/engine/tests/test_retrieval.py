"""Per-criterion evidence selection — pin, lexical rank, fallback, chunking."""

from pipeline.retrieval import chunk_docs, chunk_text, doc_id_of, select_evidence

_TURNOVER = {"id": "d1", "name": "turnover-certificate-FY25.pdf",
             "text": "CA-certified average annual turnover of 8.2 Cr across FY23-FY25"}
_UNDERTAKING = {"id": "d2", "name": "undertaking.docx",
                "text": "Standard undertaking of non-blacklisting and compliance"}
_COMPLETION = {"id": "d3", "name": "eoffice-completion.pdf",
               "text": "Completion certificate: e-Office software implementation, 3.8 Cr"}
_DOCS = [_TURNOVER, _UNDERTAKING, _COMPLETION]


def _ids(docs):
    return [d["id"] for d in docs]


def test_empty_docs_returns_empty():
    assert select_evidence("anything", []) == []


def test_pinned_doc_included_but_relevance_leads():
    # the pinned doc is guaranteed present, but the most-relevant doc (d1 turnover) still LEADS —
    # a pinned-but-irrelevant doc must not dominate the evidence.
    out = select_evidence("Average annual turnover of not less than 5 Crores", _DOCS, pinned_id="d3")
    assert out[0]["id"] == "d1"  # relevance leads
    assert "d3" in _ids(out)  # pinned still included


def test_pinned_thin_doc_does_not_bury_good_cert():
    thin = {"id": "dx", "name": "scan.pdf", "text": "letterhead only"}
    out = select_evidence("Average annual turnover over FY23-FY25", [*_DOCS, thin], pinned_id="dx")
    assert out[0]["id"] == "d1"  # good turnover cert leads, not the thin pin
    assert "dx" in _ids(out)  # thin pin still included


def test_pinned_doc_already_relevant_not_duplicated():
    out = select_evidence("annual turnover FY23-FY25", _DOCS, pinned_id="d1")
    assert _ids(out).count("d1") == 1  # already in ranked -> not appended twice


def test_pinned_missing_falls_back_to_lexical():
    out = select_evidence("Average annual turnover over FY23-FY25", _DOCS, pinned_id="gone")
    assert out[0]["id"] == "d1"  # turnover doc ranks first by overlap


def test_lexical_ranks_relevant_first():
    assert select_evidence("non-blacklisting declaration on letterhead", _DOCS)[0]["id"] == "d2"
    assert select_evidence("software implementation works", _DOCS)[0]["id"] == "d3"


def test_no_overlap_falls_back_to_all():
    out = select_evidence("zzzz qqqq wxyz", _DOCS)  # no shared tokens
    assert _ids(out) == _ids(_DOCS)  # never starve -> all docs


def test_top_k_caps_results():
    docs = [{"id": f"d{i}", "name": "turnover cert", "text": "annual turnover statement"} for i in range(10)]
    out = select_evidence("annual turnover statement", docs, top_k=3)
    assert len(out) == 3


def test_idf_prefers_the_discriminating_document():
    # "bidder" and "tender" appear everywhere; "udyam" appears once. The doc that shares the
    # rare token must win even though the boilerplate doc shares more tokens overall.
    boiler = {"id": "b", "name": "boilerplate",
              "text": "bidder tender bidder tender submission compliance requirement general"}
    rare = {"id": "r", "name": "udyam", "text": "udyam registration certificate bidder"}
    noise = [{"id": f"n{i}", "name": "n", "text": "bidder tender submission compliance"}
             for i in range(6)]
    out = select_evidence("udyam registration of the bidder", [boiler, rare, *noise])
    assert out[0]["id"] == "r"


# --- chunking ---


def test_short_text_is_one_chunk():
    assert chunk_text("short") == ["short"]


def test_empty_text_is_no_chunks():
    assert chunk_text("") == []


def test_long_text_splits_and_covers_the_tail():
    # The bug this fixes: a 20-page doc used to be truncated to its first 1200 chars, so the
    # drafter never saw anything past the cover page.
    body = "\n\n".join(f"paragraph {i} " + "filler " * 40 for i in range(40))
    chunks = chunk_text(body, size=1500, overlap=200)
    assert len(chunks) > 1
    assert all(len(c) <= 1500 + 200 for c in chunks)
    assert "paragraph 39" in chunks[-1]  # the tail survives


def test_single_oversized_paragraph_is_cut():
    chunks = chunk_text("x" * 5000, size=1000, overlap=100)
    assert len(chunks) > 1
    assert all(len(c) <= 1000 for c in chunks)


def test_chunk_docs_ids_are_addressable():
    out = chunk_docs([{"id": "doc-1", "name": "n", "text": "a"}])
    assert out[0]["id"] == "doc-1#0"
    assert doc_id_of(out[0]["id"]) == "doc-1"


def test_chunk_docs_keeps_empty_docs_addressable():
    out = chunk_docs([{"id": "doc-1", "name": "turnover cert", "text": ""}])
    assert [d["id"] for d in out] == ["doc-1#0"]


def test_pinning_still_works_after_chunking():
    """Regression: pinned ids are library_documents.id, chunk ids are "<doc>#n".

    Comparing them raw would silently stop honouring "attach a doc to this criterion" —
    the one control the bidder has over their own evidence.
    """
    docs = chunk_docs([
        {"id": "d1", "name": "turnover", "text": "annual turnover certificate FY23-FY25"},
        {"id": "d3", "name": "scan", "text": "unrelated letterhead scan"},
    ])
    out = select_evidence("annual turnover certificate", docs, pinned_id="d3")
    assert any(doc_id_of(d["id"]) == "d3" for d in out)  # the pin was honoured
    assert doc_id_of(out[0]["id"]) == "d1"  # relevance still leads
