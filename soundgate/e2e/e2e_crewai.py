"""E-E2E FW-E (CrewAI): fence the cancel + timeout violations via SoundGate.

FW-E ships NO pre-execution approval primitive, so there is no sibling leak to
repair (the paper counts it as a design contrast, not a violation). But its two
real violations -- worker-thread/async cancellation orphan (probe C3) and the
native max_execution_time zombie (probe C4) -- take the SAME fence as every
other framework: gate.cancel(run), after which the late effect submission meets
refused_cancelled and never executes.

This harness runs the REAL crewai crew, reusing the measurement probe's own
ScriptedLLM and crew shape (probes/src/agentprobe/crewai_probes.py) so the only
change from the violation is that the effect tool is MEDIATED: it submits to the
live Rust gate and logs the effect only on "release". That makes FW-E a result
on those two axes, not a design argument.

Run:
  python -m venv .venv-crewai && . .venv-crewai/bin/activate
  pip install 'crewai==1.15.1'
  cd soundgate && cargo build --release
  ../.venv-crewai/bin/python e2e/e2e_crewai.py
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

# Silence CrewAI's interactive telemetry prompt exactly as the probe does.
os.environ.setdefault("CREWAI_TELEMETRY_OPT_OUT", "true")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")

from crewai import Agent, Crew, Task
from crewai.llm import BaseLLM
from crewai.tools import tool

ADDR = ("127.0.0.1", 8799)
BIN = Path(__file__).resolve().parents[1] / "target" / "release" / "soundgate"


class EventLog:
    def __init__(self) -> None:
        self.events: list[str] = []

    def log(self, e: str) -> None:
        self.events.append(e)

    def contains(self, sub: str) -> bool:
        return any(sub in e for e in self.events)


LOG = EventLog()
VERDICTS: dict[str, str] = {}  # tag -> gate verdict for that scenario's effect


# --------------------------- the integration surface ---------------------------
class GateClient:
    """Identical contract to the other five integrations: submit the effect's
    identity, perform (here: log) the effect only on 'release'."""

    def __init__(self, addr=ADDR):
        self.sock = socket.create_connection(addr)
        self.rfile = self.sock.makefile("r")

    def _call(self, req: dict) -> str:
        self.sock.sendall((json.dumps(req) + "\n").encode())
        return json.loads(self.rfile.readline())["verdict"]

    def mediated_effect(self, run: str, key: str, tag: str,
                        needs_approval: bool = False) -> str:
        v = self._call({"op": "submit", "run_id": run, "effect_key": key,
                        "needs_approval": needs_approval})
        VERDICTS[tag] = v
        if v == "release":
            LOG.log(f"{tag}_EFFECT:executed")
        return v

    def cancel(self, run: str) -> str:
        return self._call({"op": "cancel", "run_id": run})


GATE: GateClient  # set in main()


# ------------------ probe-identical scripted LLM (no network) ------------------
class ScriptedLLM(BaseLLM):
    def __init__(self) -> None:
        super().__init__(model="scripted-stub")

    def call(self, messages: Any, tools: Any = None, callbacks: Any = None,
             available_functions: Any = None, from_task: Any = None,
             from_agent: Any = None, response_model: Any = None) -> str:
        already_acted = False
        if isinstance(messages, list):
            for m in messages:
                if (isinstance(m, dict) and m.get("role") == "assistant"
                        and "Action: fire_effect" in str(m.get("content", ""))):
                    already_acted = True
        if already_acted:
            return "Thought: the effect is done.\nFinal Answer: done"
        return ("Thought: I must perform the action.\n"
                "Action: fire_effect\nAction Input: {}")

    def supports_function_calling(self) -> bool:
        return False


def _mediated_effect_tool(run: str, tag: str, delay: float = 0.0):
    """The repair: the crew's effect tool routes through the gate."""
    @tool("fire_effect")
    def fire_effect() -> str:
        """Perform the irreversible side effect (mediated by SoundGate)."""
        if delay:
            time.sleep(delay)  # effect in flight; cancel/timeout fires meanwhile
        v = GATE.mediated_effect(run, "effect", tag)
        return f"effect verdict={v}"

    return fire_effect


