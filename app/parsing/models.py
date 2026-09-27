from pydantic import BaseModel


class PageText(BaseModel):
    page: int  # 1-based page number
    text: str
    ocr: bool = False  # True if text came from OCR fallback, not the text layer


class ParsedDocument(BaseModel):
    document_id: str
    filename: str
    path: str
    num_pages: int
    pages: list[PageText]


class Chunk(BaseModel):
    chunk_id: str
    document_id: str
    filename: str
    page_start: int
    page_end: int
    section_hint: str | None = None
    text: str
