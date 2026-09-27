from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile

from app.agents.due_diligence import run_analysis
from app.analysis.qa import answer_question
from app.analysis.report import build_report
from app.analysis.review import load_findings, review_queue, update_status
from app.config import settings
from app.ingestion.pipeline import ingest_pdf
from app.retrieval.index import list_documents, search

app = FastAPI(title="Due-Diligence Document Agent")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ingest")
async def ingest(file: UploadFile):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF ingestion is supported right now")
    dest = Path(settings.raw_dir) / file.filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(await file.read())
    parsed, chunks = ingest_pdf(dest, settings.processed_dir)
    return {
        "document_id": parsed.document_id,
        "pages": parsed.num_pages,
        "chunks": len(chunks),
    }


@app.get("/documents")
def documents():
    return {"documents": list_documents()}


@app.get("/search")
def search_chunks(q: str, n: int = 8, document_id: str | None = None):
    where = {"document_id": document_id} if document_id else None
    return {"results": search(q, n_results=n, where=where)}


@app.post("/ask")
def ask(payload: dict):
    question = payload.get("question", "").strip()
    if not question:
        raise HTTPException(400, "Missing 'question'")
    return answer_question(question, n_results=payload.get("n_results", 8))


@app.post("/analyze")
def analyze(payload: dict | None = None):
    payload = payload or {}
    return run_analysis(
        task=payload.get("task", "full due-diligence review"),
        check_ids=payload.get("check_ids"),
        processed_dir=settings.processed_dir,
    )


@app.get("/findings")
def findings(review_only: bool = False):
    fs = load_findings()
    if review_only:
        fs = review_queue(fs)
    return {"findings": [f.model_dump() for f in fs]}


@app.post("/findings/{finding_id}/review")
def review(finding_id: str, payload: dict):
    status = payload.get("status", "")
    if status not in ("APPROVED", "REJECTED", "REQUIRES_REVIEW"):
        raise HTTPException(400, "status must be APPROVED|REJECTED|REQUIRES_REVIEW")
    updated = update_status(finding_id, status)
    if updated is None:
        raise HTTPException(404, f"finding '{finding_id}' not found")
    return updated.model_dump()


@app.get("/report")
def report():
    return build_report(load_findings(), list_documents())
