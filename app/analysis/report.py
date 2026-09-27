"""Due-diligence report: executive summary + findings grouped by category.

The executive summary is generated deterministically from the findings —
it can only state what the findings state. An optional LLM polish is
available but the fallback never depends on it.
"""

import json
from pathlib import Path

from app.config import settings
from app.extraction.schemas import Finding

_SEV_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "NO_ISSUE": 3}


def _pages_str(ev) -> str:
    return f"p.{ev.page_start}" if ev.page_start == ev.page_end else f"pp.{ev.page_start}-{ev.page_end}"


def build_report(findings: list[Finding], documents: list[dict] | None = None) -> dict:
    by_sev = {}
    for f in findings:
        by_sev[f.severity] = by_sev.get(f.severity, 0) + 1

    by_cat: dict[str, list[Finding]] = {}
    for f in findings:
        by_cat.setdefault(f.category, []).append(f)
    for cat in by_cat:
        by_cat[cat].sort(key=lambda f: (_SEV_ORDER[f.severity], -f.confidence))

    high = [f for f in findings if f.severity == "HIGH"]
    unverified = [f for f in findings if f.status == "EVIDENCE_UNVERIFIED"]

    summary = (
        f"Analyzed {len(documents or [])} documents; "
        f"{len(findings)} findings: "
        + ", ".join(f"{n} {s}" for s, n in sorted(by_sev.items(), key=lambda x: _SEV_ORDER[x[0]]))
        + f". {len(unverified)} finding(s) failed evidence verification and require review."
    )
    if high:
        summary += " Top risks: " + "; ".join(
            f"{f.title} ({f.evidence[0].filename}, {_pages_str(f.evidence[0])})"
            if f.evidence else f.title
            for f in high[:5]
        ) + "."

    return {
        "executive_summary": summary,
        "stats": {
            "documents": len(documents or []),
            "findings": len(findings),
            "by_severity": by_sev,
            "unverified": len(unverified),
            "pending_review": sum(1 for f in findings if f.needs_review),
        },
        "findings_by_category": {
            cat: [f.model_dump() for f in fs] for cat, fs in by_cat.items()
        },
    }


def to_markdown(report: dict) -> str:
    lines = ["# Due-Diligence Report", "", "## Executive Summary", "", report["executive_summary"], ""]
    s = report["stats"]
    lines += [
        f"- Findings: **{s['findings']}** | "
        + " · ".join(f"{k}: {v}" for k, v in sorted(s["by_severity"].items(), key=lambda x: _SEV_ORDER[x[0]])),
        f"- Pending review: **{s['pending_review']}** (unverified: {s['unverified']})",
        "",
    ]
    for cat, findings in report["findings_by_category"].items():
        lines += [f"## {cat}", ""]
        for f in findings:
            lines += [
                f"### [{f['severity']}] {f['title']}",
                "",
                f"- **Check:** `{f['check']}`",
                f"- **Finding:** {f['finding']}",
                f"- **Reason:** {f['reason']}",
                f"- **Confidence:** {f['confidence']:.2f} · **Status:** `{f['status']}`",
                "- **Evidence:**",
            ]
            for ev in f["evidence"]:
                badge = "verified" if ev.get("verified") else "UNVERIFIED"
                pages = (
                    f"p.{ev['page_start']}"
                    if ev["page_start"] == ev["page_end"]
                    else f"pp.{ev['page_start']}-{ev['page_end']}"
                )
                lines.append(
                    f"  - `{ev['filename']}` {pages} "
                    f"[{badge} {ev.get('match_score') or 0:.2f}]\n"
                    f"    > {ev['quote']}"
                )
            lines.append("")
    return "\n".join(lines)


def save_report(report: dict, processed_dir=None) -> tuple[Path, Path]:
    out = Path(processed_dir or settings.processed_dir)
    out.mkdir(parents=True, exist_ok=True)
    j, m = out / "report.json", out / "report.md"
    j.write_text(json.dumps(report, indent=2), encoding="utf-8")
    m.write_text(to_markdown(report), encoding="utf-8")
    return j, m
