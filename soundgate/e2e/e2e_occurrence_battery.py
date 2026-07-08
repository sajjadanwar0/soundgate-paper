"""e2e_occurrence_battery.py -- EXPERIMENT A (reviewer W5/W1).

Converts the proxy ("models emit the leak-triggering plan shape", E-EXPOSURE)
into a MEASURED end-to-end occurrence: real model -> real framework -> real
approval pause -> did a gated sibling effect ACTUALLY execute during the pause?

This is the single highest-leverage experiment. Section 3 already shows,
model-free, that given the plan shape the sibling effect lands during the pause
(structural). E-EXPOSURE shows real models emit that shape at measured rates.
This battery composes the two on live models and reports the end-to-end leak
rate directly, so "occurs in practice" is measured, not argued -- and it is far
stronger occurrence evidence than more issue-tracker mining.

DESIGN (fill provider keys; frameworks already pinned in the repo):
  frameworks : reuse the e2e_* harnesses that already wire each framework to the
               gate (langgraph, llamaindex, msaf, openai_agents, langgraph.js).
               For the UNMEDIATED arm, run the same graph WITHOUT the gate
               wrapper so a real leak can occur; for the MEDIATED arm, route the
               sibling effect through SoundGate (expect 0 leaks).
  models     : the E-EXPOSURE set on NATIVE APIs, pinned with version+date
               (gpt-4o/successor, claude, gemini, deepseek, llama). Reuse
               exposure/src/exposure/providers_native.py.
  tasks      : the 10 authored tasks + >=3 naturalistic multi-turn tasks
               (answers the "authored tasks" critique). Each: one gated tool +
               >=2 benign siblings.
  pause      : REALISTIC approval latency. Sweep a fixed set {1s, 10s, 60s} (and
               optionally sample 5s-5min) during which the sibling branch runs.
  N          : >=100 runs per (framework, model, task, pause) for the unmediated
               arm; Wilson intervals as in E-EXPOSURE.

MEASURE, per cell:
  emitted        : model placed the gated call in parallel with >=1 sibling
                   (the E-EXPOSURE event) -- the precondition.
  leaked         : a gated sibling effect reached its COMMIT POINT during the
                   pause (the actual hazard) -- instrument the effect log's
                   append timestamp vs the pause window, exactly as the probes do.
  P(leak)        : unconditional end-to-end leak rate = leaked / N.
  P(leak|emit)   : conditional -- should be ~1 per Section 3's structural claim;
                   MEASURE it, do not assume it.
  mediated_leak  : same cell through SoundGate -- expect 0/N (the repair).

SUCCESS CRITERION (what satisfies a brutal reviewer):
  a non-trivial P(leak) on >=2 frameworks with >=2 CURRENT models at a realistic
  pause (>=10s), with P(leak|emit) ~1 confirming the structural composition, and
  mediated_leak = 0 across all cells.

HONEST RISK -- READ BEFORE RUNNING:
  If P(leak|emit) turns out < 1 on some framework (e.g. the runtime happens to
  schedule the sibling AFTER the pause resolves for a given task), that is a
  REAL finding you must report -- it would mean the leak is task/schedule
  sensitive, not universal, and it weakens "occurs in practice" for that cell.
  The model-free probes argue it is structural; this experiment tests that
  argument on live models. Report whatever it shows. Do not drop cells that
  don't leak.

The skeleton below is intentionally partial: it wires ONE framework (FW-A) and
ONE model provider as a worked template. Extend to the matrix. It reuses the
gate client + effect-log instrumentation shape from e2e_langgraph.py and the
provider from the exposure package.
"""
from __future__ import annotations
import json, socket, subprocess, time, threading
from pathlib import Path

# --- reuse the existing gate client shape (see e2e_langgraph.py) -------------
ADDR = ("127.0.0.1", 8797)
BIN = Path(__file__).resolve().parents[1] / "target" / "release" / "soundgate"


class GateClient:
    def __init__(self, addr=ADDR):
        self.sock = socket.create_connection(addr); self.rfile = self.sock.makefile("r")
    def _c(self, req):
        self.sock.sendall((json.dumps(req)+"\n").encode()); return json.loads(self.rfile.readline())["verdict"]
    def mediated_effect(self, run, key, do, needs_approval=False):
        v = self._c({"op":"submit","run_id":run,"effect_key":key,"needs_approval":needs_approval})
        if v == "release": do()
        return v
    def decide(self, run, key, ap): return self._c({"op":"decide","run_id":run,"effect_key":key,"approved":ap})
    def cancel(self, run): return self._c({"op":"cancel","run_id":run})


# --- what you must supply ----------------------------------------------------
# 1) a model call that returns the assistant turn's tool calls for a task, using
#    exposure/src/exposure/providers_native.py (pinned model + date). This is
#    the SAME emission measurement E-EXPOSURE already does; here you feed its
#    output into the framework.
def model_plan(provider: str, model: str, task_id: str) -> list[str]:
    """Return the tool names the model emits in the consequential turn.
    Reuse exposure.providers_native; record (provider, model, version, date)."""
    raise NotImplementedError("wire exposure.providers_native here")

# 2) a real framework run (UNMEDIATED arm) that executes the emitted plan with a
#    genuine approval pause, and records whether a gated sibling effect committed
#    DURING the pause. Reuse the FW-A graph shape from e2e_langgraph.py but WITHOUT
#    routing the sibling through the gate, so a real leak can occur.
def run_unmediated_fw_a(plan: list[str], pause_s: float) -> bool:
    """True iff a gated sibling effect committed during the approval pause."""
    raise NotImplementedError("adapt e2e_langgraph.py scenario A without the gate")

# 3) the MEDIATED arm: identical, but the sibling effect goes through the gate.
def run_mediated_fw_a(gate: GateClient, plan: list[str], pause_s: float) -> bool:
    """True iff any gated sibling effect leaked (expected: always False)."""
    raise NotImplementedError("adapt e2e_langgraph.py scenario A with the gate")


def cell(provider, model, task_id, pause_s, n, gate):
    emitted = leaked = mediated_leak = 0
    for _ in range(n):
        plan = model_plan(provider, model, task_id)
        is_parallel = _has_gated_plus_sibling(plan)      # the E-EXPOSURE predicate
        if is_parallel:
            emitted += 1
            if run_unmediated_fw_a(plan, pause_s): leaked += 1
            if run_mediated_fw_a(gate, plan, pause_s):  mediated_leak += 1
    return dict(provider=provider, model=model, task=task_id, pause_s=pause_s, n=n,
                emitted=emitted, leaked=leaked,
                p_leak=leaked/n, p_leak_given_emit=(leaked/emitted if emitted else None),
                mediated_leak=mediated_leak)


def _has_gated_plus_sibling(plan: list[str]) -> bool:
    # define the gated tool per task (as in exposure/tasks.py) and check it shares
    # the turn with >=1 benign sibling.
    raise NotImplementedError("reuse exposure.tasks consequential-tool definitions")


if __name__ == "__main__":
    # Template loop; expand to the full (framework x model x task x pause) matrix
    # and write JSONL results + a Wilson-interval table mirroring E-EXPOSURE.
    print("Experiment A is a template. Wire the three NotImplementedError hooks "
          "to exposure.providers_native + the e2e_langgraph scenario, then run "
          "the matrix and report P(leak), P(leak|emit), and mediated_leak per cell.")