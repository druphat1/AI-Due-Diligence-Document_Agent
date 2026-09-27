"""Human review workflow.

Findings persist to data/processed/findings.json. Reviewers approve,
reject, or send back for review. Anything EVIDENCE_UNVERIFIED lands in
the review queue automatically.
"""

import json
from pathlib import Path

from app.config import settings
from app.extraction.schemas import Finding, ReviewStatus

REVIEW_QUEUE_STATUSES = {"REQUIRES_REVIEW", "EVIDENCE_UNVERIFIED"}


def _store_path(processed_dir: str | Path | None = None) -> Path:
    return Path(processed_dir or settings.processed_dir) / "findings.json"


def save_findings(findings: list[Finding], processed_dir=None) -> Path:
    path = _store_path(processed_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([f.model_dump() for f in findings], indent=2), encoding="utf-8"
    )
    return path


def load_findings(processed_dir=None) -> list[Finding]:
    path = _store_path(processed_dir)
    if not path.exists():
        return []
    return [Finding(**f) for f in json.loads(path.read_text(encoding="utf-8"))]


def update_status(
    finding_id: str, status: ReviewStatus, processed_dir=None
) -> Finding | None:
    findings = load_findings(processed_dir)
    target = next((f for f in findings if f.finding_id == finding_id), None)
    if target is None:
        return None
    target.status = status
    save_findings(findings, processed_dir)
    return target


def review_queue(findings: list[Finding]) -> list[Finding]:
    """Findings a human must look at — includes every unverified one."""
    return [f for f in findings if f.status in REVIEW_QUEUE_STATUSES]
