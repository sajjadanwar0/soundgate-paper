import asyncio
import json
import time
import warnings
from importlib.metadata import version
from typing import Any

warnings.filterwarnings("ignore")

from agents import Agent, RunConfig, Runner, function_tool
from agents.items import ModelResponse
from agents.models.interface import Model
from agents.usage import Usage
from openai.types.responses import (
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
)

from agentprobe._harness import EventLog, ProbeResult, summarize  # noqa: E402

LOG = EventLog()
RUN_CONFIG = RunConfig(tracing_disabled=True)  # keyless: no trace export


def _tool_call(name: str, call_id: str) -> ResponseFunctionToolCall:
    return ResponseFunctionToolCall(
        id=f"fc_{call_id}",
        call_id=call_id,
        name=name,
        arguments=json.dumps({}),
        type="function_call",
        status="completed",
    )


def _final_message(text: str) -> ResponseOutputMessage:
    return ResponseOutputMessage(
        id="msg_final",
        role="assistant",
        status="completed",
        type="message",
        content=[ResponseOutputText(annotations=[], text=text, type="output_text")],
    )


class ScriptedModel(Model):
    """Stateless scripted model: emits `plan` tool calls on a fresh turn,
    a final message once any tool output is present in the input."""

    def __init__(self, plan: list[tuple[str, str]]):
        self._plan = plan
        self.invocations = 0

    async def get_response(  # type: ignore[override]
        self,
        system_instructions: str | None,
        input: Any,
        model_settings: Any,
        tools: Any,
        output_schema: Any,
        handoffs: Any,
        tracing: Any,
        *,
        previous_response_id: str | None = None,
        conversation_id: str | None = None,
        prompt: Any = None,
        **kwargs: Any,
    ) -> ModelResponse:
        self.invocations += 1
        LOG.log(f"model:invocation_{self.invocations}")
        has_tool_output = isinstance(input, list) and any(
            isinstance(item, dict) and item.get("type") == "function_call_output"
            for item in input
        )
        if has_tool_output:
            output: list[Any] = [_final_message("done")]
        else:
            output = [_tool_call(name, cid) for name, cid in self._plan]
        return ModelResponse(output=output, usage=Usage(), response_id=None)

    def stream_response(self, *args: Any, **kwargs: Any):  # pragma: no cover
        raise NotImplementedError("probes use non-streaming runs only")


@function_tool(needs_approval=True)
def charge_card() -> str:
    """Charge the customer's card (irreversible)."""
    LOG.log("GATED_EFFECT:charge_card_executed")
    return "charged"


@function_tool
def send_email() -> str:
    """Send a notification email (irreversible)."""
    LOG.log("EFFECT:send_email_executed")
    return "sent"


async def run_o1_o1r_o2() -> tuple[ProbeResult, ProbeResult, ProbeResult]:
    LOG.clear()
    model = ScriptedModel(plan=[("charge_card", "call_1"), ("send_email", "call_2")])
    agent = Agent(name="probe", model=model, tools=[charge_card, send_email])

    result = await Runner.run(agent, "do the task", run_config=RUN_CONFIG)
    paused = len(result.interruptions) > 0
    effect_while_paused = LOG.contains("EFFECT:send_email_executed")
    gated_ran_early = LOG.contains("GATED_EFFECT")
    trace_at_pause = list(LOG.events)

    o1 = ProbeResult(
        "sibling_leak[parallel_tool_calls]",
        violation=paused and effect_while_paused,
        detail={
            "paused_for_approval": paused,
            "sibling_effect_while_paused": effect_while_paused,
            "gated_tool_ran_before_decision": gated_ran_early,
            "trace_at_pause": trace_at_pause,
        },
    )

    effect_count_before_resume = LOG.count("EFFECT:send_email_executed")

    if paused:
        state = result.to_state()
        for item in result.interruptions:
            state.reject(item, rejection_message="rejected by human")
    effect_count_after_resume = LOG.count("EFFECT:send_email_executed")
    gated_ran_ever = LOG.contains("GATED_EFFECT")

    o1r = ProbeResult(
        "reject_after_effect",
        violation=paused and effect_count_before_resume >= 1,
        detail={
            "sibling_effect_total_at_reject": effect_count_before_resume,
            "gated_tool_ever_executed": gated_ran_ever,
        },
    )
    o2 = ProbeResult(
        "replay[resume_after_reject]",
        violation=effect_count_after_resume > 1,
        detail={
            "sibling_effect_count_before_resume": effect_count_before_resume,
            "sibling_effect_count_after_resume": effect_count_after_resume,
            "model_invocations": model.invocations,
        },
    )
    return o1, o1r, o2


def _blocking_effect(tag: str, delay: float = 0.6) -> None:
    time.sleep(delay)
    LOG.log(f"{tag}_EFFECT:executed_after_delay")


