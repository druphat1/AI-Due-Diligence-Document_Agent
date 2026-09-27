"""Page-boundary-aware chunking.

Rules:
- Chunks never cross a page boundary unless merging *tiny* pages, and when
  they do, page_start/page_end truthfully record the span.
- Pages with substantial text are chunked alone (split into pieces only if
  a single page exceeds max_chars).
- Runs of consecutive tiny pages are merged so we don't index stubs.

Exact page attribution is what makes evidence citation trustworthy later.
"""

import re

from app.parsing.models import Chunk, ParsedDocument

MAX_CHARS = 1600
OVERLAP = 150
MIN_CHARS = 300


def _split_text(text: str, max_chars: int, overlap: int) -> list[str]:
    """Split long text into <= max_chars pieces, breaking on whitespace."""
    if len(text) <= max_chars:
        return [text]
    pieces, start = [], 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            # prefer breaking at a paragraph/sentence/word boundary
            window = text[start:end]
            cut = max(window.rfind("\n\n"), window.rfind(". "), window.rfind(" "))
            if cut > max_chars * 0.5:
                end = start + cut + 1
        pieces.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [p for p in pieces if p]


def _section_hint(text: str) -> str | None:
    """Heuristic: first line is a heading if it's short and looks like one."""
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    if not first or len(first) > 90:
        return None
    letters = re.sub(r"[^A-Za-z]", "", first)
    if letters and letters.upper() == letters and len(letters) > 3:
        return first
    if re.match(r"^(\d+(\.\d+)*|[IVX]+\.|[A-Z]\.)\s+\S", first):
        return first
    if first.endswith(":"):
        return first
    return None


def chunk_document(
    doc: ParsedDocument,
    max_chars: int = MAX_CHARS,
    overlap: int = OVERLAP,
    min_chars: int = MIN_CHARS,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    run_text, run_start = "", None
    seq = 0

    def add_chunk(text: str, p_start: int, p_end: int) -> None:
        nonlocal seq
        seq += 1
        page_ref = f"p{p_start:03d}" if p_start == p_end else f"p{p_start:03d}-{p_end:03d}"
        chunks.append(
            Chunk(
                chunk_id=f"{doc.document_id}__{page_ref}_c{seq:03d}",
                document_id=doc.document_id,
                filename=doc.filename,
                page_start=p_start,
                page_end=p_end,
                section_hint=_section_hint(text),
                text=text,
            )
        )

    def flush_run(end_page: int) -> None:
        nonlocal run_text, run_start
        if run_text.strip() and run_start is not None:
            add_chunk(run_text.strip(), run_start, end_page)
        run_text, run_start = "", None

    last_page = 0
    for p in doc.pages:
        text = p.text.strip()
        last_page = p.page
        if not text:
            continue
        if len(text) < min_chars:
            if run_start is None:
                run_start = p.page
            run_text += ("\n\n" if run_text else "") + text
            if len(run_text) >= max_chars:
                flush_run(p.page)
            continue
        flush_run(p.page - 1)
        for piece in _split_text(text, max_chars, overlap):
            add_chunk(piece, p.page, p.page)

    flush_run(last_page)
    return chunks
