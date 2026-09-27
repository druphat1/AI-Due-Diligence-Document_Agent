"""Structured output schemas.

Every extraction/risk check emits Findings. Two rules keep them honest:

1. The LLM cites a `chunk_id` + `quote`; document/page metadata is then
   resolved from the index itself — the model cannot invent a source.
2. `app/analysis/evidence.py` confirms each quote is a real substring of
   the cited page. Unverifiable evidence -> EVIDENCE_UNVERIFIED.
"""

from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["NO_ISSUE", "LOW", "MEDIUM", "HIGH"]

# AUTO_VERIFIED: checked, nothing wrong (NO_ISSUE findings).
# REQUIRES_REVIEW: real finding, evidence verified — human should confirm.
# EVIDENCE_UNVERIFIED: quote not found on cited page — always in review queue.
# APPROVED / REJECTED: set by the human reviewer.
ReviewStatus = Literal[
    "AUTO_VERIFIED", "REQUIRES_REVIEW", "EVIDENCE_UNVERIFIED", "APPROVED", "REJECTED"
]


class Evidence(BaseModel):
    chunk_id: str = ""          # chunk the LLM cited; resolved to doc/page by us
    document_id: str
    filename: str
    page_start: int
    page_end: int
    quote: str                  # verbatim substring of the cited page's text
    verified: bool | None = None
    match_score: float | None = None


class Finding(BaseModel):
    finding_id: str = ""
    check: str = ""             # which DD check produced this, e.g. "change_of_control"
    category: str               # e.g. "Commercial", "IP", "Employment", "Debt"
    title: str
    finding: str                # what was found
    severity: Severity = "MEDIUM"
    reason: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    status: ReviewStatus = "REQUIRES_REVIEW"
    evidence: list[Evidence] = Field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        return self.status in ("REQUIRES_REVIEW", "EVIDENCE_UNVERIFIED")
