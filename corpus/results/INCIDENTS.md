# Incident corpus -- agent-framework stop-primitive failures

Prevalence evidence for the paper. Every row was confirmed by reading the actual issue/thread on 2026-07-02 (see `verified_via`). Rows are grouped by evidence strength so the DIRECT count -- reports that actually exhibit a node/effect re-executing or a parallel-pending effect mishandled -- stands on its own.

Generated from `src/corpus/seeds.py` by `corpus-render`. Run `corpus-enrich` to fill authoritative state/labels/dates from the GitHub API (fields left blank below were not directly observed and must be enriched before any claim depends on them).

## Counts

- DIRECT incidents (exhibit a stop-primitive failure): **11**
- ADJACENT (same root cause, no leaked effect shown): **3**
- CONTEXT (user questions / practitioner articles): **6**
- Distinct sources: abstractalgorithms.dev (1), forum.langchain.com (4), langchain-ai/langgraph (14), langchain-ai/langgraphjs (1)
- DIRECT rows by axis: A1 (5), A2 (6)
- Date span (observed): 2025-03-17 to 2026-05-13

> Honest scope: this corpus is LangGraph-dominated because LangGraph has the most-used explicit HITL/interrupt surface and the largest public tracker, so its failures are the most-reported. It is a lower bound on occurrence (an issue means at least one user hit it and filed), not a rate. The keyless probes (probes/results/MATRIX.md) supply the cross-framework universality that the issue corpus alone cannot; the two are complementary. Cancellation/timeout (A3/A4) surfaces mostly as user 'how do I even stop this' threads and cancel-loses-state bugs rather than crisp effect-leak repros -- reported as-is.

## Direct incidents

Each report shows a node/effect re-executing on resume (A2) or a parallel-pending approval/effect mishandled (A1).

