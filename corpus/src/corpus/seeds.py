"""Incident corpus -- single source of truth.

This module holds (a) the verbatim search queries used to build the corpus,
for reproducibility, and (b) the verified incident records. render.py turns
INCIDENTS into results/incidents.jsonl and results/INCIDENTS.md; enrich.py
re-fetches authoritative GitHub metadata to fill/verify fields.

VERIFICATION DISCIPLINE (this is prevalence evidence for a paper):
  - Every record was confirmed by locating the actual issue/thread and
    reading its title + body snippet on 2026-07-02 via web search of the
    public GitHub / LangChain-forum pages. The `verified_via` field records
    this.
  - Fields NOT directly observed (issue open/closed state, exact labels,
    author's maintainer status where no boilerplate was visible) are set to
    None and must be filled by `corpus-enrich` before any claim depends on
    them. Do NOT hand-assert them here.
  - Enrichment against the live GitHub API (corpus-enrich, run 2026-07-03 with
    an authenticated token) returned ZERO title/date mismatches across all 14
    GitHub rows; authoritative state/labels/closed_at live in
    results/incidents_enriched.jsonl (that file, not this one, is the source
    for open/closed claims).
  - `axis` uses the paper's taxonomy; `evidence_strength` marks how directly
    the report demonstrates a *stop-primitive* failure:
      "direct"   -- report shows a node/effect re-executing, or a
                    parallel-pending effect mishandled (A1/A2 core).
      "adjacent" -- same root cause (no per-interrupt barrier / no
                    cancellation fence) but the report itself does not
                    exhibit a leaked side effect.
      "context"  -- user question / practitioner article establishing the
                    problem is real and sought-after, not a bug report.
  - NEVER inflate: adjacent/context rows are counted separately from direct
    rows in the rendered table. A reviewer must be able to see the direct
    count alone.

AXIS taxonomy (matches probes/results/MATRIX.md):
  A1 = sibling leak (parallel effect while an approval gate is pending)
  A2 = replay (resume/re-invoke re-executes a pre-gate node/effect)
  A3 = cancellation orphan (cancel does not stop the in-flight effect)
  A4 = timeout zombie (timeout fires; effect proceeds anyway)
"""
from __future__ import annotations

# Verbatim queries run on 2026-07-02 (search engine: in-tool web search).
# Re-running these should resurface the same issues (plus drift).
QUERIES: list[dict] = [
    {"tag": "Q1-seed-6208", "query": "langchain-ai/langgraph issues 6208 interrupt"},
    {"tag": "Q2-seed-6158", "query": "langchain-ai/langgraph issue 6158 stall node re-execution interrupt resumed"},
    {"tag": "Q3-seed-3875", "query": "langchain-ai/langgraph issue 3875 interrupt human in the loop"},
    {"tag": "Q4-cancel", "query": "langgraph OR crewai agent cancellation abort tool still executes background task not stopped"},
]

# Seed incident IDs (langchain-ai/langgraph unless noted).
SEED_IDS = [6208, 6158, 5952, 3875, 6626, 6792, 4796]

# Leads that did not re-confirm on verification (search date 2026-07-02).
# Recorded for transparency so they are neither silently dropped nor asserted
# as evidence; excluded from every count in the paper.
UNVERIFIED_LEADS = [
    {"ref": "forum thread 2964", "note": "not located on 2026-07-02; the located "
                                         "multi-interrupt thread is 1657 (see INCIDENTS)."},
    {"ref": "blog.raed.dev/posts/langgraph-hitl/", "note": "a Mar-2026 practitioner "
                                                           "analysis of double-execution; not re-fetched, so unverified."},
]

R_PY = "langchain-ai/langgraph"
R_JS = "langchain-ai/langgraphjs"
R_CREW = "crewAIInc/crewAI"