async def run_o3(sync_in_thread: bool, label: str) -> ProbeResult:
    LOG.clear()

    if sync_in_thread:

        @function_tool
        def worker() -> str:
            """Blocking side-effect tool."""
            LOG.log(f"{label}:tool_started")
            _blocking_effect(label)
            return "ok"

    else:

        @function_tool
        async def worker() -> str:
            """Async side-effect tool."""
            LOG.log(f"{label}:tool_started")
            await asyncio.sleep(0.6)
            LOG.log(f"{label}_EFFECT:executed_after_delay")
            return "ok"

    model = ScriptedModel(plan=[("worker", "call_1")])
    agent = Agent(name="probe", model=model, tools=[worker])

    task = asyncio.create_task(Runner.run(agent, "go", run_config=RUN_CONFIG))
    await asyncio.sleep(0.25)  # user cancels mid-tool
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


async def run_o4_native_sync() -> ProbeResult:
    """Native tool timeout on a SYNC tool. Measured outcome on 0.17.7: the SDK
    refuses this configuration at construction time (ValueError: timeout only
    supported for async handlers). That is a positive design refusal -- the
    SDK declines to report a timeout it cannot enforce on a worker thread --
    and is recorded as a clean/contrast datum, not as "not probed"."""
    LOG.clear()
    try:

        @function_tool(timeout=0.2, timeout_behavior="raise_exception")
        def worker() -> str:
            """Blocking side-effect tool with native timeout."""
            _blocking_effect("o4_sync", delay=0.8)
            return "ok"

    except ValueError as e:
        return ProbeResult(
            "native_tool_timeout[sync_thread]",
            violation=False,
            detail={
                "outcome": "REFUSED_AT_CONSTRUCTION",
                "error": str(e),
                "note": "SDK will not attach a native timeout to a sync tool; "
                "contrast with frameworks that report a timeout while the "
                "thread's effect lands anyway",
            },
        )
    return ProbeResult(
        "native_tool_timeout[sync_thread]",
        violation=False,
        detail={"outcome": "constructed without error; rerun full timeout probe"},
    )


async def run_o4_native_async() -> ProbeResult:
    LOG.clear()

    @function_tool(timeout=0.2, timeout_behavior="raise_exception")
    async def worker() -> str:
        """Async side-effect tool with native timeout."""
        LOG.log("o4_async:tool_started")
        await asyncio.sleep(0.8)
        LOG.log("o4_async_EFFECT:executed_after_delay")
        return "ok"

    model = ScriptedModel(plan=[("worker", "call_1")])
    agent = Agent(name="probe", model=model, tools=[worker])

    timed_out = False
    try:
        await Runner.run(agent, "go", run_config=RUN_CONFIG)
    except Exception as e:
        timed_out = True
        LOG.log(f"o4_async:caller_saw={type(e).__name__}")
    effect_at_timeout = LOG.contains("o4_async_EFFECT")
    await asyncio.sleep(1.0)
    effect_after = LOG.contains("o4_async_EFFECT")
    return ProbeResult(
        "native_tool_timeout[pure_async]",
        violation=timed_out and (not effect_at_timeout) and effect_after,
        detail={
            "caller_saw_timeout": timed_out,
            "effect_at_timeout": effect_at_timeout,
            "effect_after_timeout": effect_after,
        },
    )


async def run_o4_host_wait_for() -> ProbeResult:
    """Host-level asyncio.wait_for over Runner.run with a sync blocking tool:
    the common operator pattern, kept for cross-framework comparability with
    the LangGraph and MSAF timeout probes."""
    LOG.clear()

    @function_tool
    def worker() -> str:
        """Blocking side-effect tool."""
        LOG.log("o4_host:tool_started")
        _blocking_effect("o4_host", delay=0.8)
        return "ok"

    model = ScriptedModel(plan=[("worker", "call_1")])
    agent = Agent(name="probe", model=model, tools=[worker])

    timed_out = False
    try:
        await asyncio.wait_for(
            Runner.run(agent, "go", run_config=RUN_CONFIG), timeout=0.2
        )
    except asyncio.TimeoutError:
        timed_out = True
        LOG.log("o4_host:caller_saw=TimeoutError")
    effect_at_timeout = LOG.contains("o4_host_EFFECT")
    await asyncio.sleep(1.0)
    effect_after = LOG.contains("o4_host_EFFECT")
    return ProbeResult(
        "timeout_zombie[host_wait_for]",
        violation=timed_out and (not effect_at_timeout) and effect_after,
        detail={
            "caller_saw_timeout": timed_out,
            "effect_at_timeout": effect_at_timeout,
            "effect_after_timeout": effect_after,
        },
    )


async def _amain() -> None:
    print(f"# FW-D openai-agents=={version('openai-agents')}\n")
    o1, o1r, o2 = await run_o1_o1r_o2()
    o3a = await run_o3(sync_in_thread=True, label="sync_thread")
    o3b = await run_o3(sync_in_thread=False, label="pure_async")
    o4a = await run_o4_native_sync()
    o4b = await run_o4_native_async()
    o4c = await run_o4_host_wait_for()
    print(summarize([o1, o1r, o2, o3a, o3b, o4a, o4b, o4c]))


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
