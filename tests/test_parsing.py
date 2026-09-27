"""End-to-end parsing test: generate a real PDF with PyMuPDF, parse it,
chunk it, and verify page metadata survives intact.
"""

import pymupdf
import pytest

from app.parsing.chunker import chunk_document
from app.parsing.pdf_parser import parse_pdf

CLAUSE = (
    "This Agreement may not be assigned without the prior written consent "
    "of the other party. In the event of a Change of Control, the Customer "
    "shall provide written notice no fewer than thirty (30) days prior. "
)


@pytest.fixture()
def sample_pdf(tmp_path):
    path = tmp_path / "Customer_Contract_04.pdf"
    doc = pymupdf.open()
    for i in range(1, 4):
        page = doc.new_page()
        body = CLAUSE * 8 if i == 2 else f"Page {i} content. " * 40
        page.insert_textbox(pymupdf.Rect(72, 72, 540, 740), body)
    doc.save(path)
    doc.close()
    return path


def test_parse_pdf_preserves_pages(sample_pdf):
    parsed = parse_pdf(sample_pdf)
    assert parsed.document_id == "customer_contract_04"
    assert parsed.num_pages == 3
    assert [p.page for p in parsed.pages] == [1, 2, 3]
    assert "Change of Control" in parsed.pages[1].text
    assert all(not p.ocr for p in parsed.pages)


def test_chunks_carry_page_metadata(sample_pdf):
    chunks = chunk_document(parse_pdf(sample_pdf))
    assert chunks, "expected at least one chunk"
    for c in chunks:
        assert c.document_id == "customer_contract_04"
        assert c.page_start >= 1 and c.page_end <= 3
        assert c.page_start <= c.page_end
        assert c.text.strip()
    # the clause on page 2 must be locatable to page 2
    clause_chunks = [c for c in chunks if "Change of Control" in c.text]
    assert clause_chunks and all(c.page_start <= 2 <= c.page_end for c in clause_chunks)
