"""Ingestion pipeline: raw PDFs -> parsed docs -> chunks -> Chroma index.

Usage:
    python -m app.ingestion.pipeline [raw_dir]
"""

import json
import sys
from pathlib import Path

from app.config import settings
from app.parsing.chunker import chunk_document
from app.parsing.models import Chunk, ParsedDocument
from app.parsing.pdf_parser import parse_pdf
from app.retrieval.index import index_chunks


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def ingest_pdf(
    path: str | Path, processed_dir: str | Path, collection=None
) -> tuple[ParsedDocument, list[Chunk]]:
    processed_dir = Path(processed_dir)
    parsed = parse_pdf(path)
    chunks = chunk_document(parsed)

    _write_json(
        processed_dir / "documents" / f"{parsed.document_id}.json",
        parsed.model_dump(),
    )
    _write_jsonl(
        processed_dir / "chunks" / f"{parsed.document_id}.jsonl",
        [c.model_dump() for c in chunks],
    )
    index_chunks(chunks, collection=collection)
    return parsed, chunks


def ingest_directory(
    raw_dir: str | Path | None = None,
    processed_dir: str | Path | None = None,
    collection=None,
) -> dict:
    raw_dir = Path(raw_dir or settings.raw_dir)
    processed_dir = Path(processed_dir or settings.processed_dir)
    pdfs = sorted(raw_dir.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {raw_dir}")
        return {"documents": 0, "chunks": 0}

    total_chunks = 0
    for pdf in pdfs:
        parsed, chunks = ingest_pdf(pdf, processed_dir, collection=collection)
        ocr_pages = sum(1 for p in parsed.pages if p.ocr)
        total_chunks += len(chunks)
        print(
            f"{parsed.filename}: {parsed.num_pages} pages "
            f"({ocr_pages} via OCR) -> {len(chunks)} chunks"
        )

    print(f"\nIngested {len(pdfs)} documents -> {total_chunks} chunks")
    return {"documents": len(pdfs), "chunks": total_chunks}


if __name__ == "__main__":
    ingest_directory(sys.argv[1] if len(sys.argv) > 1 else None)