| ref | axis | date | source | one-line symptom |
|---|---|---|---|---|
| [langgraph#3875](https://github.com/langchain-ai/langgraph/issues/3875) | A1 | 2025-03-17 | gh issue | Two parallel branches from START, each a node that interrupts then performs an effect (add_one); the multi-pending-interrupt case errors/misbehaves. |
| [langgraph#5952](https://github.com/langchain-ai/langgraph/issues/5952) | A1 | 2025-08-19 | gh issue | With parallel nodes where one interrupts, already-resolved interrupts keep re-firing on subsequent steps. |
| [langgraph#6533](https://github.com/langchain-ai/langgraph/issues/6533) | A1 | 2025-12-03 | gh issue | Parallel tools each expecting their own interrupt value receive each other's resume values (misrouting under parallel pending interrupts). |
| [langgraph#6624](https://github.com/langchain-ai/langgraph/issues/6624) | A1 | 2025-12-24 | gh issue | When multiple tools run in parallel under a ToolNode and each interrupts, not all interrupts are collected/surfaced. |
| [langgraph#6626](https://github.com/langchain-ai/langgraph/issues/6626) | A1 | 2025-12-25 | gh issue | Parallel tool calls that each interrupt() are assigned identical interrupt ids, so resumes cannot be routed to the right pending call. |
| [langgraph#6444](https://github.com/langchain-ai/langgraph/issues/6444) | A2 | 2025-03-27 | gh issue | On the 2nd interrupt, re-invoke resumes before the interrupt node rather than progressing, causing an infinite loop. |
| [langgraphjs#1308](https://github.com/langchain-ai/langgraphjs/issues/1308) | A2 | 2025-04-30 | gh issue | In the JS runtime, resuming after an interrupt restarts the graph from the beginning instead of the interrupt point (cross-runtime replication of the replay failure). |
| [langgraph#4796](https://github.com/langchain-ai/langgraph/issues/4796) | A2 | 2025-05-22 | gh issue | On resume, the subgraph restarts from its entry node (re-executing the parent's calling node) despite a checkpoint pointing at the human node. |
| [langgraph#6208](https://github.com/langchain-ai/langgraph/issues/6208) | A2 | 2025-09-26 | gh issue | A node with two interrupts re-runs after only one resume; fixing it needs per-interrupt id tracking not in stored metadata. |
| [langgraph#6792](https://github.com/langchain-ai/langgraph/issues/6792) | A2 | 2026-02-12 | gh issue | Resuming a subgraph interrupt re-runs an already-completed step and duplicates the returned interrupts. |
| [langgraph#7780](https://github.com/langchain-ai/langgraph/issues/7780) | A2 | 2026-05-13 | gh issue | An interrupt() inside a loop consumes extra resume values, re-running loop body iterations. |

## Adjacent incidents

Same underlying cause (no per-interrupt barrier / underspecified cancellation) but the report does not itself demonstrate a leaked side effect.

| ref | axis | date | source | one-line symptom |
|---|---|---|---|---|
| [langgraph#7686](https://github.com/langchain-ai/langgraph/issues/7686) | A1 | 2026-05-02 | gh issue | Confirms the runtime raises 'must specify the interrupt id when resuming' for multiple pending interrupts (repro uses two parallel interrupting nodes); the report itself is about the broken docs link in that error. |
| [langgraph#6158](https://github.com/langchain-ai/langgraph/pull/6158) | A2 | VERIFY | pr | The merged PARTIAL fix: stalls node re-execution until its (single) interrupt is resumed. The multi-interrupt case is explicitly left open by the maintainer-filed #6208 (still open, labeled enhancement). |
| [langgraph#5672](https://github.com/langchain-ai/langgraph/issues/5672) | A3 | 2025-07-25 | gh issue | On cancel/abort, in-progress streamed state since the last checkpoint is not persisted; durability-on-cancel gap (adjacent to zombie-effect: cancellation semantics are underspecified). |

## Context (not bug reports)

User questions and practitioner write-ups establishing the problem is real and actively worked around in the field.

| ref | axis | date | source | one-line symptom |
|---|---|---|---|---|
| [abstractalgorithms.dev](https://www.abstractalgorithms.dev/langgraph-human-in-the-loop) | A1 | 2026-04-23 | article | Independently states the paper's thesis: agents with real tools (billing, email, DB writes) take irreversible actions; advises interrupt-on-irreversible-only and TTL expiry for abandoned interrupted threads (unbounded latency / no barrier). |
| [forum#1657](https://forum.langchain.com/t/auto-resuming-challenges-in-langgraph/1657) | A2 | 2025-09-26 | forum | User struggles to auto-resume when multiple distinct interrupts exist in one graph (the multi-interrupt resume-routing problem, from the user side). This is the real thread; supersedes the unverified 'thread 2964' note. |
| [langgraph#1601](https://github.com/langchain-ai/langgraph/discussions/1601) | A3 | VERIFY | gh disc. | Multiple users hit CancelledError on background/long runs; cancellation propagation to in-flight async work is fragile. Discussion, not a bug report. |
| [forum#590](https://forum.langchain.com/t/how-to-cleanly-stop-the-workflow-of-the-react-agent-from-the-tool/590) | A3 | 2025-07-22 | forum | User returning 'cancel' from a tool to stop the flow found it sometimes stops, other times restarts the agent unexpectedly (cancellation is not a reliable stop). |
| [forum#2538](https://forum.langchain.com/t/stopping-endpoint-for-deep-agents/2538) | A3 | 2025-12-17 | forum | User needs a stop button for a running deep-agent and finds no obvious mechanism to stop execution. |
| [forum#3265](https://forum.langchain.com/t/how-to-propagate-cancellation-across-multi-level-langgraph-agents/3265) | A3 | 2026-03-28 | forum | In a supervisor -> sub-agent -> sub-sub-agent setup over HTTP, a user cancel does not propagate down to stop execution at the deepest active agent. |

## Reproducibility -- verbatim search queries (2026-07-02)

- `Q1-seed-6208`: langchain-ai/langgraph issues 6208 interrupt
- `Q2-seed-6158`: langchain-ai/langgraph issue 6158 stall node re-execution interrupt resumed
- `Q3-seed-3875`: langchain-ai/langgraph issue 3875 interrupt human in the loop
- `Q4-cancel`: langgraph OR crewai agent cancellation abort tool still executes background task not stopped

## Unverified leads (recorded, NOT counted as evidence)

- **forum thread 2964** -- prior notes cited forum thread 2964; not located 2026-07-02. The real multi-interrupt forum thread found is 1657 (see INCIDENTS). VERIFY or drop.
- **blog.raed.dev/posts/langgraph-hitl/** -- cited in review notes as a Mar-2026 practitioner analysis of double-execution; not re-fetched this session. VERIFY before citing.