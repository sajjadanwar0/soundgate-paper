"""SOUNDGATE ↔ LangGraph integration.

Wraps side-effecting work in a LangGraph node so every external effect is
admitted by the gate before it executes, following the paper's contract:
the effect runs ONLY on a `release` verdict.

Two effect kinds:

  * needs_approval=False — dedup/cancel/timeout protection with no human in the
    loop. `submit` returns `release` immediately (first time) and the effect
    runs; a replay of the same (thread, key) is refused as a duplicate, and a
    cancelled/closed thread's effect is fenced. No graph pause.

  * needs_approval=True — human-in-the-loop. `submit` HOLDS the effect (it does
    NOT run); the node raises LangGraph `interrupt(...)` to collect a decision;
    on resume you call `gate.decide(...)`, and the effect runs iff the verdict
    is `release`. A SIBLING branch that submits a *consequential* effect
    (needs_approval=True) during the pause is held by the same gate — that is
    the sibling-leak repair. Mark every externally-consequential effect
    needs_approval=True (or make it your deployment policy); the gate then holds
    all of them during any pause, and a per-effect decision (or a run cancel,
    which fences every held effect at once) governs whether each executes.

Map LangGraph's `thread_id` (the cancellable unit) to the gate's `run_id`, and
use a stable, caller-named `effect_key` per logical effect within the thread.

Works with either client:
    from soundgate import GateClient            # PyO3 extension
    # from soundgate_client import GateClient   # pure-Python
"""

from __future__ import annotations

from typing import Callable, Optional


def thread_run_id(config: dict) -> str:
    """Derive the gate run_id from a LangGraph RunnableConfig."""
    return str(config["configurable"]["thread_id"])


def mediate_no_approval(gate, run_id: str, effect_key: str, do_effect: Callable[[], object]):
    """Effect with no human approval. Runs on release; safe under replay/cancel."""
    v = gate.submit(run_id, effect_key, needs_approval=False)
    if v == "release":
        return do_effect()
    return f"[gate: {v}] effect not performed"


def mediate_with_approval(
        gate,
        run_id: str,
        effect_key: str,
        do_effect: Callable[[], object],
        interrupt_fn: Callable[[object], object],
        prompt: object = "approve this effect?",
        resume_to_approved: Callable[[object], bool] = bool,
):
    """Human-in-the-loop effect.

    First pass: submit holds the effect and we `interrupt` for a decision.
    On resume: `interrupt_fn` returns the human's payload; we `decide` and run
    the effect iff released. `interrupt_fn` is LangGraph's `interrupt` (passed
    in so this module has no hard LangGraph dependency); `resume_to_approved`
    maps that payload to a bool.
    """
    v = gate.submit(run_id, effect_key, needs_approval=True)
    if v == "release":
        # Rare: gate configured to auto-release this identity.
        return do_effect()
    if v != "held_for_approval":
        # duplicate / cancelled / rejected — never run.
        return f"[gate: {v}] effect not performed"

    # Held. Pause the graph for a decision. On resume, `payload` is the human's
    # answer supplied via Command(resume=...).
    payload = interrupt_fn({"approve": {"effect_key": effect_key}, "prompt": prompt})
    approved = resume_to_approved(payload)
    decision = gate.decide(run_id, effect_key, approved)
    if decision == "release":
        return do_effect()
    return f"[gate: {decision}] effect not performed"


# --------------------------------------------------------------------------
# Runnable local demo (no LLM, no real graph needed): shows the gate flow a
# node would drive. Start the gate first:  ./target/release/soundgate 127.0.0.1:8796
# then:  python soundgate_langgraph.py
# --------------------------------------------------------------------------
if __name__ == "__main__":
    try:
        from soundgate import GateClient
    except ModuleNotFoundError:
        from soundgate_client import GateClient  # type: ignore

    gate = GateClient("127.0.0.1:8796") if "GateClient" in dir() else None
    run = "thread-demo-1"
    log = []

    def send_email():
        log.append("EMAIL SENT")
        return "sent"

    # 1) no-approval effect runs, replay is deduped
    print("no-approval:", mediate_no_approval(gate, run, "welcome_email", send_email))
    print("replay     :", mediate_no_approval(gate, run, "welcome_email", send_email))

    # 2) approval effect: simulate interrupt+resume with an approve then a reject
    def fake_interrupt(_): return {"approved": True}
    print("approve    :", mediate_with_approval(
        gate, run, "refund_500", lambda: (log.append("REFUND 500"), "refunded")[1],
        interrupt_fn=fake_interrupt, resume_to_approved=lambda p: p["approved"]))

    def fake_reject(_): return {"approved": False}
    print("reject     :", mediate_with_approval(
        gate, run, "wire_10000", lambda: (log.append("WIRE 10000"), "wired")[1],
        interrupt_fn=fake_reject, resume_to_approved=lambda p: p["approved"]))

    print("effects performed:", log)
    assert log == ["EMAIL SENT", "REFUND 500"], log
    print("OK — approved effects ran, replay+rejected effects did not")