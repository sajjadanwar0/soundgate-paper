from __future__ import annotations

import json
import operator
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Annotated, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

ADDR = ("127.0.0.1", 8797)
BIN = Path(__file__).resolve().parents[1] / "target" / "release" / "soundgate"

EXECUTED: list[str] = []

class GateClient:
    def __init__(self, addr=ADDR):
        self.sock = socket.create_connection(addr)
        self.rfile = self.sock.makefile("r")

    def _call(self, req: dict) -> str:
        self.sock.sendall((json.dumps(req) + "\n").encode())
        return json.loads(self.rfile.readline())["verdict"]

    def mediated_effect(self, run_id: str, effect_key: str, do_effect,
                        needs_approval: bool = False) -> str:
        v = self._call({"op": "submit", "run_id": run_id,
                        "effect_key": effect_key,
                        "needs_approval": needs_approval})
        if v == "release":
            do_effect()
        return v

    def decide(self, run_id: str, effect_key: str, approved: bool) -> str:
        return self._call({"op": "decide", "run_id": run_id,
                           "effect_key": effect_key, "approved": approved})

    def cancel(self, run_id: str) -> str:
        return self._call({"op": "cancel", "run_id": run_id})


class S(TypedDict):
    notes: Annotated[list, operator.add]


def compiled(*nodes, fan_out: bool):
    g = StateGraph(S)
    for name, fn in nodes:
        g.add_node(name, fn)
    if fan_out:
        for name, _ in nodes:
            g.add_edge(START, name)
            g.add_edge(name, END)
    else:
        prev = START
        for name, _ in nodes:
            g.add_edge(prev, name)
            prev = name
        g.add_edge(prev, END)
    return g.compile(checkpointer=InMemorySaver())


def main() -> None:
    srv = subprocess.Popen([str(BIN), f"{ADDR[0]}:{ADDR[1]}"],
                           stderr=subprocess.DEVNULL)
    time.sleep(0.4)

    try:
        gate = GateClient()
        results = []
        run = "lgA"

        def approval_node(state: S) -> S:
            decision = interrupt("approve the run's actions?")
            return {"notes": [f"gate:{decision}"]}

        def sibling_node(state: S) -> S:
            v = gate.mediated_effect(run, "sibling_email",
                                     lambda: EXECUTED.append("sibling_email"),
                                     needs_approval=True)
            return {"notes": [f"sibling:{v}"]}

        g = compiled(("gate", approval_node), ("sibling", sibling_node),
                     fan_out=True)
        cfg = {"configurable": {"thread_id": "tA"}}
        first = g.invoke({"notes": []}, cfg)
        paused = bool(first.get("__interrupt__"))
        during_pause = len(EXECUTED)  # must be 0: sibling held, not executed
        rej = gate.decide(run, "sibling_email", False)
        g.invoke(Command(resume="reject"), cfg)
        a_ok = paused and during_pause == 0 and rej == "refused_rejected" \
               and len(EXECUTED) == 0

        results.append(a_ok)

        print(f"A sibling-leak repaired   : paused={paused} "
              f"effects_during_pause={during_pause} reject={rej} "
              f"effects_total={len(EXECUTED)} -> "
              f"{'HELD+REFUSED (repaired)' if a_ok else 'LEAK'}")

        run = "lgB"
        node_runs = {"n": 0}
        verdicts: list[str] = []

        def charge_then_ask(state: S) -> S:
            node_runs["n"] += 1
            v = gate.mediated_effect(run, "charge_card",
                                     lambda: EXECUTED.append("charge_card"))
            verdicts.append(v)
            decision = interrupt("charged; continue?")  # node WILL re-run
            return {"notes": [f"b:{decision}:{v}"]}

        g = compiled(("charge", charge_then_ask), fan_out=False)
        cfg = {"configurable": {"thread_id": "tB"}}
        g.invoke({"notes": []}, cfg)
        g.invoke(Command(resume="continue"), cfg)
        charges = EXECUTED.count("charge_card")
        b_ok = node_runs["n"] == 2 and charges == 1 \
               and verdicts == ["release", "refused_duplicate"]
        results.append(b_ok)
        print(f"B replay repaired         : node_body_ran={node_runs['n']}x "
              f"verdicts={verdicts} effect_executed={charges}x -> "
              f"{'EXACTLY-ONCE (repaired)' if b_ok else 'DOUBLE-EXEC'}")

        run = "lgC"

        zombie_verdict: list[str] = []

        def spawning_node(state: S) -> S:
            def zombie():
                time.sleep(0.4)
                zombie_verdict.append(
                    gate.mediated_effect(run, "post_webhook",
                                         lambda: EXECUTED.append("post_webhook")))
            threading.Thread(target=zombie, daemon=True).start()
            return {"notes": ["spawned"]}

        g = compiled(("spawn", spawning_node), fan_out=False)
        g.invoke({"notes": []}, {"configurable": {"thread_id": "tC"}})

        time.sleep(0.1)
        gate.cancel(run)
        time.sleep(0.6)  # let the zombie fire against the fence
        c_ok = zombie_verdict == ["refused_cancelled"] \
               and "post_webhook" not in EXECUTED
        results.append(c_ok)

        print(f"C zombie fenced           : zombie_verdict={zombie_verdict} "
              f"effect_executed={'post_webhook' in EXECUTED} -> "
              f"{'FENCED (repaired)' if c_ok else 'ORPHAN'}")

        ok = all(results)
        print(f"\nE-E2E (real langgraph==1.2.7): "
              f"{'3/3 violations repaired in situ' if ok else 'FAILURE'}")

        if not ok:
            raise SystemExit(1)
    finally:
        srv.terminate()


if __name__ == "__main__":
    main()