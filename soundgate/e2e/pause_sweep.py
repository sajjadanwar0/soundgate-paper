import argparse
import json
import socket
import sys
import time
from typing import Annotated, TypedDict
import operator
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import interrupt, Command

EFFECTS = []


class St(TypedDict):
    notes: Annotated[list, operator.add]


class GateClient:
    def __init__(self, host, port):
        self.host, self.port = host, port

    def _rpc(self, obj):
        with socket.create_connection((self.host, self.port), timeout=5) as s:
            s.sendall((json.dumps(obj) + "\n").encode())
            buf = b""
            while not buf.endswith(b"\n"):
                chunk = s.recv(65536)
                if not chunk:
                    raise ConnectionError("gate closed")
                buf += chunk
            return json.loads(buf.decode())

    def submit(self, run, key, needs_approval=True):
        return self._rpc({"op": "submit", "run_id": run, "effect_key": key,
                          "needs_approval": needs_approval})["verdict"]

    def decide(self, run, key, approved):
        return self._rpc({"op": "decide", "run_id": run, "effect_key": key,
                          "approved": approved})["verdict"]


def _build(effect_node, approval_node):
    g = StateGraph(St)
    g.add_node("approval", approval_node)
    g.add_node("effect", effect_node)
    g.add_edge(START, "approval")
    g.add_edge(START, "effect")
    g.add_edge("approval", END)
    g.add_edge("effect", END)

    return g.compile(checkpointer=InMemorySaver())

def run_unmediated(pause_s: float, tid: str):
    EFFECTS.clear()

    def approval_node(state: St) -> St:
        d = interrupt("approve action?")
        return {"notes": [f"gate:{d}"]}

    def effect_node(state: St) -> St:
        EFFECTS.append("effect")
        return {"notes": ["effect:done"]}

    g = _build(effect_node, approval_node)
    cfg = {"configurable": {"thread_id": f"sweep-unmed-{tid}"}}
    first = g.invoke({"notes": []}, cfg)
    paused = bool(first.get("__interrupt__"))
    during_pause = len(EFFECTS) > 0
    time.sleep(pause_s)
    g.invoke(Command(resume="reject"), cfg)
    after = len(EFFECTS) > 0

    return paused, during_pause, after


def run_mediated(gate: GateClient, pause_s: float, tid: str):
    EFFECTS.clear()
    run = f"sweep-med-{tid}"

    def approval_node(state: St) -> St:
        d = interrupt("approve action?")
        return {"notes": [f"gate:{d}"]}

    def effect_node(state: St) -> St:
        v = gate.submit(run, "effect", needs_approval=True)
        if v == "release":
            EFFECTS.append("effect")
        return {"notes": [f"effect:{v}"]}

    g = _build(effect_node, approval_node)
    cfg = {"configurable": {"thread_id": f"sweep-med-{tid}"}}
    first = g.invoke({"notes": []}, cfg)
    paused = bool(first.get("__interrupt__"))
    during_pause = len(EFFECTS) > 0          # 0: held at the gate
    time.sleep(pause_s)
    gate.decide(run, "effect", False)          # human rejects
    g.invoke(Command(resume="reject"), cfg)
    after = len(EFFECTS) > 0
    return paused, during_pause, after


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate", default="127.0.0.1:8799")
    ap.add_argument("--pauses", default="0,0.1,0.5,1.0,2.0")
    ap.add_argument("--reps", type=int, default=20)
    args = ap.parse_args()

    host, port = args.gate.split(":")
    gate = GateClient(host, int(port))
    pauses = [float(x) for x in args.pauses.split(",")]

    print("=" * 72)
    print("FW-A (LangGraph) approval-pause sweep -- sibling leak vs pause duration")
    try:
        import langgraph.version as v
        ver = getattr(v, "__version__", "?")
    except Exception:
        ver = "?"
    print(f"langgraph {ver}   reps/pause: {args.reps}   gate: {args.gate}")
    print("-" * 72)
    print("%-8s | %-28s | %-28s" % ("pause(s)", "UNMEDIATED", "MEDIATED (SoundGate)"))
    print("%-8s | %-28s | %-28s" % ("", "leak@pause  after-reject", "leak@pause  after-reject"))
    print("-" * 72)

    failures = []
    rows = []

    for p in pauses:
        u_dur = u_aft = m_dur = m_aft = 0
        for i in range(args.reps):
            paused, dur, aft = run_unmediated(p, f"{p}-{i}")
            if not paused:
                failures.append((p, i, "unmediated run did not pause"))
            u_dur += dur
            u_aft += aft
            paused, dur, aft = run_mediated(gate, p, f"{p}-{i}")
            if not paused:
                failures.append((p, i, "mediated run did not pause"))
            m_dur += dur
            m_aft += aft
        rows.append((p, u_dur, u_aft, m_dur, m_aft))
        print("%-8s | %2d/%-2d leaked  %2d/%-2d effect | %2d/%-2d leaked  %2d/%-2d effect"
              % (p, u_dur, args.reps, u_aft, args.reps,
                 m_dur, args.reps, m_aft, args.reps))
        # oracles
        if u_dur != args.reps:
            failures.append((p, "-", f"unmediated leak not pause-invariant: {u_dur}/{args.reps}"))
        if m_dur != 0:
            failures.append((p, "-", f"mediated leaked during pause: {m_dur}/{args.reps}"))
        if m_aft != 0:
            failures.append((p, "-", f"mediated effect survived rejection: {m_aft}/{args.reps}"))

    print("-" * 72)
    print("Reading: the unmediated leak count is INVARIANT to pause duration -- the")
    print("effect lands in the fan-out superstep before invoke() returns, so no human")
    print("reaction time closes it. Every mediated cell is zero at every pause.")

    if failures:
        print("\nFAILURES:")
        for f in failures[:40]:
            print("  ", f)
        print("\nVERDICT: FAIL")
        return 1
    print("\nVERDICT: PASS -- leak is pause-invariant unmediated; zero under the gate")
    print("at every pause value; rejection yields zero effects throughout.")
    return 0


if __name__ == "__main__":
    sys.exit(main())