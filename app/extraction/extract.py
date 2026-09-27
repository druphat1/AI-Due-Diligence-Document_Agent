"""Structured extraction: retrieved chunks -> Finding objects.

Anti-hallucination design: the LLM cites a `chunk_id` and a `quote`.
Document id, filename, and page range are resolved from the index via
`get_chunks_by_ids` — the model's claim about WHERE evidence lives is
never trusted; only the quote itself is taken from the model, and that
gets verified against the real page text downstream.
"""

import json
import re

from app.analysis.checks import CheckSpec
from app.extraction.schemas import Evidence, Finding
from app.llm.provider import get_llm
from app.retrieval.index import get_chunks_by_ids, search

_SYSTEM = """You are a due-diligence extraction engine. You receive a specific
check and evidence excerpts retrieved from deal documents.

Rules — non-negotiable:
- Cite ONLY chunk_ids shown in the excerpts. Never invent a chunk_id,
  document name, or page number.
- Every "quote" must be a VERBATIM substring copied from that chunk's
  text. Do not paraphrase, summarize, or complete a sentence.
- Compare across all documents provided; one finding may cite evidence
  from multiple documents.
- If nothing relevant was found, emit one finding with severity
  "NO_ISSUE" citing the chunk(s) you reviewed.
- Emit at most one finding per issue per document set; consolidate
  duplicates.

Respond with JSON only:
{
  "findings": [
    {
      "title": "short label",
      "finding": "what was found, in one or two sentences",
      "severity": "NO_ISSUE|LOW|MEDIUM|HIGH",
      "confidence": 0.0,
      "reason": "why this severity",
      "evidence": [{"chunk_id": "...", "quote": "verbatim excerpt"}]
    }
  ]
}"""


def _format_chunks(hits: list[dict]) -> str:
    blocks = []
    for h in hits:
        m = h["metadata"]
        blocks.append(
            f"[chunk_id={h['chunk_id']} | file={m['filename']} | "
            f"pages={m['page_start']}-{m['page_end']}]\n{h['text']}"
        )
    return "\n\n---\n\n".join(blocks)


def _parse_findings(raw: str) -> list[dict]:
    """Extract the findings array from LLM output, tolerating stray prose."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        data = json.loads(match.group(0)) if match else {}
    return data.get("findings", []) if isinstance(data, dict) else []


def _bind_evidence(items: list[dict], collection=None) -> list[Evidence]:
    """Resolve cited chunk_ids to authoritative index metadata."""
    ids = [e.get("chunk_id", "") for e in items]
    resolved = get_chunks_by_ids(ids, collection=collection)
    bound = []
    for item in items:
        cid = item.get("chunk_id", "")
        hit = resolved.get(cid)
        if hit:  # real chunk — trust the index for doc/page, not the LLM
            m = hit["metadata"]
            bound.append(
                Evidence(
                    chunk_id=cid,
                    document_id=m["document_id"],
                    filename=m["filename"],
                    page_start=m["page_start"],
                    page_end=m["page_end"],
                    quote=item.get("quote", ""),
                )
            )
        else:  # hallucinated chunk_id — keep it, verification will fail it
            bound.append(
                Evidence(
                    chunk_id=cid,
                    document_id="unresolved",
                    filename="unresolved",
                    page_start=0,
                    page_end=0,
                    quote=item.get("quote", ""),
                    verified=False,
                    match_score=0.0,
                )
            )
    return bound


def extract_findings(
    check: CheckSpec,
    hits: list[dict],
    llm=None,
    collection=None,
) -> list[Finding]:
    llm = llm or get_llm()
    user = (
        f"CHECK: {check.name}\n"
        f"WHAT TO LOOK FOR: {check.instructions}\n"
        f"SEVERITY GUIDANCE: {check.severity_hint}\n\n"
        f"EVIDENCE EXCERPTS:\n{_format_chunks(hits)}"
    )
    raw = llm.complete(
        [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}],
        json_mode=True,
    )
    findings = []
    for i, f in enumerate(_parse_findings(raw), 1):
        finding = Finding(
            finding_id=f"{check.id}__{i:02d}",
            check=check.id,
            category=check.category,
            title=f.get("title", check.name),
            finding=f.get("finding", ""),
            severity=f.get("severity", "MEDIUM"),
            confidence=max(0.0, min(1.0, float(f.get("confidence", 0.5)))),
            reason=f.get("reason", ""),
            evidence=_bind_evidence(f.get("evidence", []), collection=collection),
        )
        findings.append(finding)
    return findings


def run_check(
    check: CheckSpec,
    n_results: int = 10,
    llm=None,
    collection=None,
) -> list[Finding]:
    """Retrieve evidence for one check across ALL documents, then extract.

    Cross-document retrieval is the point: a single check can cite
    multiple agreements when issues interact."""
    hits = search(check.query, n_results=n_results, collection=collection)
    if not hits:
        return []
    return extract_findings(check, hits, llm=llm, collection=collection)
