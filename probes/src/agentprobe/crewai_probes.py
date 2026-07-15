import asyncio
import builtins
import os
import time
import warnings
from importlib.metadata import version
from typing import Any
from crewai import Agent, BaseLLM, Crew, Task
from crewai.tools import tool
from agentprobe._harness import EventLog, ProbeResult, summarize
import os
import tempfile
from crewai import Crew

warnings.filterwarnings("ignore")
os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")
os.environ.setdefault("CREWAI_TESTING", "true")

LOG = EventLog()

class ScriptedLLM(BaseLLM):
    """Emits one tool Action, then a Final Answer. Stateless decision rule:
    if the running conversation already contains an Observation (tool result),
    finish; otherwise act."""

    def __init__(self) -> None:
        super().__init__(model="scripted-stub")

    def call(
            self,
            messages: Any,
            tools: Any = None,
            callbacks: Any = None,
            available_functions: Any = None,
            from_task: Any = None,
            from_agent: Any = None,
            response_model: Any = None,
    ) -> str:
        LOG.log("llm:call")
        already_acted = False

        if isinstance(messages, list):
            for m in messages:
                if (
                        isinstance(m, dict)
                        and m.get("role") == "assistant"
                        and "Action: fire_effect" in str(m.get("content", ""))
                ):
                    already_acted = True

        if already_acted:
            return "Thought: the effect is done.\nFinal Answer: done"

        return (
            "Thought: I must perform the action.\n"
            "Action: fire_effect\n"
            "Action Input: {}"
        )

    def supports_function_calling(self) -> bool:
        return False


def _mk_effect_tool(tag: str, delay: float = 0.0):
    @tool("fire_effect")
    def fire_effect() -> str:
        """Perform the irreversible side effect."""
        if delay:
            time.sleep(delay)
        LOG.log(f"{tag}_EFFECT:executed")
        return "effect done"

    return fire_effect


def _mk_crew(tag: str, delay: float = 0.0, human_input: bool = False,
             max_execution_time: int | None = None) -> Crew:
    agent = Agent(
        role="worker",
        goal="perform the action",
        backstory="a deterministic probe agent",
        llm=ScriptedLLM(),
        tools=[_mk_effect_tool(tag, delay)],
        verbose=False,
        max_iter=4,
        max_execution_time=max_execution_time,
    )
    task = Task(
        description="perform the action using the fire_effect tool",
        expected_output="the word done",
        agent=agent,
        human_input=human_input,
    )
    return Crew(agents=[agent], tasks=[task], verbose=False)

def run_c1() -> ProbeResult:
    LOG.clear()
    real_input = builtins.input

    def fake_input(prompt: str = "") -> str:
        LOG.log("HUMAN:feedback_requested")
        return ""  # accept

    builtins.input = fake_input
    try:
        crew = _mk_crew("C1", human_input=True)
        crew.kickoff()
    finally:
        builtins.input = real_input
    events = list(LOG.events)
    effect_idx = next((i for i, e in enumerate(events) if "C1_EFFECT" in e), None)
    human_idx = next(
        (i for i, e in enumerate(events) if "HUMAN:feedback_requested" in e), None
    )
    effect_before_review = (
            effect_idx is not None and human_idx is not None and effect_idx < human_idx
    )
    return ProbeResult(
        "review_after_effect[human_input]",
        violation=effect_before_review,
        detail={
            "effect_executed": effect_idx is not None,
            "feedback_requested": human_idx is not None,
            "effect_before_review": effect_before_review,
            "note": "human_input is post-hoc feedback by design; no "
                    "pre-execution approval primitive exists in OSS CrewAI",
        },
    )

async def _c3() -> ProbeResult:
    LOG.clear()
    crew = _mk_crew("C3", delay=0.8)
    run = asyncio.create_task(crew.kickoff_async())

    for _ in range(100):
        await asyncio.sleep(0.02)
        if LOG.contains("llm:call"):
            break
    await asyncio.sleep(0.3)
    run.cancel()
    cancelled_seen = False
    caller_saw = None

    try:
        await run
    except asyncio.CancelledError:
        cancelled_seen = True
    except Exception as e:
        caller_saw = type(e).__name__
    effect_at_cancel = LOG.contains("C3_EFFECT")

    await asyncio.sleep(1.2)
    effect_after = LOG.contains("C3_EFFECT")

    return ProbeResult(
        "cancellation[kickoff_async]",
        violation=cancelled_seen and (not effect_at_cancel) and effect_after,
        detail={
            "cancelled_seen": cancelled_seen,
            "caller_saw_other": caller_saw,
            "effect_at_cancel": effect_at_cancel,
            "effect_after_cancel": effect_after,
        },
    )

def run_c3() -> ProbeResult:
    return asyncio.run(_c3())


