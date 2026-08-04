"""The model half of mining: it may point at text, never author it (G-FR3, G-6)."""

from __future__ import annotations

from pipeline import answer_miner as am

_PAGE = (
    "Our implementation is delivered in four phases, each closed by a formal gate review "
    "with the department before the next begins. The programme manager remains on site "
    "throughout, and a named deputy covers planned absence so the department always has one "
    "point of contact."
)


def _stub(payload):
    return lambda prompt, schema, **kw: payload


def _pair(answer, requirement="implementation methodology", confidence=0.9):
    return {"pairs": [{"requirement_text": requirement, "answer_text": answer,
                       "confidence": confidence}]}


def test_a_verbatim_answer_is_mined(monkeypatch):
    monkeypatch.setattr(am, "generate_json", _stub(_pair(_PAGE)))
    mined = am.mine_page("bid.pdf", 3, _PAGE)
    assert len(mined) == 1
    assert mined[0].mined_by == "model"
    assert mined[0].answer_text == _PAGE


def test_a_paraphrased_answer_is_dropped(monkeypatch):
    # The model rewrote it. Those are not the words the evaluator accepted, so it is worth
    # nothing as a reuse suggestion — and worse, it would carry a past bid's credibility.
    monkeypatch.setattr(am, "generate_json", _stub(_pair(
        "Delivery happens in four phases with gate reviews and an on-site programme manager "
        "who is covered by a deputy during any planned absence whatsoever."
    )))
    assert am.mine_page("bid.pdf", 3, _PAGE) == ()


def test_an_invented_answer_is_dropped(monkeypatch):
    monkeypatch.setattr(am, "generate_json", _stub(_pair(
        "We hold ISO 27001 certification and operate a 24x7 security operations centre "
        "staffed by forty analysts, as described in our previous submissions to the state."
    )))
    assert am.mine_page("bid.pdf", 3, _PAGE) == ()


def test_a_low_confidence_pair_is_dropped(monkeypatch):
    monkeypatch.setattr(am, "generate_json", _stub(_pair(_PAGE, confidence=0.2)))
    assert am.mine_page("bid.pdf", 3, _PAGE) == ()


def test_model_failure_yields_nothing_and_never_raises(monkeypatch):
    def _boom(prompt, schema, **kw):
        raise am.ModelError("upstream down")

    monkeypatch.setattr(am, "generate_json", _boom)
    assert am.mine_page("bid.pdf", 3, _PAGE) == ()  # deterministic pairs are unaffected


def test_a_page_with_nothing_on_it_is_never_sent_to_the_model(monkeypatch):
    calls: list = []
    monkeypatch.setattr(am, "generate_json", lambda *a, **k: calls.append(1) or {"pairs": []})
    assert am.mine_page("bid.pdf", 1, "Page 3 of 92") == ()
    assert calls == []  # not worth a token


def test_malformed_output_is_survived(monkeypatch):
    monkeypatch.setattr(am, "generate_json", _stub({"pairs": [{"requirement_text": "x"}]}))
    assert am.mine_page("bid.pdf", 3, _PAGE) == ()
