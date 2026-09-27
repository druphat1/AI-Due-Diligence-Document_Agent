import json
from pathlib import Path

import streamlit as st

from app.agents.due_diligence import run_analysis
from app.analysis.checks import CHECKS
from app.analysis.qa import answer_question
from app.analysis.report import build_report, to_markdown
from app.analysis.review import load_findings, review_queue, save_findings, update_status
from app.config import settings
from app.extraction.schemas import Finding
from app.ingestion.pipeline import ingest_pdf
from app.retrieval.index import list_documents, search

st.set_page_config(page_title="Due-Diligence Document Agent", layout="wide")
st.title("Due-Diligence Document Agent")

SEV_COLOR = {"HIGH": "[!]", "MEDIUM": "[~]", "LOW": "[-]", "NO_ISSUE": "[ok]"}

tab_room, tab_ask, tab_analyze, tab_report = st.tabs(
    ["Data Room", "Ask", "Analysis & Review", "Report"]
)

# ---------- Data Room ----------
with tab_room:
    st.header("Data Room")
    uploads = st.file_uploader("Upload PDFs", type=["pdf"], accept_multiple_files=True)
    if st.button("Ingest uploaded files", disabled=not uploads):
        for up in uploads:
            dest = Path(settings.raw_dir) / up.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(up.getvalue())
            parsed, chunks = ingest_pdf(dest, settings.processed_dir)
            st.success(f"{parsed.filename}: {parsed.num_pages} pages → {len(chunks)} chunks")
    docs = list_documents()
    if docs:
        st.subheader("Indexed documents")
        st.dataframe(docs, use_container_width=True)
    with st.expander("Raw chunk search (no LLM)"):
        q = st.text_input("Retrieval query", key="search_q")
        if q:
            for h in search(q):
                m = h["metadata"]
                st.markdown(
                    f"**{m['filename']}** · p.{m['page_start']}"
                    f" · `{h['chunk_id']}` · dist {h['distance']:.3f}"
                )
                st.caption(h["text"][:400] + ("…" if len(h["text"]) > 400 else ""))

# ---------- Ask ----------
with tab_ask:
    question = st.text_input(
        "Question",
        placeholder="Which contracts require consent if ownership of the company changes?",
    )
    if question:
        try:
            result = answer_question(question)
        except Exception as e:
            st.error(f"LLM call failed (is your API key set in .env?): {e}")
        else:
            st.markdown("### Answer")
            st.write(result.get("answer", ""))
            st.caption(f"Confidence: {result.get('confidence', 0):.2f}")
            for c in result.get("citations", []):
                pages = (
                    f"p.{c['page_start']}"
                    if c.get("page_start") == c.get("page_end")
                    else f"pp.{c.get('page_start')}-{c.get('page_end')}"
                )
                with st.expander(f"{c['filename']} — {pages}"):
                    st.markdown(f"> {c['quote']}")

# ---------- Analysis & Review ----------
with tab_analyze:
    st.header("Run Due-Diligence Analysis")
    selected = st.multiselect(
        "Checks (leave empty to let the agent choose)",
        options=[c.id for c in CHECKS],
        format_func=lambda i: next(c.name for c in CHECKS if c.id == i),
    )
    if st.button("Run analysis", type="primary"):
        try:
            with st.spinner("Retrieving evidence, extracting, verifying…"):
                report = run_analysis(
                    check_ids=selected or None, processed_dir=settings.processed_dir
                )
            st.success(report["executive_summary"])
        except Exception as e:
            st.error(f"Analysis failed: {e}")

    findings = load_findings()
    if findings:
        queue_ids = {f.finding_id for f in review_queue(findings)}
        st.subheader(f"Findings ({len(findings)}) — {len(queue_ids)} awaiting review")
        for f in findings:
            icon = SEV_COLOR.get(f.severity, "⚪")
            flag = " — needs review" if f.finding_id in queue_ids else ""
            with st.expander(f"{icon} [{f.severity}] {f.title} · `{f.status}`{flag}"):
                st.write(f.finding)
                st.caption(f"Check: `{f.check}` · {f.reason}")
                st.progress(f.confidence, text=f"confidence {f.confidence:.2f}")
                for ev in f.evidence:
                    badge = "verified" if ev.verified else "UNVERIFIED"
                    pages = (
                        f"p.{ev.page_start}"
                        if ev.page_start == ev.page_end
                        else f"pp.{ev.page_start}-{ev.page_end}"
                    )
                    st.markdown(
                        f"**{ev.filename}** · {pages} · {badge} "
                        f"(score {ev.match_score or 0:.2f})"
                    )
                    st.markdown(f"> {ev.quote}")
                c1, c2, c3 = st.columns(3)
                if c1.button("Approve", key=f"ok_{f.finding_id}"):
                    update_status(f.finding_id, "APPROVED")
                    st.rerun()
                if c2.button("Reject", key=f"no_{f.finding_id}"):
                    update_status(f.finding_id, "REJECTED")
                    st.rerun()
                if c3.button("Request review", key=f"rev_{f.finding_id}"):
                    update_status(f.finding_id, "REQUIRES_REVIEW")
                    st.rerun()

# ---------- Report ----------
with tab_report:
    findings = load_findings()
    if not findings:
        st.info("Run an analysis first.")
    else:
        report = build_report(findings, list_documents())
        st.markdown(to_markdown(report))
        c1, c2 = st.columns(2)
        c1.download_button(
            "Download report.md", to_markdown(report), "due_diligence_report.md"
        )
        c2.download_button(
            "Download report.json",
            json.dumps(report, indent=2),
            "due_diligence_report.json",
        )
