"""Analysis-layer tests: extraction, checks, verification, review, e2e.

Uses an ephemeral Chroma collection (no files touched) and MockProvider
(no API calls). The mock quotes chunk text verbatim, so its findings
verify — hallucination cases are constructed explicitly.
"""

import json

import chromadb
import pymupdf
import pytest

from app.agents.due_diligence import plan_checks, run_analysis
from app.analysis.checks import CHECKS, CHECKS_BY_ID
from app.analysis.evidence import quote_in_text, verify_finding
from app.analysis.review import load_findings, review_queue, update_status
from app.extraction.extract import _bind_evidence, extract_findings
from app.extraction.schemas import Evidence, Finding
from app.ingestion.pipeline import ingest_pdf
from app.llm.provider import MockProvider
from app.parsing.chunker import chunk_document
from app.parsing.models import Chunk
from app.retrieval.index import get_chunks_by_ids, index_chunks, list_documents, search
from scripts.make_sample_docs import DOCS, EXPECTED, make_pdf


@pytest.fixture()
def collection():
    # unique name: ephemeral clients share a backend in some chroma versions
    import uuid

    return chromadb.EphemeralClient().get_or_create_collection(f"t_{uuid.uuid4().hex[:8]}")


def _chunks(doc_id: str, filename: str, page: int, text: str) -> Chunk:
    return Chunk(
        chunk_id=f"{doc_id}__p{page:03d}_c001",
        document_id=doc_id,
        filename=filename,
        page_start=page,
        page_end=page,
        text=text,
    )


# ---------- check catalog ----------

def test_eight_checks_defined():
    assert len(CHECKS) == 8
    expected = {
        "change_of_control", "assignment_restrictions", "termination_rights",
        "exclusivity", "ip_ownership", "material_liabilities",
        "debt_guarantees", "litigation_regulatory",
    }
    assert set(CHECKS_BY_ID) == expected
    for c in CHECKS:
        assert c.query and c.instructions and c.severity_hint and c.category


# ---------- multi-document retrieval ----------

def test_multi_document_retrieval(collection):
    index_chunks([
        _chunks("contract_a", "A.pdf", 2, "Assignment requires prior written consent."),
        _chunks("contract_b", "B.pdf", 5, "The loan is guaranteed by the parent company."),
        _chunks("contract_c", "C.pdf", 1, "General boilerplate about notices."),
    ], collection=collection)
    hits = search("guarantee loan", n_results=2, collection=collection)
    assert hits and hits[0]["metadata"]["document_id"] == "contract_b"
    docs = list_documents(collection=collection)
    assert {d["document_id"] for d in docs} == {"contract_a", "contract_b", "contract_c"}


# ---------- extraction & evidence binding ----------

def test_extraction_binds_chunk_metadata(collection):
    index_chunks([
        _chunks("contract_a", "A.pdf", 7, "A Change of Control requires prior written consent."),
    ], collection=collection)
    hits = search("change of control consent", collection=collection)
    findings = extract_findings(
        CHECKS_BY_ID["change_of_control"], hits, llm=MockProvider(), collection=collection
    )
    assert len(findings) == 1
    f = findings[0]
    assert f.check == "change_of_control" and f.category == "Commercial"
    ev = f.evidence[0]
    # metadata came from the index, not the model
    assert ev.document_id == "contract_a" and ev.page_start == 7
    Finding(**f.model_dump())  # schema-valid


def test_hallucinated_chunk_id_fails_verification(collection):
    index_chunks([_chunks("a", "A.pdf", 1, "Real text.")], collection=collection)
    bound = _bind_evidence(
        [{"chunk_id": "does_not_exist", "quote": "made up"}], collection=collection
    )
    assert bound[0].document_id == "unresolved" and bound[0].verified is False


# ---------- evidence verification ----------

def test_verify_finding_real_quote(collection):
    index_chunks([_chunks("a", "A.pdf", 3, "The Customer may terminate for convenience.")],
                 collection=collection)
    f = Finding(
        check="termination_rights", category="Commercial", title="t", finding="x",
        severity="HIGH", confidence=0.9,
        evidence=[Evidence(chunk_id="a__p003_c001", document_id="a", filename="A.pdf",
                           page_start=3, page_end=3,
                           quote="terminate for convenience")],
    )
    verify_finding(f, collection=collection)
    assert f.status == "REQUIRES_REVIEW" and f.evidence[0].verified is True


def test_verify_finding_hallucinated_quote(collection):
    index_chunks([_chunks("a", "A.pdf", 3, "The Customer may terminate for convenience.")],
                 collection=collection)
    f = Finding(
        check="termination_rights", category="Commercial", title="t", finding="x",
        severity="HIGH", confidence=0.95,
        evidence=[Evidence(chunk_id="a__p003_c001", document_id="a", filename="A.pdf",
                           page_start=3, page_end=3,
                           quote="The company owes a five million dollar penalty.")],
    )
    verify_finding(f, collection=collection)
    assert f.status == "EVIDENCE_UNVERIFIED" and f.confidence <= 0.4


def test_quote_scoring():
    text = "The Licensor retains all right, title, and ownership of the Platform IP."
    assert quote_in_text("retains all right, title, and ownership", text) == 1.0
    assert quote_in_text("completely unrelated obligation", text) < 0.85


# ---------- severity ----------

def test_severity_values():
    for sev in ("NO_ISSUE", "LOW", "MEDIUM", "HIGH"):
        Finding(category="c", title="t", finding="x", severity=sev)
    with pytest.raises(Exception):
        Finding(category="c", title="t", finding="x", severity="CRITICAL")


# ---------- planning & review ----------

def test_plan_checks_mock():
    llm = MockProvider()
    docs = [{"document_id": "a", "filename": "A.pdf"}]
    selected = plan_checks("full review", docs, llm=llm)
    assert set(selected) == set(CHECKS_BY_ID)


def test_review_workflow(tmp_path):
    f = Finding(finding_id="f1", category="c", title="t", finding="x",
                severity="HIGH", status="EVIDENCE_UNVERIFIED")
    from app.analysis.review import save_findings
    save_findings([f], processed_dir=tmp_path)
    assert review_queue(load_findings(tmp_path))  # unverified is queued
    update_status("f1", "APPROVED", processed_dir=tmp_path)
    loaded = load_findings(tmp_path)
    assert loaded[0].status == "APPROVED" and not review_queue(loaded)


# ---------- end-to-end ----------

def test_end_to_end(tmp_path, collection):
    raw = tmp_path / "raw"
    raw.mkdir()
    for name, clauses in DOCS.items():
        make_pdf(raw / name, num_pages=5, clauses=clauses)
    for pdf in sorted(raw.glob("*.pdf")):
        ingest_pdf(pdf, tmp_path / "processed", collection=collection)

    report = run_analysis(
        task="full review", llm=MockProvider(), collection=collection,
        processed_dir=tmp_path / "processed",
    )
    assert report["stats"]["documents"] == len(DOCS) == 6
    assert report["stats"]["findings"] >= len(CHECKS)
    # every finding cites real evidence that verified
    for cat, fs in report["findings_by_category"].items():
        for f in fs:
            assert f["evidence"], f"finding without evidence: {f['title']}"
            assert all(e["verified"] for e in f["evidence"])
    # every expected check has a finding
    covered = {f["check"] for fs in report["findings_by_category"].values() for f in fs}
    assert covered == set(EXPECTED)
