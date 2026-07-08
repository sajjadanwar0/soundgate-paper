"""Render the incident corpus from seeds.INCIDENTS.

Writes:
  results/incidents.jsonl  -- one JSON object per incident (machine-readable)
  results/INCIDENTS.md     -- the human-readable evidence table

The counts separate DIRECT rows (report exhibits a stop-primitive failure)
from ADJACENT and CONTEXT rows, so the corpus cannot be read as inflating the
direct evidence. Nothing here fabricates: fields that were not observed are
rendered as blank / VERIFY exactly as stored in seeds.py.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from .seeds import INCIDENTS, QUERIES, UNVERIFIED_LEADS

RESULTS = Path(__file__).resolve().parents[2] / "results"

AXIS_NAME = {
    "A1": "A1 sibling leak (parallel effect while gate pending)",
    "A2": "A2 replay (resume re-executes pre-gate node/effect)",
    "A3": "A3 cancellation orphan (cancel does not stop in-flight effect)",
    "A4": "A4 timeout zombie (timeout fires; effect proceeds anyway)",
}
STRENGTH_ORDER = {"direct": 0, "adjacent": 1, "context": 2}


def _ref(rec: dict) -> str:
    """Human label, e.g. 'langgraph#6208' or 'forum#3265' or an article host."""
    repo = rec["repo"]
    if rec["id"] is None:
        return repo
    if repo.endswith("langgraph"):
        return f"langgraph#{rec['id']}"
    if repo.endswith("langgraphjs"):
        return f"langgraphjs#{rec['id']}"
    if repo == "forum.langchain.com":
        return f"forum#{rec['id']}"
    if repo.endswith("crewAI"):
        return f"crewai#{rec['id']}"
    return f"{repo}#{rec['id']}"


def write_jsonl() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    with (RESULTS / "incidents.jsonl").open("w") as fh:
        for rec in INCIDENTS:
            fh.write(json.dumps(rec) + "\n")


def render_md() -> str:
    direct = [r for r in INCIDENTS if r["evidence_strength"] == "direct"]
    adjacent = [r for r in INCIDENTS if r["evidence_strength"] == "adjacent"]
    context = [r for r in INCIDENTS if r["evidence_strength"] == "context"]

    lines: list[str] = []
    lines.append("# Incident corpus -- agent-framework stop-primitive failures")
    lines.append("")
    lines.append("Prevalence evidence for the paper. Every row was confirmed by "
                 "reading the actual issue/thread on 2026-07-02 (see `verified_via`). "
                 "Rows are grouped by evidence strength so the DIRECT count -- reports "
                 "that actually exhibit a node/effect re-executing or a parallel-pending "
                 "effect mishandled -- stands on its own.")
    lines.append("")
    lines.append("Generated from `src/corpus/seeds.py` by `corpus-render`. "
                 "Run `corpus-enrich` to fill authoritative state/labels/dates from the "
                 "GitHub API (fields left blank below were not directly observed and must "
                 "be enriched before any claim depends on them).")
    lines.append("")

    # headline counts
    lines.append("## Counts")
    lines.append("")
    lines.append(f"- DIRECT incidents (exhibit a stop-primitive failure): **{len(direct)}**")
    lines.append(f"- ADJACENT (same root cause, no leaked effect shown): **{len(adjacent)}**")
    lines.append(f"- CONTEXT (user questions / practitioner articles): **{len(context)}**")
    repos = Counter(r["repo"] for r in INCIDENTS)
    lines.append(f"- Distinct sources: {', '.join(f'{k} ({v})' for k, v in sorted(repos.items()))}")
    ax = Counter(r["axis"] for r in direct)
    lines.append("- DIRECT rows by axis: "
                 + ", ".join(f"{k} ({ax[k]})" for k in sorted(ax)))
    dated = [r["created"] for r in INCIDENTS if r["created"]]
    if dated:
        lines.append(f"- Date span (observed): {min(dated)} to {max(dated)}")
    lines.append("")
    lines.append("> Honest scope: this corpus is LangGraph-dominated because LangGraph "
                 "has the most-used explicit HITL/interrupt surface and the largest public "
                 "tracker, so its failures are the most-reported. It is a lower bound on "
                 "occurrence (an issue means at least one user hit it and filed), not a "
                 "rate. The keyless probes (probes/results/MATRIX.md) supply the "
                 "cross-framework universality that the issue corpus alone cannot; the two "
                 "are complementary. Cancellation/timeout (A3/A4) surfaces mostly as "
                 "user 'how do I even stop this' threads and cancel-loses-state bugs "
                 "rather than crisp effect-leak repros -- reported as-is.")
    lines.append("")

    def table(rows: list[dict], title: str, note: str) -> None:
        rows = sorted(rows, key=lambda r: (STRENGTH_ORDER[r["evidence_strength"]],
                                           r["axis"], r["created"] or "0000"))
        lines.append(f"## {title}")
        lines.append("")
        lines.append(note)
        lines.append("")
        lines.append("| ref | axis | date | source | one-line symptom |")
        lines.append("|---|---|---|---|---|")
        for r in rows:
            date = r["created"] or "VERIFY"
            src = {"issue": "gh issue", "discussion": "gh disc.", "forum": "forum",
                   "article": "article"}.get(r["kind"], r["kind"])
            sym = r["symptom"].replace("|", "\\|")
            lines.append(f"| [{_ref(r)}]({r['url']}) | {r['axis']} | {date} | {src} | {sym} |")
        lines.append("")

    table(direct, "Direct incidents",
          "Each report shows a node/effect re-executing on resume (A2) or a "
          "parallel-pending approval/effect mishandled (A1).")
    table(adjacent, "Adjacent incidents",
          "Same underlying cause (no per-interrupt barrier / underspecified "
          "cancellation) but the report does not itself demonstrate a leaked side effect.")
    table(context, "Context (not bug reports)",
          "User questions and practitioner write-ups establishing the problem is "
          "real and actively worked around in the field.")

    # queries + unverified
    lines.append("## Reproducibility -- verbatim search queries (2026-07-02)")
    lines.append("")
    for q in QUERIES:
        lines.append(f"- `{q['tag']}`: {q['query']}")
    lines.append("")
    lines.append("## Unverified leads (recorded, NOT counted as evidence)")
    lines.append("")
    for u in UNVERIFIED_LEADS:
        lines.append(f"- **{u['ref']}** -- {u['note']}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    write_jsonl()
    md = render_md()
    (RESULTS / "INCIDENTS.md").write_text(md)
    direct = sum(1 for r in INCIDENTS if r["evidence_strength"] == "direct")
    print(f"wrote results/incidents.jsonl ({len(INCIDENTS)} records) and "
          f"results/INCIDENTS.md ({direct} direct)")


if __name__ == "__main__":
    main()