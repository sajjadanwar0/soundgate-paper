from __future__ import annotations
import asyncio
import time
from importlib.metadata import version
from typing import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from ._harness import EventLog, ProbeResult, summarize

LOG = EventLog()


class S(TypedDict, total=False):
    note: str

def _parallel_gate_graph(gate_first: bool):
    def gate(state: S):
        LOG.log("gate:before_interrupt")
        decision = interrupt({"question": "approve the plan?"})
        LOG.log(f"gate:resumed_with={decision}")
        return {"note": f"gate:{decision}"}

    def side_effect(state: S):
        LOG.log("EFFECT:executed")
        return {}

    b = StateGraph(S)
    if gate_first:
        b.add_node("gate", gate)
        b.add_node("side_effect", side_effect)
    else:
        b.add_node("side_effect", side_effect)
        b.add_node("gate", gate)
    b.add_edge(START, "gate")
    b.add_edge(START, "side_effect")
    b.add_edge("gate", END)
    b.add_edge("side_effect", END)
    return b.compile(checkpointer=InMemorySaver())


def probe_sibling_leak(gate_first: bool, label: str) -> ProbeResult:
    LOG.clear()
    g = _parallel_gate_graph(gate_first)
    cfg = {"configurable": {"thread_id": f"t-{label}"}}
    result = g.invoke({"note": ""}, cfg)
    paused = "__interrupt__" in result
    effect_during_pause = LOG.contains("EFFECT:executed")
    trace = list(LOG.events)
    g.invoke(Command(resume=False), cfg)

    return ProbeResult(
        name=f"sibling_leak[{label}]",
        violation=paused and effect_during_pause,
        detail={"paused": paused, "effect_while_paused": effect_during_pause,
                "effect_total_after_reject": LOG.count("EFFECT:executed"),
                "trace_at_pause": trace},
    )

def probe_replay() -> ProbeResult:
    LOG.clear()

    def act_then_gate(state: S):
        LOG.log("P2_EFFECT:executed")
        decision = interrupt({"question": "approve?"})
        LOG.log(f"P2_gate:resumed_with={decision}")
        return {"note": "done"}

    b = StateGraph(S)
    b.add_node("act_then_gate", act_then_gate)
    b.add_edge(START, "act_then_gate")
    b.add_edge("act_then_gate", END)
    g = b.compile(checkpointer=InMemorySaver())
    cfg = {"configurable": {"thread_id": "t-p2"}}
    g.invoke({"note": ""}, cfg)
    at_pause = LOG.count("P2_EFFECT:executed")
    g.invoke(Command(resume=True), cfg)  # APPROVES
    after = LOG.count("P2_EFFECT:executed")

    return ProbeResult(
        name="replay_double_execution",
        violation=after > 1,
        detail={"effect_count_at_pause": at_pause, "effect_count_after_approve": after},
    )

def probe_cancellation(sync_in_thread: bool, label: str) -> ProbeResult:
    LOG.clear()

    def blocking_tool():
        time.sleep(0.6)
        LOG.log(f"{label}_EFFECT:executed_after_delay")

    async def node_sync(state: S):
        LOG.log(f"{label}:node_started")
        await asyncio.to_thread(blocking_tool)
        return {"note": "done"}

    async def node_async(state: S):
        LOG.log(f"{label}:node_started")
        await asyncio.sleep(0.6)
        LOG.log(f"{label}_EFFECT:executed_after_delay")
        return {"note": "done"}

    b = StateGraph(S)
    b.add_node("worker", node_sync if sync_in_thread else node_async)
    b.add_edge(START, "worker")
    b.add_edge("worker", END)
    g = b.compile(checkpointer=InMemorySaver())
    cfg = {"configurable": {"thread_id": f"t-{label}"}}

    async def scenario():
        task = asyncio.create_task(g.ainvoke({"note": ""}, cfg))

        await asyncio.sleep(0.15)
        task.cancel()
        seen = False
        try:
            await task
        except asyncio.CancelledError:
            seen = True
        at = LOG.contains("EFFECT")

        await asyncio.sleep(0.8)
        after = LOG.contains("EFFECT")

        return seen, at, after

    seen, at, after = asyncio.run(scenario())

    return ProbeResult(
        name=f"cancellation[{label}]",
        violation=seen and (not at) and after,
        detail={"cancelled_seen": seen, "effect_at_cancel": at,
                "effect_after_cancel": after},
    )


def probe_timeout_zombie() -> ProbeResult:
    LOG.clear()

    def blocking():
        time.sleep(0.8)
        LOG.log("TO_EFFECT:executed_after_delay")

    async def node(state: S):
        LOG.log("TO:node_started")
        await asyncio.to_thread(blocking)
        return {"note": "done"}

    b = StateGraph(S)
    b.add_node("worker", node)
    b.add_edge(START, "worker")
    b.add_edge("worker", END)
    g = b.compile(checkpointer=InMemorySaver())
    cfg = {"configurable": {"thread_id": "t-to"}}

    async def scenario():
        timed_out = False
        try:
            await asyncio.wait_for(g.ainvoke({"note": ""}, cfg), timeout=0.2)
        except asyncio.TimeoutError:
            timed_out = True
        at = LOG.contains("TO_EFFECT")
        await asyncio.sleep(1.0)
        after = LOG.contains("TO_EFFECT")
        return timed_out, at, after

    timed_out, at, after = asyncio.run(scenario())

    return ProbeResult(
        name="timeout_zombie",
        violation=timed_out and (not at) and after,
        detail={"caller_saw_timeout": timed_out, "effect_at_timeout": at,
                "effect_after_timeout": after},
    )


def main() -> None:
    print(f"# FW-A langgraph=={version('langgraph')}\n")
    results = [
        probe_sibling_leak(True, "gate_first"),
        probe_sibling_leak(False, "effect_first"),
        probe_replay(),
        probe_cancellation(True, "sync_thread"),
        probe_cancellation(False, "pure_async"),
        probe_timeout_zombie(),
    ]
    print(summarize(results))


if __name__ == "__main__":
    main()