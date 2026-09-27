"""PDF text extraction with per-page granularity and OCR fallback.

Every page's text is recorded separately so downstream chunks can cite
exact page numbers. Pages with no text layer (scanned PDFs) fall back to
RapidOCR.
"""

import hashlib
import re
from pathlib import Path

import pymupdf

from app.parsing.models import PageText, ParsedDocument

_ocr_engine = None


def _get_ocr():
    """Lazy-load RapidOCR so the onnxruntime dep is only paid when needed."""
    global _ocr_engine
    if _ocr_engine is None:
        from rapidocr_onnxruntime import RapidOCR

        _ocr_engine = RapidOCR()
    return _ocr_engine


def _ocr_page(page: pymupdf.Page) -> str:
    pix = page.get_pixmap(dpi=200)
    import numpy as np

    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
        pix.height, pix.width, pix.n
    )
    result, _ = _get_ocr()(img)
    if not result:
        return ""
    return "\n".join(line[1] for line in result)


def document_id_for(path: Path) -> str:
    """Stable, filesystem-safe document id derived from the filename."""
    stem = re.sub(r"[^a-z0-9]+", "_", path.stem.lower()).strip("_")
    return stem or hashlib.sha1(path.name.encode()).hexdigest()[:10]


def parse_pdf(path: str | Path) -> ParsedDocument:
    path = Path(path)
    pages: list[PageText] = []
    with pymupdf.open(path) as doc:
        for i, page in enumerate(doc):
            text = page.get_text("text").strip()
            ocr = False
            if not text:
                text, ocr = _ocr_page(page).strip(), True
            pages.append(PageText(page=i + 1, text=text, ocr=ocr))
    return ParsedDocument(
        document_id=document_id_for(path),
        filename=path.name,
        path=str(path),
        num_pages=len(pages),
        pages=pages,
    )