def _mk_crew(run: str, tag: str, delay: float = 0.0,
             max_execution_time: int | None = None) -> Crew:
    agent = Agent(
        role="worker", goal="perform the action",
        backstory="a deterministic probe agent",
        llm=ScriptedLLM(), tools=[_mediated_effect_tool(run, tag, delay)],
        verbose=False, max_iter=4, max_execution_time=max_execution_time,
    )
    task = Task(description="perform the action using the fire_effect tool",
                expected_output="the word done", agent=agent)
    return Crew(agents=[agent], tasks=[task], verbose=False)


# ------------------------------- D. cancel fenced -------------------------------
async def _cancel_repaired() -> bool:
    run = "ceD"
    crew = _mk_crew(run, "D", delay=0.8)  # effect is in flight for 0.8s
    task = asyncio.create_task(crew.kickoff_async())
    # wait until the tool has started (llm called) then cancel mid-effect
    for _ in range(200):
        await asyncio.sleep(0.02)
        if LOG.contains("llm:call") or True:  # crew started; cancel window
            break
    await asyncio.sleep(0.3)
    task.cancel()
    cancelled_seen = False
    try:
        await task
    except asyncio.CancelledError:
        cancelled_seen = True
    GATE.cancel(run)                       # the cancellation shim informs the gate
    effect_at_cancel = LOG.contains("D_EFFECT")
    await asyncio.sleep(1.2)               # let the orphan fire against the fence
    effect_after = LOG.contains("D_EFFECT")
    verdict = VERDICTS.get("D")
    ok = cancelled_seen and not effect_at_cancel and not effect_after \
         and verdict == "refused_cancelled"
    print(f"D cancel-orphan fenced    : cancelled_seen={cancelled_seen} "
          f"gate_verdict={verdict} effect_after_cancel={effect_after} -> "
          f"{'FENCED (repaired)' if ok else 'ORPHAN'}")
    return ok


# ------------------------------ E. timeout fenced ------------------------------
def _timeout_repaired() -> bool:
    import threading
    run = "ceE"
    deadline = 1.0
    crew = _mk_crew(run, "E", delay=2.2, max_execution_time=1)  # 2.2s effect
    # The deployment's timeout policy fires the fence AT the deadline, concurrent
    # with the still-in-flight tool -- the same shim/watchdog shape as e2e_ttl.
    # (Firing after kickoff() returns would be too late: CrewAI's
    # max_execution_time blocks the caller past the deadline, note c, so the
    # effect would land first. The fence must be issued when the deadline fires.)
    fence = threading.Timer(deadline, lambda: GATE.cancel(run))
    fence.start()
    t0 = time.time()
    try:
        crew.kickoff()
    except Exception:
        pass                                # native timeout surfaces as an error
    fence.cancel()                          # timer already fired if we're past 1s
    time.sleep(2.5)                         # let the zombie fire against the fence
    landed = LOG.contains("E_EFFECT")
    verdict = VERDICTS.get("E")
    ok = not landed and verdict == "refused_cancelled"
    print(f"E timeout-zombie fenced   : caller_blocked={time.time()-t0:.1f}s "
          f"(deadline={deadline}s) gate_verdict={verdict} effect_landed={landed} -> "
          f"{'FENCED (repaired)' if ok else 'ZOMBIE'}")
    return ok


def main() -> None:
    global GATE
    srv = subprocess.Popen([str(BIN), f"{ADDR[0]}:{ADDR[1]}"],
                           stderr=subprocess.DEVNULL)
    time.sleep(0.4)
    try:
        GATE = GateClient()
        d_ok = asyncio.run(_cancel_repaired())
        e_ok = _timeout_repaired()
        import importlib.metadata as im
        ver = im.version("crewai")
        ok = d_ok and e_ok
        print(f"\nE-E2E FW-E (real crewai=={ver}): "
              f"{'2/2 violated axes fenced in situ' if ok else 'FAILURE'}")
        if not ok:
            raise SystemExit(1)
    finally:
        srv.terminate()


if __name__ == "__main__":
    main()