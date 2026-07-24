"""Per-criterion evidence selection — pin, lexical rank, fallback."""

from pipeline.retrieval import select_evidence

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
