"""Agentic orchestration for a due-diligence task.

Pipeline:  list documents -> plan which checks are relevant -> per check,
retrieve evidence across documents -> extract structured findings ->
verify every quote -> persist for human review -> build report.

Deliberately a plain loop, not a framework: the workflow is linear and
deterministic except for the two LLM calls (planning, extraction).

Usage:  python -m app.agents.due_diligence [task]
"""

import json
import sys

from app.analysis.checks import CHECKS, CHECKS_BY_ID
from app.analysis.evidence import verify_findings
from app.analysis.report import build_report, save_report
from app.analysis.review import save_findings
from app.extraction.extract import run_check
from app.extraction.schemas import Finding
from app.llm.provider import get_llm
from app.retrieval.index import list_documents


def plan_checks(task: str, documents: list[dict], llm=None) -> list[str]:
    """Decide which checks apply, given the task and what's in the room."""
    llm = llm or get_llm()
    catalog = "\n".join(f"- id={c.id}  {c.name} ({c.category})" for c in CHECKS)
    doclist = "\n".join(f"- {d['filename']}" for d in documents)
    raw = llm.complete(
        [
            {
                "role": "system",
                "content": "You are a due-diligence planner. Given a task and a "
                "document list, select which checks to run. Respond with JSON: "
                '{"check_ids": ["..."]}',
            },
            {
                "role": "user",
                "content": f"TASK: {task}\n\nDOCUMENTS:\n{doclist}\n\n"
                f"AVAILABLE CHECKS:\n{catalog}",
            },
        ],
        json_mode=True,
    )
    try:
        ids = json.loads(raw).get("check_ids", [])
    except json.JSONDecodeError:
        ids = []
    selected = [i for i in ids if i in CHECKS_BY_ID]
    return selected or [c.id for c in CHECKS]  # fallback: run everything


def run_analysis(
    task: str = "full due-diligence review",
    check_ids: list[str] | None = None,
    n_results: int = 10,
    llm=None,
    collection=None,
    processed_dir=None,
) -> dict:
    llm = llm or get_llm()
    documents = list_documents(collection=collection)
    if not documents:
        raise RuntimeError("Index is empty — ingest documents first.")

    selected = check_ids or plan_checks(task, documents, llm=llm)
    print(f"Checks selected: {', '.join(selected)}")

    findings: list[Finding] = []
    for cid in selected:
        check = CHECKS_BY_ID[cid]
        fs = run_check(check, n_results=n_results, llm=llm, collection=collection)
        print(f"  {check.name}: {len(fs)} finding(s)")
        findings.extend(fs)

    verify_findings(findings, collection=collection)
    save_findings(findings, processed_dir=processed_dir)

    report = build_report(findings, documents)
    j, m = save_report(report, processed_dir=processed_dir)
    print(f"\n{report['executive_summary']}")
    print(f"Report: {j} / {m}")
    return report


if __name__ == "__main__":
    task = " ".join(sys.argv[1:]) or "full due-diligence review"
    run_analysis(task)
