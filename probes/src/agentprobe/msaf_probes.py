"""msaf_probes.py -- keyless control-plane probes for Microsoft Agent Framework
(agent-framework-core) workflows. No API keys, no LLMs: executors are plain
Python functions/classes, because the questions are about the FRAMEWORK's
enforcement semantics, not about any model.

Framework HITL model (measured, v1.10.0): an executor calls
``ctx.request_info(request, response_type)``; the request handler COMPLETES
(fire-and-forget), the workflow drains remaining work, and the run ends in
state ``IDLE_WITH_PENDING_REQUESTS``. The caller answers with
``workflow.run(responses={request_id: value})``, which dispatches to a
``@response_handler`` on the same executor. There is no mid-function
suspension and (as of this probe) no native run timeout parameter on
``Workflow.run``.

Violation predicates -- fixed BEFORE first execution:

  M1  SIBLING LEAK: fan-out from start to {approval-gate executor, effect
      executor}. Violation: the run reaches IDLE_WITH_PENDING_REQUESTS (i.e.
      is paused awaiting the human) AND the sibling effect executed before any
      response was provided.
  M1r REJECT-AFTER-EFFECT: continuing M1, the human responds "no".
      Violation: the effect had already executed (count >= 1 at rejection
      time), so the rejection could not prevent it.
  M2  POST-REQUEST REPLAY (in-process response): an executor logs an effect
      BEFORE calling request_info; the human approves via
      run(responses=...). Violation: effect count > 1 after approval.
  M2c POST-REQUEST REPLAY (checkpoint restore): same workflow built with
      checkpoint storage; after the run idles with a pending request, a FRESH
      workflow instance restores from the latest checkpoint and delivers the
      approval. Violation: effect count > 1 across the two instances. This is
      the fair analogue of LangGraph's resume, which is also checkpoint
      restoration.
  M3a CANCELLATION ORPHAN (sync-in-thread): asyncio task running the workflow
      is cancelled while an executor runs a blocking effect via
      asyncio.to_thread. Violation: caller observes CancelledError, effect had
      not landed at that moment, and the effect lands afterward.
  M3b CANCELLATION (pure async): contrast case; records whether cancellation
      propagates and prevents the effect.
  M4  TIMEOUT ZOMBIE (host-level): asyncio.wait_for imposes a wall-clock
      deadline over Workflow.run while a blocking effect is in flight.
      Violation: caller sees TimeoutError, effect had not landed at that
      moment, and the effect lands afterward.

BRUTAL-REVIEWER NOTES (scope limits this probe does NOT escape):
  * MSAF's request/response is documented as an asynchronous external-info
    pattern, not a barrier; M1's "violation" is against the operator's
    barrier ASSUMPTION, exactly as in the LlamaIndex L1 probe. The paper's
    expectation-audit table must quote MSAF's own framing (VERIFY wording
    against current docs at write-up time) rather than imply MSAF promises
    suspension of siblings.
  * M4 uses asyncio.wait_for because Workflow.run exposes no timeout
    parameter in 1.10.0. Absence of a native deadline is itself a matrix
    datum; do NOT report M4 as the framework's native timeout being unsound.
  * Effects are appends to an in-process event log (same construct as all
    other probes in this suite); the Phase-0 out-of-process sink upgrade
    applies here identically.
"""

# NOTE: no `from __future__ import annotations` here -- agent-framework 1.10.0
# validates handler signatures against the WorkflowContext class object and
# does not resolve PEP 563 string annotations (verified against
# _workflows/_workflow_context.py: `annotation is WorkflowContext`).

import asyncio
import time
import warnings
from dataclasses import dataclass
from importlib.metadata import version

warnings.filterwarnings("ignore")

import agent_framework as af  # noqa: E402
from agent_framework import WorkflowContext  # noqa: E402  (bare name required by annotation validator)

from agentprobe._harness import EventLog, ProbeResult, summarize  # noqa: E402

LOG = EventLog()


@dataclass
class ApprovalRequest:
    """Payload for the human-approval request."""

    question: str = "approve the plan?"


