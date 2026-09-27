"""Evidence-backed Q&A over the indexed data room.

The LLM is instructed to answer ONLY from retrieved chunks and to cite
(document, page) for every claim. Retrieval happens first; the model
never sees the question without evidence in context.
"""

import json

from app.llm.provider import get_llm
from app.retrieval.index import search

_SYSTEM = """You are a due-diligence analyst. Answer the question ONLY using
the evidence excerpts provided. For every claim, cite the source.

Respond with JSON:
{
  "answer": "...",
  "citations": [
    {"document_id": "...", "filename": "...", "page_start": 0, "page_end": 0,
     "quote": "verbatim substring from the excerpt"}
  ],
  "confidence": 0.0
}
If the evidence does not answer the question, say so explicitly and return
an empty citations list. Never answer from general knowledge."""


def _format_evidence(hits: list[dict]) -> str:
    blocks = []
    for i, h in enumerate(hits, 1):
        m = h["metadata"]
        pages = (
            f"p.{m['page_start']}"
            if m["page_start"] == m["page_end"]
            else f"pp.{m['page_start']}-{m['page_end']}"
        )
        blocks.append(
            f"[{i}] {m['filename']} ({m['document_id']}), {pages}\n{h['text']}"
        )
    return "\n\n---\n\n".join(blocks)


def answer_question(question: str, n_results: int = 8, collection=None) -> dict:
    hits = search(question, n_results=n_results, collection=collection)
    if not hits:
        return {"answer": "No relevant documents found.", "citations": [], "confidence": 0.0}

    llm = get_llm()
    raw = llm.complete(
        [
            {"role": "system", "content": _SYSTEM},
            {
                "role": "user",
                "content": f"QUESTION:\n{question}\n\nEVIDENCE EXCERPTS:\n{_format_evidence(hits)}",
            },
        ],
        json_mode=True,
    )
    result = json.loads(raw)
    result["retrieved_chunks"] = [h["chunk_id"] for h in hits]
    return result


if __name__ == "__main__":
    import sys

    q = " ".join(sys.argv[1:]) or "Which contracts require consent if ownership changes?"
    print(json.dumps(answer_question(q), indent=2))
