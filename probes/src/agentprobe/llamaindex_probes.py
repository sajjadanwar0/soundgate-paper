"""FW-B (LlamaIndex Workflows) control-plane probes. Model-free, no API keys.

Probes: parallel approval leak, and timeout zombie (native workflow timeout).
Run: `uv run agentprobe-llamaindex`
"""
from __future__ import annotations
import asyncio
import time
from importlib.metadata import version

from llama_index.core.workflow import (
    Context, Event, StartEvent, StopEvent, Workflow, step,
    InputRequiredEvent, HumanResponseEvent, WorkflowTimeoutError,
)

from ._harness import EventLog, ProbeResult, summarize

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
    except Exception as e:  # noqa: BLE001
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
    """A step spawns a background worker (via to_thread) that will fire an
    effect after a delay, then the step returns. cancel_run() raises
    WorkflowCancelledByUser inside the workflow (cooperative cancellation,
    introspected from handler.cancel_run -> external_adapter.cancel). The
    worker thread is NOT owned by the workflow's cancellation, so it can still
    fire its effect after the run is reported cancelled."""

    @step
    async def spawn(self, ev: StartEvent, ctx: Context) -> StopEvent:
        LOG.log("C:step_started")

        def zombie():
            time.sleep(0.5)  # outlives the cancel
            LOG.log("C_EFFECT:executed_after_cancel")

        import threading
        threading.Thread(target=zombie, daemon=True).start()
        # keep the step alive so the run is genuinely in-flight at cancel time
        await asyncio.sleep(2.0)
        return StopEvent(result="ok")


async def probe_cancellation() -> ProbeResult:
    """PREDICATE (fixed before run): VIOLATION iff cancel_run() returns
    (caller believes the run stopped) AND the spawned effect executes anyway
    after cancellation. This is the A3 orphaned-effect axis with LlamaIndex's
    NATIVE cancellation surface, not a host wrapper."""
    LOG.clear()
    wf = CancelWF(timeout=10)
    handler = wf.run()
    await asyncio.sleep(0.2)  # let the step start and spawn the worker
    effect_at_cancel = LOG.contains("C_EFFECT:executed_after_cancel")
    await handler.cancel_run()  # native cancel; caller now believes it stopped
    cancelled_ack = True
    await asyncio.sleep(0.8)  # give the zombie time to fire
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
    """First step performs a side effect, then emits an event that the second
    step consumes. We serialize the Context AFTER the effect step has run and
    BEFORE completion, then resume via run(ctx=from_dict(...)). The question:
    does the resumed run re-execute the already-completed effect step?"""

    @step
    async def effect(self, ev: StartEvent, ctx: Context) -> ReplayEffectStart:
        LOG.log("R_EFFECT:executed")
        return ReplayEffectStart()

    @step
    async def finish(self, ev: ReplayEffectStart, ctx: Context) -> StopEvent:
        # small await so we can snapshot between the two steps in the probe
        await asyncio.sleep(0.05)
        return StopEvent(result="done")


async def probe_replay() -> ProbeResult:
    """PREDICATE (fixed before run): VIOLATION iff, after resuming from a
    serialized mid-run Context, the effect step executes a SECOND time
    (effect count 1 -> 2). Clean iff the effect executes exactly once across
    the original partial run and the resumed run. This is the A2 replay axis
    via Context.to_dict/from_dict (introspected as the documented persistence
    path). Marked NOT PROBED previously; now measured."""
    LOG.clear()
    from llama_index.core.workflow import Context as Ctx

    # Run 1: start, let the effect step fire, snapshot mid-run, then abandon.
    wf = ReplayWF(timeout=10)
    handler = wf.run()
    # poll until the effect has executed but before the workflow completes
    snap = None
    for _ in range(200):
        await asyncio.sleep(0.01)
        if LOG.contains("R_EFFECT:executed"):
            try:
                snap = handler.ctx.to_dict()
            except Exception as e:  # noqa: BLE001
                snap = None
                LOG.log(f"snap_err:{type(e).__name__}")
            break
    try:
        await handler  # let run 1 finish so state is well-defined
    except Exception:  # noqa: BLE001
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

    # Run 2: resume from the serialized context on a fresh workflow instance.
    wf2 = ReplayWF(timeout=10)
    try:
        restored = Ctx.from_dict(wf2, snap)
        await wf2.run(ctx=restored)
    except Exception as e:  # noqa: BLE001
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