# Verified incident records. url/title/date observed 2026-07-02.
INCIDENTS: list[dict] = [
    # ---------------- DIRECT: replay (A2) ----------------
    {
        "id": 6208, "repo": R_PY, "kind": "issue",
        "url": "https://github.com/langchain-ai/langgraph/issues/6208",
        "title": "Do not re-execute a node that interrupted unless all of its interrupts have been resumed",
        "created": "2025-09-26", "state": None, "author_type": "maintainer",  # boilerplate: "I am a LangGraph maintainer"
        "axis": "A2", "evidence_strength": "direct", "provenance": "seed",
        "symptom": "A node with two interrupts re-runs after only one resume; fixing it needs per-interrupt id tracking not in stored metadata.",
        "verified_via": "web_search:2026-07-02",
    },
    {
        "id": 6792, "repo": R_PY, "kind": "issue",
        "url": "https://github.com/langchain-ai/langgraph/issues/6792",
        "title": "Resuming after interrupt doesn't reuse prior task outputs when interrupt is in subgraph",
        "created": "2026-02-12", "state": None, "author_type": None,
        "axis": "A2", "evidence_strength": "direct", "provenance": "seed",
        "symptom": "Resuming a subgraph interrupt re-runs an already-completed step and duplicates the returned interrupts.",
        "verified_via": "web_search:2026-07-02",
    },
    {
        "id": 4796, "repo": R_PY, "kind": "issue",
        "url": "https://github.com/langchain-ai/langgraph/issues/4796",
        "title": "Subgraph (using interrupt) restarts instead of resuming from internal breakpoint",
        "created": "2025-05-22", "state": None, "author_type": None,
        "axis": "A2", "evidence_strength": "direct", "provenance": "seed",
        "symptom": "On resume, the subgraph restarts from its entry node (re-executing the parent's calling node) despite a checkpoint pointing at the human node.",
        "verified_via": "web_search:2026-07-02",
    },
    {
        "id": 7780, "repo": R_PY, "kind": "issue",
        "url": "https://github.com/langchain-ai/langgraph/issues/7780",
        "title": "[BUG] Interrupt() in a loop will cause extra resumes",
        "created": "2026-05-13", "state": None, "author_type": None,
        "axis": "A2", "evidence_strength": "direct", "provenance": "search:Q1",
        "symptom": "An interrupt() inside a loop consumes extra resume values, re-running loop body iterations.",
        "verified_via": "web_search:2026-07-02",
    },
    {
        "id": 6444, "repo": R_PY, "kind": "issue",
        "url": "https://github.com/langchain-ai/langgraph/issues/6444",
        "title": "Resume to a specific subgraph node after interrupt",
        "created": "2025-03-27", "state": None, "author_type": None,
        "axis": "A2", "evidence_strength": "direct", "provenance": "search:Q2",
        "symptom": "On the 2nd interrupt, re-invoke resumes before the interrupt node rather than progressing, causing an infinite loop.",
        "verified_via": "web_search:2026-07-02",
    },
    {
        "id": 1308, "repo": R_JS, "kind": "issue",
        "url": "https://github.com/langchain-ai/langgraphjs/issues/1308",
        "title": "Human-in-the-loop Resume Not Working in LangGraph JS with Checkpoint",
        "created": "2025-04-30", "state": None, "author_type": None,
        "axis": "A2", "evidence_strength": "direct", "provenance": "search:Q3",
        "symptom": "In the JS runtime, resuming after an interrupt restarts the graph from the beginning instead of the interrupt point (cross-runtime replication of the replay failure).",
        "verified_via": "web_search:2026-07-02",
    },
    # ---------------- DIRECT: sibling / parallel (A1) ----------------
    {
        "id": 3875, "repo": R_PY, "kind": "issue",
        "url": "https://github.com/langchain-ai/langgraph/issues/3875",
        "title": "Bug: Error when having multiple nodes, each with a single `interrupt`",
        "created": "2025-03-17", "state": None, "author_type": None,
        "axis": "A1", "evidence_strength": "direct", "provenance": "seed",
        "symptom": "Two parallel branches from START, each a node that interrupts then performs an effect (add_one); the multi-pending-interrupt case errors/misbehaves.",
        "verified_via": "web_search:2026-07-02",
    },
    {
        "id": 5952, "repo": R_PY, "kind": "issue",
        "url": "https://github.com/langchain-ai/langgraph/issues/5952",
        "title": "Resolved interrupts from nodes executed in parallel keep firing unnecessarily",
        "created": "2025-08-19", "state": None, "author_type": None,
        "axis": "A1", "evidence_strength": "direct", "provenance": "seed",
        "symptom": "With parallel nodes where one interrupts, already-resolved interrupts keep re-firing on subsequent steps.",
        "verified_via": "web_search:2026-07-02",
    },
    {
        "id": 6626, "repo": R_PY, "kind": "issue",
        "url": "https://github.com/langchain-ai/langgraph/issues/6626",
        "title": "`interrupt()` calls in parallel tools generate identical IDs, making multi-interrupt resume impossible",
        "created": "2025-12-25", "state": None, "author_type": None,
        "axis": "A1", "evidence_strength": "direct", "provenance": "seed",
        "symptom": "Parallel tool calls that each interrupt() are assigned identical interrupt ids, so resumes cannot be routed to the right pending call.",
        "verified_via": "web_search:2026-07-02",
    },
    {
        "id": 6624, "repo": R_PY, "kind": "issue",
        "url": "https://github.com/langchain-ai/langgraph/issues/6624",
        "title": "ToolNode doesn't collect all interrupts from parallel tool execution",
        "created": "2025-12-24", "state": None, "author_type": None,
        "axis": "A1", "evidence_strength": "direct", "provenance": "search:Q1",
        "symptom": "When multiple tools run in parallel under a ToolNode and each interrupts, not all interrupts are collected/surfaced.",
        "verified_via": "web_search:2026-07-02",
    },
    {
        "id": 6533, "repo": R_PY, "kind": "issue",
        "url": "https://github.com/langchain-ai/langgraph/issues/6533",
        "title": "Interrupt resume values misrouted between tools when using a ToolNode",
        "created": "2025-12-03", "state": None, "author_type": None,
        "axis": "A1", "evidence_strength": "direct", "provenance": "search:Q1",
        "symptom": "Parallel tools each expecting their own interrupt value receive each other's resume values (misrouting under parallel pending interrupts).",
        "verified_via": "web_search:2026-07-02",
    },
    # ---------------- ADJACENT: shared root cause ----------------
    {
        "id": 6158, "repo": R_PY, "kind": "pr",
        "url": "https://github.com/langchain-ai/langgraph/pull/6158",
        "title": None,  # enrichment 2026-07-03 confirms: PULL REQUEST (COLLABORATOR), merged/closed 2025-10-06
        "created": None, "state": "closed", "author_type": "maintainer",
        "axis": "A2", "evidence_strength": "adjacent", "provenance": "seed",
        "symptom": "The merged PARTIAL fix: stalls node re-execution until its (single) interrupt is resumed. The multi-interrupt case is explicitly left open by the maintainer-filed #6208 (still open, labeled enhancement).",
        "verified_via": "corpus-enrich:2026-07-03 (is_pull_request=true, closed_at=2025-10-06, author_association=COLLABORATOR)",
    },
    {
        "id": 7686, "repo": R_PY, "kind": "issue",
        "url": "https://github.com/langchain-ai/langgraph/issues/7686",
        "title": "docs(langgraph): broken docs URL in RuntimeError raised on resume with multiple pending interrupts",
        "created": "2026-05-02", "state": None, "author_type": None,
        "axis": "A1", "evidence_strength": "adjacent", "provenance": "search:Q2",
        "symptom": "Confirms the runtime raises 'must specify the interrupt id when resuming' for multiple pending interrupts (repro uses two parallel interrupting nodes); the report itself is about the broken docs link in that error.",
        "verified_via": "web_search:2026-07-02",
    },
    # ---------------- CANCELLATION (A3) -- distinct texture ----------------
    {
        "id": 5672, "repo": R_PY, "kind": "issue",
        "url": "https://github.com/langchain-ai/langgraph/issues/5672",
        "title": "Run Cancellation Causes Loss of Streamed State Not Yet Persisted as a Checkpoint",
        "created": "2025-07-25", "state": None, "author_type": None,
        "axis": "A3", "evidence_strength": "adjacent", "provenance": "search:Q4",
        "symptom": "On cancel/abort, in-progress streamed state since the last checkpoint is not persisted; durability-on-cancel gap (adjacent to zombie-effect: cancellation semantics are underspecified).",
        "verified_via": "web_search:2026-07-02",
    },
    {
        "id": 1601, "repo": R_PY, "kind": "discussion",
        "url": "https://github.com/langchain-ai/langgraph/discussions/1601",
        "title": "Cancelled error with langgraph runs",
        "created": None, "state": None, "author_type": None,
        "axis": "A3", "evidence_strength": "context", "provenance": "search:Q4",
        "symptom": "Multiple users hit CancelledError on background/long runs; cancellation propagation to in-flight async work is fragile. Discussion, not a bug report.",
        "verified_via": "web_search:2026-07-02",
    },
    {
        "id": 590, "repo": "forum.langchain.com", "kind": "forum",
        "url": "https://forum.langchain.com/t/how-to-cleanly-stop-the-workflow-of-the-react-agent-from-the-tool/590",
        "title": "How to cleanly stop the workflow of the react agent from the tool?",
        "created": "2025-07-22", "state": None, "author_type": "user",
        "axis": "A3", "evidence_strength": "context", "provenance": "search:Q4",
        "symptom": "User returning 'cancel' from a tool to stop the flow found it sometimes stops, other times restarts the agent unexpectedly (cancellation is not a reliable stop).",
        "verified_via": "web_search:2026-07-02",
    },
    {
        "id": 3265, "repo": "forum.langchain.com", "kind": "forum",
        "url": "https://forum.langchain.com/t/how-to-propagate-cancellation-across-multi-level-langgraph-agents/3265",
        "title": "How to propagate cancellation across multi-level LangGraph agents",
        "created": "2026-03-28", "state": None, "author_type": "user",
        "axis": "A3", "evidence_strength": "context", "provenance": "search:Q4",
        "symptom": "In a supervisor -> sub-agent -> sub-sub-agent setup over HTTP, a user cancel does not propagate down to stop execution at the deepest active agent.",
        "verified_via": "web_search:2026-07-02",
    },
    {
        "id": 2538, "repo": "forum.langchain.com", "kind": "forum",
        "url": "https://forum.langchain.com/t/stopping-endpoint-for-deep-agents/2538",
        "title": "Stopping endpoint for deep agents",
        "created": "2025-12-17", "state": None, "author_type": "user",
        "axis": "A3", "evidence_strength": "context", "provenance": "search:Q4",
        "symptom": "User needs a stop button for a running deep-agent and finds no obvious mechanism to stop execution.",
        "verified_via": "web_search:2026-07-02",
    },
    # ---------------- CONTEXT: practitioner articulation of the thesis ----------------
    {
        "id": None, "repo": "abstractalgorithms.dev", "kind": "article",
        "url": "https://www.abstractalgorithms.dev/langgraph-human-in-the-loop",
        "title": "Human-in-the-Loop Workflows with LangGraph: Interrupts, Approvals, and Async Execution",
        "created": "2026-04-23", "state": None, "author_type": "practitioner",
        "axis": "A1", "evidence_strength": "context", "provenance": "search:Q4",
        "symptom": "Independently states the paper's thesis: agents with real tools (billing, email, DB writes) take irreversible actions; advises interrupt-on-irreversible-only and TTL expiry for abandoned interrupted threads (unbounded latency / no barrier).",
        "verified_via": "web_search:2026-07-02",
    },
    {
        "id": 1657, "repo": "forum.langchain.com", "kind": "forum",
        "url": "https://forum.langchain.com/t/auto-resuming-challenges-in-langgraph/1657",
        "title": "Auto resuming challenges in langgraph",
        "created": "2025-09-26", "state": None, "author_type": "user",
        "axis": "A2", "evidence_strength": "context", "provenance": "search:Q1",
        "symptom": "User struggles to auto-resume when multiple distinct interrupts exist in one graph (the multi-interrupt resume-routing problem, from the user side). This is the real thread; supersedes the unverified 'thread 2964' note.",
        "verified_via": "web_search:2026-07-02",
    },
]