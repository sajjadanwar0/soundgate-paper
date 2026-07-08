"""E-E2E-B: soundgate wired into a REAL LlamaIndex Workflows agent (keyless).

The FW-A demo (e2e_langgraph.py) repairs a Pregel/superstep runtime; this
repairs FW-B's event-driven runtime -- the second, independently designed
execution model -- answering the "one framework is a case study" objection
with the two frameworks' two architectures.

Scenarios mirror FW-B's measured violation axes (probe transcript:
probes/results/llamaindex.txt):
  A. SIBLING LEAK + REJECT-AFTER-EFFECT REPAIRED: fan-out to a gate step
     (InputRequiredEvent) and a sibling effect step; the sibling's effect is
     mediated -> HELD while the run awaits human input; the human rejects
     both -> ZERO effects executed. (Unmediated, the probe shows the sibling
     effect firing before the human response.)
  C. CANCELLATION ZOMBIE FENCED: a step spawns a worker thread that fires a
     mediated effect after a delay; the run is cancelled via the native
     cancel_run() (which the probe shows does NOT cover the thread); the
     zombie's later submission is refused_cancelled -> zero post-cancel
     effects.
Replay is not demonstrated here because FW-B is natively CLEAN on that axis
(Context.from_dict does not re-execute completed steps; probe
replay[context_restore] 1->1) -- there is nothing to repair.

Run (uses the probes venv for llama-index-core==0.14.23; gate binary built):
  cd soundgate && cargo build --release
  ../probes/.venv/bin/python e2e/e2e_llamaindex.py
"""
from __future__ import annotations

import asyncio
import json
import socket
import subprocess
import threading
import time
from pathlib import Path

from llama_index.core.workflow import (
    Context,
    Event,
    HumanResponseEvent,
    InputRequiredEvent,
    StartEvent,
    StopEvent,
    Workflow,
    step,
)

ADDR = ("127.0.0.1", 8807)
BIN = Path(__file__).resolve().parents[1] / "target" / "release" / "soundgate"


# ---------------------------------------------------------------- gate shim
class GateClient:
    """~20-line mediation wrapper: submit; perform the effect ONLY on release."""

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


EFFECTS: list[str] = []          # the world: what actually executed
gate: GateClient | None = None   # set in main()


# ------------------------------------------------- Scenario A: sibling leak
class GoEffect(Event): ...
class GoGate(Event): ...
class EffectDone(Event):
    verdict: str
class GateDone(Event):
    resumed: str


class MediatedParallelWF(Workflow):
    """Same fan-out shape as the violation probe, sibling effect mediated."""

    @step
    async def fan(self, ev: StartEvent, ctx: Context) -> GoGate | GoEffect:
        ctx.send_event(GoEffect())
        return GoGate()

    @step
    async def sibling(self, ev: GoEffect, ctx: Context) -> EffectDone:
        v = gate.mediated_effect(
            "runA", "send_email",
            lambda: EFFECTS.append("send_email"),
            needs_approval=True,
        )
        return EffectDone(verdict=v)

    @step
    async def gate_step(self, ev: GoGate, ctx: Context) -> GateDone:
        ctx.write_event_to_stream(InputRequiredEvent(prefix="approve?"))
        resp = await ctx.wait_for_event(HumanResponseEvent)
        return GateDone(resumed=resp.response)

    @step
    async def done(self, ev: EffectDone | GateDone, ctx: Context) -> StopEvent | None:
        got = ctx.collect_events(ev, [EffectDone, GateDone])
        if got is None:
            return None
        return StopEvent(result={"sibling_verdict": got[0].verdict,
                                 "human": got[1].resumed})


async def scenario_a() -> bool:
    wf = MediatedParallelWF(timeout=20)
    handler = wf.run()
    effects_during_pause = None
    sibling_verdict_at_pause = None
    async for ev in handler.stream_events():
        if isinstance(ev, InputRequiredEvent):
            # Run is now paused for human input; the sibling has raced ahead.
            await asyncio.sleep(0.3)  # let the sibling step finish its submit
            effects_during_pause = len(EFFECTS)
            # HUMAN REJECTS: the run continues (framework semantics), but the
            # gate refuses the held effect forever.
            d = gate.decide("runA", "send_email", approved=False)
            sibling_verdict_at_pause = d
            handler.ctx.send_event(HumanResponseEvent(response="no"))
    res = await handler
    ok = (effects_during_pause == 0
          and sibling_verdict_at_pause == "refused_rejected"
          and res["sibling_verdict"] == "held_for_approval"
          and len(EFFECTS) == 0)
    print(f"A sibling-leak repaired   : paused=True sibling={res['sibling_verdict']} "
          f"effects_during_pause={effects_during_pause} "
          f"reject={sibling_verdict_at_pause} effects_total={len(EFFECTS)} "
          f"-> {'HELD+REFUSED (repaired)' if ok else 'LEAK'}")
    return ok


# -------------------------------------------- Scenario C: cancellation zombie
class CancelWF(Workflow):
    @step
    async def spawn(self, ev: StartEvent, ctx: Context) -> StopEvent:
        def zombie():
            time.sleep(0.8)  # outlives the cancellation below
            gate.mediated_effect("runC", "post_webhook",
                                 lambda: EFFECTS.append("post_webhook"),
                                 needs_approval=False)
        threading.Thread(target=zombie, daemon=False).start()
        await asyncio.sleep(5.0)  # cancelled long before this completes
        return StopEvent(result="never")


async def scenario_c() -> bool:
    wf = CancelWF(timeout=30)
    handler = wf.run()
    await asyncio.sleep(0.2)
    gate.cancel("runC")            # the shim's cancel accompanies...
    try:
        await handler.cancel_run() # ...the framework's native cancel
    except Exception:
        pass
    time.sleep(1.2)                # zombie thread wakes, submits, is fenced
    ok = len([e for e in EFFECTS if e == "post_webhook"]) == 0
    print(f"C zombie fenced           : cancel=native+gate zombie_effect_executed="
          f"{not ok} effects_total={len(EFFECTS)} "
          f"-> {'FENCED (repaired)' if ok else 'ORPHANED'}")
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
        n = int(a) + int(c)
        print(f"\nE-E2E-B (real llama-index-core==0.14.23): {n}/2 violation "
              f"classes repaired in situ (replay is natively clean on FW-B)")
        return 0 if n == 2 else 1
    finally:
        srv.terminate()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))