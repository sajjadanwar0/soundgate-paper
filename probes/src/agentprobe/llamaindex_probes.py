from __future__ import annotations
import asyncio
import time
from importlib.metadata import version
from llama_index.core.workflow import Context as Ctx
from llama_index.core.workflow import (
    Context, Event, StartEvent, StopEvent, Workflow, step,
    InputRequiredEvent, HumanResponseEvent, WorkflowTimeoutError,
)
from ._harness import EventLog, ProbeResult, summarize
import threading

LOG = EventLog()


class GoEffect(Event): ...
class GoGate(Event): ...
class EffectDone(Event): ...
class GateDone(Event): ...

class ParallelApprovalWF(Workflow):
    @step
    async def fan(self, ev: StartEvent, ctx: Context) -> GoGate | GoEffect:
        ctx.send_event(GoEffect())
        return GoGate()

    @step
    async def effect(self, ev: GoEffect, ctx: Context) -> EffectDone:
        LOG.log("L_EFFECT:executed")
        return EffectDone()

    @step
    async def gate(self, ev: GoGate, ctx: Context) -> GateDone:
        LOG.log("gate:before_input")
        ctx.write_event_to_stream(InputRequiredEvent(prefix="approve?"))
        resp = await ctx.wait_for_event(HumanResponseEvent)
        LOG.log(f"gate:resumed={resp.response}")
        return GateDone()

    @step
    async def done(self, ev: EffectDone | GateDone, ctx: Context) -> StopEvent:
        got = ctx.collect_events(ev, [EffectDone, GateDone])
        if got is None:
            return None
        return StopEvent(result="done")


async def probe_parallel_leak() -> ProbeResult:
    LOG.clear()
    wf = ParallelApprovalWF(timeout=5)
    handler = wf.run()
    effect_before_response = False
    async for ev in handler.stream_events():
        if isinstance(ev, InputRequiredEvent):
            effect_before_response = LOG.contains("L_EFFECT:executed")
            handler.ctx.send_event(HumanResponseEvent(response="no"))  # REJECT
    try:
        await handler
    except Exception as e:
        LOG.log(f"handler_err:{type(e).__name__}")

    return ProbeResult(
        name="parallel_approval_leak",
        violation=effect_before_response,
        detail={"effect_before_human_response": effect_before_response,
                "effect_total": LOG.count("L_EFFECT:executed"),
                "trace": list(LOG.events)},
    )


class TimeoutWF(Workflow):
    @step
    async def act(self, ev: StartEvent, ctx: Context) -> StopEvent:
        LOG.log("T:step_started")

        await asyncio.to_thread(self._blocking)
        LOG.log("T_EFFECT:executed_after_delay")

        return StopEvent(result="ok")

    @staticmethod
    def _blocking():
        time.sleep(1.0)


async def probe_timeout_zombie() -> ProbeResult:
    LOG.clear()
    wf = TimeoutWF(timeout=0.3)
    timed_out = False
    try:
        await wf.run()
    except WorkflowTimeoutError:
        timed_out = True
    at = LOG.contains("T_EFFECT:executed_after_delay")

    await asyncio.sleep(1.2)
    after = LOG.contains("T_EFFECT:executed_after_delay")

    return ProbeResult(
        name="timeout_zombie",
        violation=timed_out and (not at) and after,
        detail={"caller_saw_timeout": timed_out, "effect_at_timeout": at,
                "effect_after_timeout": after},
    )

class CancelWF(Workflow):
    @step
    async def spawn(self, ev: StartEvent, ctx: Context) -> StopEvent:
        LOG.log("C:step_started")

        def zombie():
            time.sleep(0.5)
            LOG.log("C_EFFECT:executed_after_cancel")

        threading.Thread(target=zombie, daemon=True).start()
        await asyncio.sleep(2.0)

        return StopEvent(result="ok")


async def probe_cancellation() -> ProbeResult:
    LOG.clear()
    wf = CancelWF(timeout=10)
    handler = wf.run()

    await asyncio.sleep(0.2)
    effect_at_cancel = LOG.contains("C_EFFECT:executed_after_cancel")
    await handler.cancel_run()
    cancelled_ack = True
    await asyncio.sleep(0.8)
    effect_after_cancel = LOG.contains("C_EFFECT:executed_after_cancel")

    return ProbeResult(
        name="cancellation[cancel_run:worker_thread]",
        violation=cancelled_ack and (not effect_at_cancel) and effect_after_cancel,
        detail={"cancel_returned": cancelled_ack,
                "effect_at_cancel": effect_at_cancel,
                "effect_after_cancel": effect_after_cancel,
                "note": "native cancel_run raises WorkflowCancelledByUser in-workflow; "
                        "worker thread is not covered by cooperative cancellation"},
    )

class ReplayEffectStart(Event): ...

class ReplayWF(Workflow):
    @step
    async def effect(self, ev: StartEvent, ctx: Context) -> ReplayEffectStart:
        LOG.log("R_EFFECT:executed")
        return ReplayEffectStart()

    @step
    async def finish(self, ev: ReplayEffectStart, ctx: Context) -> StopEvent:
        await asyncio.sleep(0.05)

        return StopEvent(result="done")

async def probe_replay() -> ProbeResult:
    LOG.clear()

    wf = ReplayWF(timeout=10)
    handler = wf.run()
    snap = None

    for _ in range(200):
        await asyncio.sleep(0.01)
        if LOG.contains("R_EFFECT:executed"):
            try:
                snap = handler.ctx.to_dict()
            except Exception as e:
                snap = None
                LOG.log(f"snap_err:{type(e).__name__}")
            break
    try:
        await handler
    except Exception:
        pass

    count_after_run1 = LOG.count("R_EFFECT:executed")

    if snap is None:
        return ProbeResult(
            name="replay[context_restore]",
            violation=False,
            detail={"outcome": "NOT PROBED: could not snapshot mid-run context",
                    "effect_count_run1": count_after_run1,
                    "note": "VERIFY: to_dict may require an in-flight external context"},
        )

    wf2 = ReplayWF(timeout=10)

    try:
        restored = Ctx.from_dict(wf2, snap)
        await wf2.run(ctx=restored)
    except Exception as e:
        LOG.log(f"resume_err:{type(e).__name__}")
    total = LOG.count("R_EFFECT:executed")
    replayed = total > count_after_run1

    return ProbeResult(
        name="replay[context_restore]",
        violation=replayed,
        detail={"effect_count_run1": count_after_run1,
                "effect_count_after_resume": total,
                "note": "resume via run(ctx=Context.from_dict(to_dict())); "
                        "violation = effect re-executed on restore"},
    )

async def _run_all() -> list[ProbeResult]:
    return [
        await probe_parallel_leak(),
        await probe_timeout_zombie(),
        await probe_cancellation(),
        await probe_replay(),
    ]

def main() -> None:
    print(f"# FW-B llama-index-core=={version('llama-index-core')}\n")
    results = asyncio.run(_run_all())
    print(summarize(results))

if __name__ == "__main__":
    main()