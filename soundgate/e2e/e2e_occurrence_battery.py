from __future__ import annotations
import json, socket, subprocess, time, threading
from pathlib import Path

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

def model_plan(provider: str, model: str, task_id: str) -> list[str]:
    raise NotImplementedError("wire exposure.providers_native here")

def run_unmediated_fw_a(plan: list[str], pause_s: float) -> bool:
    raise NotImplementedError("adapt e2e_langgraph.py scenario A without the gate")

def run_mediated_fw_a(gate: GateClient, plan: list[str], pause_s: float) -> bool:
    raise NotImplementedError("adapt e2e_langgraph.py scenario A with the gate")

def cell(provider, model, task_id, pause_s, n, gate):
    emitted = leaked = mediated_leak = 0
    for _ in range(n):
        plan = model_plan(provider, model, task_id)
        is_parallel = _has_gated_plus_sibling(plan)
        if is_parallel:
            emitted += 1
            if run_unmediated_fw_a(plan, pause_s): leaked += 1
            if run_mediated_fw_a(gate, plan, pause_s):  mediated_leak += 1
    return dict(provider=provider, model=model, task=task_id, pause_s=pause_s, n=n,
                emitted=emitted, leaked=leaked,
                p_leak=leaked/n, p_leak_given_emit=(leaked/emitted if emitted else None),
                mediated_leak=mediated_leak)


def _has_gated_plus_sibling(plan: list[str]) -> bool:
    raise NotImplementedError("reuse exposure.tasks consequential-tool definitions")

if __name__ == "__main__":
    print("Experiment A is a template. Wire the three NotImplementedError hooks "
          "to exposure.providers_native + the e2e_langgraph scenario, then run "
          "the matrix and report P(leak), P(leak|emit), and mediated_leak per cell.")