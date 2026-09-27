# Due-Diligence Document Agent

Evidence-backed document analysis for M&A-style due diligence. Every
finding is cited to **document → page → verbatim quote**, then
mechanically verified against the extracted text. The LLM never gets to
assert where evidence lives — it cites a `chunk_id`, and document/page
metadata is resolved from the index itself.

## What it does

```
PDFs → parse (page-level) → chunk (page-aware) → Chroma index
     → per-check retrieval → LLM extraction → Finding objects
     → evidence verification → human review queue → DD report
```

## Stack

| Layer | Choice |
|---|---|
| LLM | Groq (`openai/gpt-oss-120b`) behind `app/llm/provider.py` — swap via `LLM_PROVIDER` (groq/openai/gemini/mock) |
| Embeddings + vector store | ChromaDB (persistent, local MiniLM-L6-v2 embeddings, no API key) |
| Parsing | PyMuPDF, `rapidocr-onnxruntime` fallback for scanned pages |
| API / UI | FastAPI / Streamlit |

## Architecture

```
app/
├── ingestion/pipeline.py    PDF dir → parsed docs + chunks + index
├── parsing/                 pdf_parser.py (per-page text, OCR fallback)
│                            chunker.py    (page-boundary-aware chunks)
├── retrieval/index.py       Chroma: index, search, get_page_text,
│                            get_chunks_by_ids, list_documents
├── extraction/schemas.py    Finding / Evidence (Pydantic)
│           /extract.py      check → retrieved chunks → Findings;
│                            chunk_id → metadata binding (anti-hallucination)
├── analysis/checks.py       the 8-check catalog
│           /evidence.py     quote-vs-page verification
│           /review.py       findings store + approve/reject workflow
│           /report.py       report builder + markdown
│           /qa.py           cited Q&A
└── agents/due_diligence.py  plan checks → run → verify → report
```

## The 8 checks

`change_of_control` · `assignment_restrictions` · `termination_rights` ·
`exclusivity` · `ip_ownership` · `material_liabilities` ·
`debt_guarantees` · `litigation_regulatory`

Each check is a retrieval query + extraction instructions + severity
rubric (`app/analysis/checks.py`).

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
cp .env.example .env            # add GROQ_API_KEY (console.groq.com, free)
```

## Usage

```bash
# demo data room: 6 synthetic contracts covering all 8 checks
python -m scripts.make_sample_docs          # writes data/test/*.pdf

# full pipeline
python -m app.ingestion.pipeline data/test  # parse → chunk → index
python -m app.agents.due_diligence          # plan → extract → verify → report

# or interactively
python -m app.analysis.qa "which contracts require consent on change of control?"
uvicorn app.api.main:app --reload           # API on :8000
streamlit run streamlit_app.py              # UI on :8501
pytest                                      # 13 tests
```

## Example finding

```json
{
  "check": "change_of_control", "category": "Commercial",
  "title": "Change of Control triggers consent and default",
  "severity": "HIGH", "confidence": 0.99, "status": "REQUIRES_REVIEW",
  "evidence": [
    {"filename": "Customer_Contract_01.pdf", "page_start": 2,
     "quote": "...requires the prior written consent of the other party.",
     "verified": true, "match_score": 1.0},
    {"filename": "Loan_Agreement.pdf", "page_start": 3,
     "quote": "...an immediate Event of Default...",
     "verified": true, "match_score": 1.0}
  ]
}
```

## Evidence verification

- LLM output binds `chunk_id` → index metadata (document/page can't be
  fabricated; a fake `chunk_id` resolves to `unresolved` and fails).
- Each quote is fuzzy-matched against the cited page's real extracted
  text. Score < 0.85 → `EVIDENCE_UNVERIFIED`, confidence capped at 0.4,
  automatically queued for human review.
- Verified `NO_ISSUE` findings → `AUTO_VERIFIED`; real findings →
  `REQUIRES_REVIEW`; reviewers then `APPROVED` / `REJECTED`.

## Status lifecycle

`AUTO_VERIFIED` / `REQUIRES_REVIEW` / `EVIDENCE_UNVERIFIED` → human →
`APPROVED` / `REJECTED`

## Limitations

- PDF only (docx has no reliable page numbers — deliberate omission).
- Extraction quality is bounded by retrieval: a clause that never makes
  the top-k chunks can't be cited. `n_results` per check is tunable.
- NO_ISSUE means "nothing found in retrieved evidence," not "proven absent."
- Check selection is LLM-driven with an all-checks fallback; a bad plan
  degrades to running everything, never to running nothing.

## Roadmap

- [ ] `.docx` ingestion (section-level citations instead of pages)
- [ ] LangGraph agent loop for iterative evidence gathering
- [ ] Real data room (SEC EDGAR material-contract exhibits)
- [ ] PostgreSQL persistence, deployment (Project 3)
