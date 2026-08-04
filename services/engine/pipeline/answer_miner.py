"""Model-assisted mining of requirement -> answer pairs (G-FR3).

The deterministic pass (app/deterministic/answer_mining.py) reads structure: form headings and
compliance tables, which is most of an Indian government bid. This handles the residue — prose
that answers a requirement it never names — and it is deliberately the smaller half.

Two properties matter more than recall here:

  * **Verbatim or nothing.** A reused answer is worth something because those exact words were
    accepted by an evaluator. A paraphrase is just the model writing, with a past bid's
    reputation attached. So every returned answer is checked against the source page and
    dropped if it is not actually there.
  * **The page is data.** A submitted bid is untrusted input (G-6): the schema is allowlisted,
    this component has no tools, and nothing in the page can make it fetch, write or obey.

Model failure returns () — the deterministic pairs still stand. Never crash, never invent.
"""

from __future__ import annotations

from pathlib import Path

from app.deterministic.answer_mining import MinedAnswer, appears_verbatim, match_section_key

from .client import ModelError, generate_json
from .schemas import ANSWER_PAIR_SCHEMA

_PROMPT = (Path(__file__).resolve().parents[1] / "prompts" / "answer_miner.md").read_text()

#: Pages are sent whole; a bid page is well under any context limit and truncating mid-answer
#: would produce exactly the non-verbatim output the gate then discards.
_MAX_PAGE_CHARS = 12000
#: Below this the model is guessing at a page with nothing on it.
_MIN_CONFIDENCE = 0.5
_MIN_ANSWER_CHARS = 120


def mine_page(
    document: str, page: int, text: str, section_specs: tuple[tuple[str, str], ...] = (),
) -> tuple[MinedAnswer, ...]:
    """Mine one page of prose. Returns () on model failure, malformed output, or nothing found."""
    if len(text.strip()) < _MIN_ANSWER_CHARS:
        return ()
    try:
        result = generate_json(_PROMPT.replace("{{TEXT}}", text[:_MAX_PAGE_CHARS]),
                               ANSWER_PAIR_SCHEMA)
    except ModelError:
        return ()  # the deterministic pairs are unaffected

    out: list[MinedAnswer] = []
    for pair in (result.get("pairs") or []):
        requirement = (pair.get("requirement_text") or "").strip()
        answer = (pair.get("answer_text") or "").strip()
        if not requirement or len(answer) < _MIN_ANSWER_CHARS:
            continue
        if float(pair.get("confidence") or 0) < _MIN_CONFIDENCE:
            continue
        # The gate that makes this safe: the model may only POINT AT text, never author it.
        if not appears_verbatim(answer, text):
            continue
        out.append(
            MinedAnswer(
                requirement_text=requirement[:300],
                answer_text=answer,
                section_key=match_section_key(requirement, section_specs),
                mined_by="model",
                document=document,
            )
        )
    del page  # kept in the signature so callers read as (document, page, text)
    return tuple(out)
