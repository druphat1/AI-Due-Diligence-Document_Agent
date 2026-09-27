"""Evidence verification — the trust layer.

Each Evidence item carries a quote + page citation resolved from the
index. Here we check the quote actually appears in that page's extracted
text (normalized fuzzy substring match — not semantic similarity, so a
hallucinated quote fails loudly) and stamp verified/match_score on it.

Status transitions after verification:
  any evidence verified  -> keep severity; NO_ISSUE -> AUTO_VERIFIED,
                            issues stay REQUIRES_REVIEW
  nothing verified       -> EVIDENCE_UNVERIFIED, confidence capped at 0.4
"""

import difflib
import re

from app.extraction.schemas import Finding
from app.retrieval.index import get_page_text


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def quote_in_text(quote: str, text: str) -> float:
    """Similarity score in [0,1] of the best matching window of `text`."""
    q, t = _normalize(quote), _normalize(text)
    if not q or not t:
        return 0.0
    if q in t:
        return 1.0
    # sliding window fuzzy match over windows roughly the quote's length
    best = 0.0
    words_t = t.split(" ")
    q_words = len(q.split(" "))
    step = max(1, q_words // 4)
    for i in range(0, len(words_t), step):
        window = " ".join(words_t[i : i + q_words + 2])
        best = max(best, difflib.SequenceMatcher(None, q, window).ratio())
    return best


def verify_finding(
    finding: Finding, collection=None, threshold: float = 0.85
) -> Finding:
    if not finding.evidence:
        finding.status = "EVIDENCE_UNVERIFIED"
        finding.confidence = min(finding.confidence, 0.4)
        return finding

    verified_any = False
    for ev in finding.evidence:
        if ev.verified is False and ev.match_score == 0.0:
            continue  # unresolved chunk_id — already failed
        page_text = get_page_text(ev.document_id, ev.page_start, collection=collection)
        ev.match_score = quote_in_text(ev.quote, page_text)
        ev.verified = ev.match_score >= threshold
        verified_any = verified_any or ev.verified

    if not verified_any:
        finding.status = "EVIDENCE_UNVERIFIED"
        finding.confidence = min(finding.confidence, 0.4)
    elif finding.severity == "NO_ISSUE":
        finding.status = "AUTO_VERIFIED"
    return finding


def verify_findings(
    findings: list[Finding], collection=None, threshold: float = 0.85
) -> list[Finding]:
    return [verify_finding(f, collection=collection, threshold=threshold) for f in findings]
