# Phase 1 — Cross-Framework Control-Plane Violation Matrix

Generated: 2026-07-02. All probes keyless (scripted model stubs or direct
workflow invocation; zero API calls). Every verdict below reproduced
identically across 5/5 repetitions in this environment (30/30 for FW-A
core probes in the earlier pass). Raw per-rep logs: `results/reps/`.
Canonical single-run logs: `results/<framework>.txt`.
FW-B row completed 2026-07-04 with the finished 4-probe suite (worker-thread
cancellation + context-restore replay added to the original leak/timeout
pair); verdicts reproduced 5/5 identically in a second environment
(single-vCPU container). Rerun `uv run agentprobe-llamaindex` locally (5x)
and commit `results/llamaindex.txt` alongside this file.
FW-F additionally replicated verdict-identically on a second machine under
Node v23.6.0 (user hardware, 5/5 reps), giving the JS column two Node major
versions and two machines.

## Frameworks under test

| ID   | Framework                | Version (pinned)          | Runtime      |
|------|--------------------------|---------------------------|--------------|
| FW-A | LangGraph (Python)       | langgraph==1.2.7          | CPython 3.12 |
| FW-B | LlamaIndex Workflows     | llama-index-core==0.14.23 | CPython 3.12 |
| FW-C | MS Agent Framework       | agent-framework-core==1.10.0 | CPython 3.12 |
| FW-D | OpenAI Agents SDK        | openai-agents==0.17.7     | CPython 3.12 |
| FW-E | CrewAI (OSS)             | crewai==1.15.1            | CPython 3.12 (isolated venv) |
| FW-F | LangGraph.js             | @langchain/langgraph@1.4.7 | Node v22.22.2 + v23.6.0 |

## Matrix

Legend: **V** = violation (predicate met), **c** = clean under the fixed
predicate, **R** = refused at construction (framework will not build the
configuration), **n/a** = axis does not exist by construction,
**NP** = not probed (honest gap, no claim made).

| Axis                                   | FW-A | FW-B | FW-C | FW-D | FW-E | FW-F |
|----------------------------------------|------|------|------|------|------|------|
| A1 Sibling leak while gate pending     | V    | V    | V    | V    | n/a¹ | V    |
| A1r Reject lands after effect          | V    | V²   | V    | V    | V¹   | V    |
| A2 Resume replays pre-gate effect      | V (1→2) | c (1→1)¹⁰ | c (1→1) | c (1→1) | NP³ | V (1→2) |
| A2c Replay across checkpoint restore   | NP   | NP   | c (1→1) | n/a⁴ | NP³ | NP   |
| A3 Cancel: sync work in thread         | V    | V¹⁰  | V    | V    | V⁵   | n/a⁶ |
| A3 Cancel: pure async                  | c    | NP   | c    | c    | NP   | V⁶   |
| A4 Native/host timeout zombie          | V⁷   | c    | V⁷   | c (async) / R (sync)⁸ | c (strict)⁹ | V (native) |
| A4b Timeout blocks, effect lands anyway| —    | —    | —    | —    | **V**⁹ | —    |

