import asyncio
import json
import socket
import subprocess
import threading
import time
import warnings
from dataclasses import dataclass
from pathlib import Path

warnings.filterwarnings("ignore")

import agent_framework as af
from agent_framework import WorkflowContext

ADDR = ("127.0.0.1", 8808)
BIN = Path(__file__).resolve().parents[1] / "target" / "release" / "soundgate"

class GateClient:
    def __init__(self, addr=ADDR):
        self.sock = socket.create_connection(addr, timeout=5.0)
        self.rf = self.sock.makefile("r")
        self.lock = threading.Lock()

    def _call(self, req: dict) -> str:
        with self.lock:
            self.sock.sendall((json.dumps(req) + "\n").encode())
            return json.loads(self.rf.readline())["verdict"]

    def mediated_effect(self, run_id, effect_key, do_effect, needs_approval):
        v = self._call({"op": "submit", "run_id": run_id,
                        "effect_key": effect_key,
                        "needs_approval": needs_approval})
        if v == "release":
            do_effect()
        return v

    def decide(self, run_id, effect_key, approved):
        return self._call({"op": "decide", "run_id": run_id,
                           "effect_key": effect_key, "approved": approved})

    def cancel(self, run_id):
        return self._call({"op": "cancel", "run_id": run_id})


EFFECTS = []
gate = None
SIBLING_VERDICT = []

@dataclass
class ApprovalRequest:
    question: str = "approve the plan?"

class GateExecutor(af.Executor):
    @af.handler
    async def start(self, msg: str, ctx: WorkflowContext) -> None:
        await ctx.request_info(ApprovalRequest(), str)

    @af.response_handler
    async def on_decision(
            self, original: ApprovalRequest, decision: str, ctx: WorkflowContext
    ) -> None:
        pass

async def scenario_a() -> bool:
    EFFECTS.clear()
    SIBLING_VERDICT.clear()

    @af.executor(id="fan")
    async def fan(msg: str, ctx: WorkflowContext[str]) -> None:
        await ctx.send_message(msg)

    @af.executor(id="side_effect")
    async def side_effect(msg: str, ctx: WorkflowContext) -> None:
        v = gate.mediated_effect(
            "runA", "send_email",
            lambda: EFFECTS.append("send_email"),
            needs_approval=True,
        )
        SIBLING_VERDICT.append(v)

    gate_exec = GateExecutor(id="gate")
    wf = (
        af.WorkflowBuilder(start_executor=fan)
        .add_fan_out_edges(fan, [gate_exec, side_effect])
        .build()
    )
    result = await wf.run("go")
    paused = result.get_final_state() == af.WorkflowRunState.IDLE_WITH_PENDING_REQUESTS
    effects_during_pause = len(EFFECTS)
    d = gate.decide("runA", "send_email", approved=False)
    requests = result.get_request_info_events()

    if requests:
        await wf.run(responses={requests[0].request_id: "no"})
    ok = (paused
          and effects_during_pause == 0
          and SIBLING_VERDICT == ["held_for_approval"]
          and d == "refused_rejected"
          and len(EFFECTS) == 0)
    print(f"A sibling-leak repaired   : paused={paused} "
          f"sibling={SIBLING_VERDICT[0] if SIBLING_VERDICT else '?'} "
          f"effects_during_pause={effects_during_pause} reject={d} "
          f"effects_total={len(EFFECTS)} "
          f"-> {'HELD+REFUSED (repaired)' if ok else 'LEAK'}")

    return ok


async def scenario_c() -> bool:
    EFFECTS.clear()

    def blocking_tool() -> None:
        time.sleep(0.8)
        gate.mediated_effect("runC", "post_webhook",
                             lambda: EFFECTS.append("post_webhook"),
                             needs_approval=False)

    @af.executor(id="worker")
    async def worker(msg: str, ctx: WorkflowContext) -> None:
        await asyncio.to_thread(blocking_tool)

    wf = af.WorkflowBuilder(start_executor=worker).build()
    task = asyncio.create_task(wf.run("go"))

    await asyncio.sleep(0.2)

    gate.cancel("runC")
    task.cancel()
    cancelled_seen = False

    try:
        await task
    except asyncio.CancelledError:
        cancelled_seen = True
    except Exception:
        pass
    await asyncio.sleep(1.2)
    ok = cancelled_seen and len([e for e in EFFECTS if e == "post_webhook"]) == 0

    print(f"C zombie fenced           : cancelled_seen={cancelled_seen} "
          f"zombie_effect_executed={len(EFFECTS) != 0} "
          f"effects_total={len(EFFECTS)} "
          f"-> {'FENCED (repaired)' if ok else 'ORPHANED'}")

    return ok

async def scenario_d() -> bool:
    EFFECTS.clear()

    def blocking_tool() -> None:
        time.sleep(0.8)
        gate.mediated_effect("runT", "issue_refund",
                             lambda: EFFECTS.append("issue_refund"),
                             needs_approval=False)

    @af.executor(id="worker")
    async def worker(msg: str, ctx: WorkflowContext) -> None:
        await asyncio.to_thread(blocking_tool)

    wf = af.WorkflowBuilder(start_executor=worker).build()
    timed_out = False

    try:
        await asyncio.wait_for(wf.run("go"), timeout=0.25)
    except asyncio.TimeoutError:
        timed_out = True
        gate.cancel("runT")

    await asyncio.sleep(1.2)

    ok = timed_out and len([e for e in EFFECTS if e == "issue_refund"]) == 0

    print(f"D timeout zombie fenced   : caller_saw_timeout={timed_out} "
          f"zombie_effect_executed={len(EFFECTS) != 0} "
          f"effects_total={len(EFFECTS)} "
          f"-> {'FENCED (repaired)' if ok else 'ZOMBIE'}")

    return ok

async def main():
    global gate
    srv = subprocess.Popen([str(BIN), f"{ADDR[0]}:{ADDR[1]}"],
                           stderr=subprocess.DEVNULL)
    time.sleep(0.5)
    try:
        gate = GateClient()
        a = await scenario_a()
        c = await scenario_c()
        d = await scenario_d()
        n = int(a) + int(c) + int(d)
        print(f"\nE-E2E-C (real agent-framework-core==1.10.0): {n}/3 violation "
              f"classes repaired in situ (replay is natively clean on FW-C)")
        return 0 if n == 3 else 1
    finally:
        srv.terminate()

if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))