class GateExecutor(af.Executor):
    """Approval gate: requests human info, records the decision when it arrives."""

    @af.handler
    async def start(self, msg: str, ctx: WorkflowContext) -> None:
        LOG.log("gate:before_request")
        await ctx.request_info(ApprovalRequest(), str)
        # NOTE: handler completes here; there is no suspension point.

    @af.response_handler
    async def on_decision(
        self, original: ApprovalRequest, decision: str, ctx: WorkflowContext
    ) -> None:
        LOG.log(f"gate:resumed_with={decision}")


class ActThenGateExecutor(af.Executor):
    """M2: performs the effect FIRST, then requests approval."""

    @af.handler
    async def start(self, msg: str, ctx: WorkflowContext) -> None:
        LOG.log("M2_EFFECT:executed")
        await ctx.request_info(ApprovalRequest(), str)

    @af.response_handler
    async def on_decision(
        self, original: ApprovalRequest, decision: str, ctx: WorkflowContext
    ) -> None:
        LOG.log(f"M2_gate:resumed_with={decision}")


def _fan_and_effect():
    @af.executor(id="fan")
    async def fan(msg: str, ctx: WorkflowContext[str]) -> None:
        await ctx.send_message(msg)

    @af.executor(id="side_effect")
    async def side_effect(msg: str, ctx: WorkflowContext) -> None:
        LOG.log("EFFECT:executed")  # stands in for an email send / ticket create

    return fan, side_effect


# ---------------------------------------------------------------- M1 sibling
async def run_m1() -> tuple[ProbeResult, ProbeResult]:
    LOG.clear()
    fan, side_effect = _fan_and_effect()
    gate = GateExecutor(id="gate")
    wf = (
        af.WorkflowBuilder(start_executor=fan)
        .add_fan_out_edges(fan, [gate, side_effect])
        .build()
    )
    result = await wf.run("go")
    paused = result.get_final_state() == af.WorkflowRunState.IDLE_WITH_PENDING_REQUESTS
    effect_while_paused = LOG.contains("EFFECT:executed")
    trace_at_pause = list(LOG.events)
    requests = result.get_request_info_events()
    # Human REJECTS:
    if requests:
        await wf.run(responses={requests[0].request_id: "no"})
    effect_total = LOG.count("EFFECT:executed")
    m1 = ProbeResult(
        "sibling_leak[fan_out]",
        violation=paused and effect_while_paused,
        detail={
            "paused": paused,
            "effect_while_paused": effect_while_paused,
            "trace_at_pause": trace_at_pause,
        },
    )
    m1r = ProbeResult(
        "reject_after_effect",
        violation=paused and effect_total >= 1,
        detail={"effect_total_after_reject": effect_total},
    )
    return m1, m1r


# ---------------------------------------------------------------- M2 replay
async def run_m2_inprocess() -> ProbeResult:
    LOG.clear()
    actor = ActThenGateExecutor(id="act_then_gate")
    wf = af.WorkflowBuilder(start_executor=actor).build()
    result = await wf.run("go")
    count_at_pause = LOG.count("M2_EFFECT:executed")
    requests = result.get_request_info_events()
    if requests:
        await wf.run(responses={requests[0].request_id: "yes"})  # human APPROVES
    count_after = LOG.count("M2_EFFECT:executed")
    return ProbeResult(
        "replay[in_process_response]",
        violation=count_after > 1,
        detail={
            "effect_count_at_pause": count_at_pause,
            "effect_count_after_approve": count_after,
        },
    )


async def run_m2_checkpoint_restore() -> ProbeResult:
    LOG.clear()
    storage = af.InMemoryCheckpointStorage()

    def build():
        actor = ActThenGateExecutor(id="act_then_gate")
        return af.WorkflowBuilder(
            name="m2c_replay_probe", start_executor=actor, checkpoint_storage=storage
        ).build()

    wf1 = build()
    result = await wf1.run("go")
    count_at_pause = LOG.count("M2_EFFECT:executed")
    requests = result.get_request_info_events()
    if not requests:
        return ProbeResult(
            "replay[checkpoint_restore]",
            violation=False,
            detail={"error": "no pending request; probe inconclusive"},
        )
    request_id = requests[0].request_id
    checkpoints = await storage.list_checkpoints(workflow_name="m2c_replay_probe")
    if not checkpoints:
        return ProbeResult(
            "replay[checkpoint_restore]",
            violation=False,
            detail={"note": "no checkpoints persisted; restore path not probeable"},
        )
    latest = checkpoints[-1]
    # Fresh instance simulates process restart, the fair analogue of
    # LangGraph's checkpoint-based resume.
    wf2 = build()
    await wf2.run(checkpoint_id=latest.checkpoint_id, responses={request_id: "yes"})
    count_after = LOG.count("M2_EFFECT:executed")
    return ProbeResult(
        "replay[checkpoint_restore]",
        violation=count_after > 1,
        detail={
            "effect_count_at_pause": count_at_pause,
            "effect_count_after_restore_approve": count_after,
            "checkpoints_persisted": len(checkpoints),
        },
    )