¹ FW-E has no pre-execution approval primitive in OSS 1.15.1
(`human_input=True` is post-hoc feedback, introspected from source; VERIFY
docs wording before quoting). The A1 axis cannot exist; the A1r row is the
by-design variant: the effect executes, then review is requested
(`review_after_effect[human_input]`).
² FW-B's single event-bus probe (`parallel_approval_leak`) witnesses both the
leak and the reject-after-effect in one trace.
³ `Crew.from_checkpoint` exists in 1.15 but mid-task replay semantics are
unverified. No claim.
⁴ FW-D resume consumes a serialized `RunState`; turn results are cached in
state, so "fresh process restore" and "in-process resume" traverse the same
cached path (`model_invocations=2`, effect count 1→1).
⁵ FW-E cancellation probed via `kickoff_async` + task cancel: orphaned effect
lands after cancellation acknowledged.
⁶ No sync/async split exists in JS. The single cancellation surface is the
documented `config.signal` (AbortController). Caller observes `AbortError`;
the node's promise chain is NOT interrupted; effect lands afterward. This is
the native surface, not a host-level wrapper.
⁷ No native run-timeout parameter exists (FW-A `invoke`, FW-C `Workflow.run`
in the pinned versions); probed via host-level `asyncio.wait_for` and
labeled as such.
⁸ FW-D native per-tool timeout: pure-async tool is cleanly cancelled;
attaching a native timeout to a sync tool is refused at construction
(`ValueError`). Sound-by-refusal design datum.
⁹ FW-E `max_execution_time`: strict zombie predicate is clean, but forensics
show the caller BLOCKS ~2.24 s past a 1.0 s deadline (executor `__exit__`
does `shutdown(wait=True)`), the `TimeoutError` surfaces only after the
timed-out work completes, and the effect executes anyway. Pre-registered as
distinct predicate A4b (`timeout_blocks_then_effect`): timeout observed +
effect executed + surfacing latency ≥ 1.5× deadline.
¹⁰ FW-B, measured by the completed suite (2026-07-04): native `cancel_run`
raises `WorkflowCancelledByUser` inside the workflow but does not cover a
worker thread — the thread's effect lands after cancellation is
acknowledged (V). Resume via the documented
`Context.from_dict(ctx.to_dict())` round-trip does not re-execute the
completed step (1→1, clean) — a design contrast with FW-A/FW-F.

## Headline findings

1. **Sibling leak generalizes across five execution models**: Pregel
   superstep fan-out (FW-A), event bus (FW-B), message-passing fan-out
   (FW-C), parallel tool calls in a single model turn (FW-D), and the JS
   Pregel port (FW-F). It is not a LangGraph quirk; it is what happens when
   "pause" means "pause one branch" and no barrier exists.
2. **Replay is a design property, not an implementation accident**: the
   resume-replays-pre-gate-effect violation reproduces in both language
   runtimes of the same framework (FW-A Python 1→2, FW-F JS 1→2), while three
   independently designed frameworks are clean — FW-C and FW-D cache
   completed work in the resume token / checkpoint, and FW-B restores step
   progress through its serialized context (footnote 10). LangGraph's own
   docs state the re-execution behavior; our contribution on this axis is
   characterization + the sibling interaction, not discovery.
3. **Cancellation soundness is host-language-dependent**: identical
   pure-async node code is cleanly cancellable under Python asyncio (FW-A/C/D
   contrast rows) and NOT cancellable under Node (FW-F violates on its native
   AbortSignal surface), because JS promises cannot be interrupted. Sync work
   in threads is unsound everywhere it is constructible (FW-A/C/D/E), and
   FW-D is the only framework that refuses to build the unsound
   configuration (native timeout on sync tool → ValueError).
4. **A new violation class from FW-E**: `timeout_blocks_then_effect` — the
   framework's own timeout mechanism reports the timeout only AFTER the
   timed-out work has completed and its effect landed, while blocking the
   caller past the deadline. Distinct from the async zombie (FW-A/C) where
   the caller returns promptly and the effect lands in the background.

## Known limits of this pass (do not oversell)

- Effects are in-process log appends. The Phase-0 out-of-process effect sink
  upgrade applies to all probes here; verdicts are not expected to change
  (the traces are unambiguous) but the artifact must not rely on in-process
  state for its headline numbers.
- FW-D/FW-E plan shapes are emitted by scripted model stubs. Whether real
  models emit gated+ungated parallel tool calls at material rates is exactly
  what Phase 3 E-EXPOSURE measures. No prevalence claim is made from these
  probes.
- Host-level timeout rows (⁷) measure the pattern integrators are forced
  into by the absence of a native parameter; they are labeled host-level and
  never presented as native-mechanism defects.
- FW-E replay row is NP. FW-B's remaining NP cells are pure-async
  cancellation and checkpoint-restore replay (A2c); its context-restore
  replay and worker-thread cancellation are now measured (footnote 10).