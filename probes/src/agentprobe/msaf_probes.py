import asyncio
import time
import warnings
from dataclasses import dataclass
from importlib.metadata import version
warnings.filterwarnings("ignore")
import agent_framework as af
from agent_framework import WorkflowContext
from agentprobe._harness import EventLog, ProbeResult, summarize

LOG = EventLog()

@dataclass
class ApprovalRequest:
    question: str = "approve the plan?"

class GateExecutor(af.Executor):
    @af.handler
    async def start(self, msg: str, ctx: WorkflowContext) -> None:
        LOG.log("gate:before_request")
        await ctx.request_info(ApprovalRequest(), str)

    @af.response_handler
    async def on_decision(
        self, original: ApprovalRequest, decision: str, ctx: WorkflowContext
    ) -> None:
        LOG.log(f"gate:resumed_with={decision}")


class ActThenGateExecutor(af.Executor):
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


async def run_m2_inprocess() -> ProbeResult:
    LOG.clear()
    actor = ActThenGateExecutor(id="act_then_gate")
    wf = af.WorkflowBuilder(start_executor=actor).build()
    result = await wf.run("go")
    count_at_pause = LOG.count("M2_EFFECT:executed")
    requests = result.get_request_info_events()

    if requests:
        await wf.run(responses={requests[0].request_id: "yes"})
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

    await asyncio.sleep(0.15)

    task.cancel()
    cancelled_seen = False

    try:
        await task
    except asyncio.CancelledError:
        cancelled_seen = True
    except Exception as e:
        LOG.log(f"{label}:caller_saw={type(e).__name__}")
    effect_at_cancel = LOG.contains("EFFECT")
    await asyncio.sleep(0.8)
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