def run_c4_strict_zombie() -> ProbeResult:
    LOG.clear()
    crew = _mk_crew("C4", delay=2.2, max_execution_time=1)
    timed_out = False
    err = None

    try:
        crew.kickoff()
    except Exception as e:
        timed_out = "timed out" in str(e).lower() or isinstance(e, TimeoutError)
        err = type(e).__name__
    effect_at_timeout = LOG.contains("C4_EFFECT")
    time.sleep(2.0)
    effect_after = LOG.contains("C4_EFFECT")

    return ProbeResult(
        "timeout_zombie_strict[max_execution_time]",
        violation=timed_out and (not effect_at_timeout) and effect_after,
        detail={
            "caller_saw_timeout": timed_out,
            "caller_exception": err,
            "effect_at_timeout": effect_at_timeout,
            "effect_after_timeout": effect_after,
        },
    )


def run_c4b_blocking_overrun() -> ProbeResult:
    LOG.clear()
    deadline = 1.0
    crew = _mk_crew("C4B", delay=2.2, max_execution_time=int(deadline))
    t0 = time.perf_counter()
    timed_out = False
    err = None

    try:
        crew.kickoff()
    except Exception as e:
        timed_out = "timed out" in str(e).lower() or isinstance(e, TimeoutError)
        err = type(e).__name__

    surfaced_at = time.perf_counter() - t0
    effect_happened = LOG.contains("C4B_EFFECT")
    time.sleep(0.5)
    effect_happened = effect_happened or LOG.contains("C4B_EFFECT")
    overrun = surfaced_at >= 1.5 * deadline

    return ProbeResult(
        "timeout_blocks_then_effect[max_execution_time]",
        violation=timed_out and effect_happened and overrun,
        detail={
            "caller_saw_timeout": timed_out,
            "caller_exception": err,
            "timeout_surfaced_at_s": round(surfaced_at, 2),
            "declared_deadline_s": deadline,
            "effect_executed_despite_timeout": effect_happened,
        },
    )

def run_c5_checkpoint_replay() -> ProbeResult:
    try:
        from crewai.state.checkpoint_config import CheckpointConfig
    except Exception as e:  # noqa: BLE001
        return ProbeResult("replay[checkpoint_resume]", violation=False,
                           detail={"outcome": "NOT PROBED: CheckpointConfig import failed",
                                   "err": f"{type(e).__name__}: {e}"})

    LOG.clear()

    with tempfile.TemporaryDirectory() as d:
        crew1 = _mk_crew("C5")
        crew1.checkpoint = CheckpointConfig(location=d, on_events=["task_completed"])
        try:
            crew1.kickoff()
        except Exception as e:
            LOG.log(f"run1_err:{type(e).__name__}")
        count_run1 = LOG.count("C5_EFFECT:executed")

        written = []

        for root, _dirs, files in os.walk(d):
            written += [os.path.join(root, f) for f in files]

        if not written:
            return ProbeResult(
                "replay[checkpoint_resume]",
                violation=False,
                detail={"outcome": "NOT PROBED: checkpoint write fails for tool-bearing crews",
                        "reason": "PydanticSerializationError on tool function object "
                                  "(crewai serializes RuntimeState via model_dump(mode='json'))",
                        "effect_count_run1": count_run1,
                        "VERIFY": "revisit with a crewai-serializable tool (structured tool "
                                  "or registered function) if this axis becomes load-bearing"},
            )

        resumed_ok = False

        try:
            ckpt = written[0]
            crew2 = Crew.from_checkpoint(CheckpointConfig(restore_from=ckpt))
            crew2.kickoff()
            resumed_ok = True
        except Exception as e:
            LOG.log(f"resume_err:{type(e).__name__}")
        count_total = LOG.count("C5_EFFECT:executed")

    replayed = count_total > count_run1
    return ProbeResult(
        "replay[checkpoint_resume]",
        violation=replayed,
        detail={"effect_count_run1": count_run1,
                "effect_count_after_resume": count_total,
                "resume_completed": resumed_ok,
                "checkpoint_file": written[0],
                "note": "restore via Crew.from_checkpoint(restore_from=file) + kickoff(); "
                        "violation = completed task's effect re-executed on resume"},
    )

def main() -> None:
    print(f"# FW-E crewai=={version('crewai')}\n")
    c1 = run_c1()
    c3 = run_c3()
    c4 = run_c4_strict_zombie()
    c4b = run_c4b_blocking_overrun()
    try:
        c5 = run_c5_checkpoint_replay()
    except Exception as e:
        c5 = ProbeResult("replay[checkpoint_resume]", violation=False,
                         detail={"outcome": "NOT PROBED: probe raised",
                                 "err": f"{type(e).__name__}: {e}", "VERIFY": True})
    print(summarize([c1, c3, c4, c4b, c5]))


if __name__ == "__main__":
    main()