"""Chroma-backed chunk index.

Chroma's built-in default embedding function (all-MiniLM-L6-v2, local ONNX)
means the retrieval layer needs zero API keys. Metadata on every chunk
(document_id, filename, page range) enables filtered queries and is what
evidence verification later relies on.
"""

import chromadb

from app.config import settings
from app.parsing.models import Chunk


def get_collection(name: str | None = None, chroma_dir: str | None = None):
    client = chromadb.PersistentClient(path=chroma_dir or settings.chroma_dir)
    return client.get_or_create_collection(
        name or settings.chroma_collection,
        metadata={"hnsw:space": "cosine"},
    )


def _metadata(chunk: Chunk) -> dict:
    """Chroma metadata values must be str/int/float/bool — drop Nones."""
    meta = chunk.model_dump(exclude={"text"})
    return {k: v for k, v in meta.items() if v is not None}


def index_chunks(chunks: list[Chunk], collection=None) -> int:
    if not chunks:
        return 0
    coll = collection or get_collection()
    coll.upsert(
        ids=[c.chunk_id for c in chunks],
        documents=[c.text for c in chunks],
        metadatas=[_metadata(c) for c in chunks],
    )
    return len(chunks)


def search(
    query: str,
    n_results: int = 8,
    where: dict | None = None,
    collection=None,
) -> list[dict]:
    """Return hits as [{chunk_id, text, metadata, distance}], best first."""
    coll = collection or get_collection()
    res = coll.query(
        query_texts=[query],
        n_results=n_results,
        where=where,
        include=["documents", "metadatas", "distances"],
    )
    hits = []
    for i, chunk_id in enumerate(res["ids"][0]):
        hits.append(
            {
                "chunk_id": chunk_id,
                "text": res["documents"][0][i],
                "metadata": res["metadatas"][0][i],
                "distance": res["distances"][0][i],
            }
        )
    return hits


def get_page_text(document_id: str, page: int, collection=None) -> str:
    """Fetch all chunk text for a specific document page — used by the
    evidence verifier to confirm a quoted clause really lives on the
    cited page."""
    coll = collection or get_collection()
    res = coll.get(
        where={
            "$and": [
                {"document_id": document_id},
                {"page_start": {"$lte": page}},
                {"page_end": {"$gte": page}},
            ]
        },
        include=["documents"],
    )
    return "\n\n".join(res["documents"])


def get_chunks_by_ids(chunk_ids: list[str], collection=None) -> dict[str, dict]:
    """Resolve chunk ids to their authoritative metadata.

    Extraction asks the LLM to cite chunk_ids; this function is how we
    bind each citation to the real document/page instead of trusting
    whatever the model claims."""
    if not chunk_ids:
        return {}
    coll = collection or get_collection()
    res = coll.get(ids=chunk_ids, include=["documents", "metadatas"])
    return {
        cid: {"text": doc, "metadata": meta}
        for cid, doc, meta in zip(res["ids"], res["documents"], res["metadatas"])
    }


def list_documents(collection=None) -> list[dict]:
    """Distinct documents in the index: document_id, filename, page range."""
    coll = collection or get_collection()
    res = coll.get(include=["metadatas"])
    docs: dict[str, dict] = {}
    for meta in res["metadatas"]:
        d = docs.setdefault(
            meta["document_id"],
            {
                "document_id": meta["document_id"],
                "filename": meta["filename"],
                "max_page": 0,
                "chunks": 0,
            },
        )
        d["max_page"] = max(d["max_page"], meta["page_end"])
        d["chunks"] += 1
    return sorted(docs.values(), key=lambda d: d["document_id"])
