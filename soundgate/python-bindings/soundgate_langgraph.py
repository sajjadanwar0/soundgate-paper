from __future__ import annotations

from typing import Callable, Optional


def thread_run_id(config: dict) -> str:
    return str(config["configurable"]["thread_id"])


def mediate_no_approval(gate, run_id: str, effect_key: str, do_effect: Callable[[], object]):
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
    v = gate.submit(run_id, effect_key, needs_approval=True)
    if v == "release":
        return do_effect()

    if v != "held_for_approval":
        return f"[gate: {v}] effect not performed"

    payload = interrupt_fn({"approve": {"effect_key": effect_key}, "prompt": prompt})
    approved = resume_to_approved(payload)
    decision = gate.decide(run_id, effect_key, approved)

    if decision == "release":
        return do_effect()
    return f"[gate: {decision}] effect not performed"

if __name__ == "__main__":
    try:
        from soundgate import GateClient
    except ModuleNotFoundError:
        from soundgate_client import GateClient

    gate = GateClient("127.0.0.1:8796") if "GateClient" in dir() else None
    run = "thread-demo-1"
    log = []

    def send_email():
        log.append("EMAIL SENT")
        return "sent"

    print("no-approval:", mediate_no_approval(gate, run, "welcome_email", send_email))
    print("replay     :", mediate_no_approval(gate, run, "welcome_email", send_email))

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