# ------------------------------------------------------------ M3 cancellation
async def run_m3(sync_in_thread: bool, label: str) -> ProbeResult:
    LOG.clear()

    def blocking_tool() -> None:
        time.sleep(0.6)  # e.g. an HTTP POST in flight
        LOG.log(f"{label}_EFFECT:executed_after_delay")

    @af.executor(id="worker")
    async def worker_sync(msg: str, ctx: WorkflowContext) -> None:
        LOG.log(f"{label}:node_started")
        await asyncio.to_thread(blocking_tool)

    @af.executor(id="worker")
    async def worker_async(msg: str, ctx: WorkflowContext) -> None:
        LOG.log(f"{label}:node_started")
        await asyncio.sleep(0.6)
        LOG.log(f"{label}_EFFECT:executed_after_delay")

    wf = af.WorkflowBuilder(
        start_executor=worker_sync if sync_in_thread else worker_async
    ).build()

    task = asyncio.create_task(wf.run("go"))
    await asyncio.sleep(0.15)  # user cancels mid-tool
    task.cancel()
    cancelled_seen = False
    try:
        await task
    except asyncio.CancelledError:
        cancelled_seen = True
    except Exception as e:  # framework may wrap cancellation
        LOG.log(f"{label}:caller_saw={type(e).__name__}")
    effect_at_cancel = LOG.contains("EFFECT")
    await asyncio.sleep(0.8)  # give any zombie work time to land
    effect_after = LOG.contains("EFFECT")
    return ProbeResult(
        f"cancellation[{label}]",
        violation=cancelled_seen and (not effect_at_cancel) and effect_after,
        detail={
            "cancelled_seen": cancelled_seen,
            "effect_at_cancel": effect_at_cancel,
            "effect_after_cancel": effect_after,
        },
    )


# ---------------------------------------------------------------- M4 timeout
async def run_m4() -> ProbeResult:
    LOG.clear()

    def blocking() -> None:
        time.sleep(0.8)
        LOG.log("M4_EFFECT:executed_after_delay")

    @af.executor(id="worker")
    async def worker(msg: str, ctx: WorkflowContext) -> None:
        LOG.log("M4:node_started")
        await asyncio.to_thread(blocking)

    wf = af.WorkflowBuilder(start_executor=worker).build()
    timed_out = False
    try:
        await asyncio.wait_for(wf.run("go"), timeout=0.2)
    except asyncio.TimeoutError:
        timed_out = True
        LOG.log("caller:TimeoutError")
    effect_at_timeout = LOG.contains("M4_EFFECT")
    await asyncio.sleep(1.0)
    effect_after = LOG.contains("M4_EFFECT")
    return ProbeResult(
        "timeout_zombie[host_wait_for]",
        violation=timed_out and (not effect_at_timeout) and effect_after,
        detail={
            "caller_saw_timeout": timed_out,
            "effect_at_timeout": effect_at_timeout,
            "effect_after_timeout": effect_after,
            "note": "no native run timeout parameter exists on Workflow.run in 1.10.0",
        },
    )


async def _amain() -> None:
    print(f"# FW-C agent-framework-core=={version('agent-framework-core')}\n")
    m1, m1r = await run_m1()
    m2 = await run_m2_inprocess()
    m2c = await run_m2_checkpoint_restore()
    m3a = await run_m3(sync_in_thread=True, label="sync_thread")
    m3b = await run_m3(sync_in_thread=False, label="pure_async")
    m4 = await run_m4()
    print(summarize([m1, m1r, m2, m2c, m3a, m3b, m4]))


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
