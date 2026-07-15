from __future__ import annotations

import json
import socket
import subprocess
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Annotated, TypedDict
import operator

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import interrupt, Command

HERE = Path(__file__).resolve()
GATE_BIN = HERE.parents[1] / "target" / "release" / "soundgate"
GATE_ADDR = ("127.0.0.1", 8815)
HOOK_ADDR = ("127.0.0.1", 8816)
HOOK_URL = f"http://{HOOK_ADDR[0]}:{HOOK_ADDR[1]}/charge"
LEDGER = HERE.parent / "webhook_ledger.txt"

HITS: list[dict] = []


class _Hook(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(n).decode("utf-8", "replace") if n else ""
        HITS.append({"t": time.time(), "body": body})
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"ok":true}')


def start_hook() -> HTTPServer:
    srv = HTTPServer(HOOK_ADDR, _Hook)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def do_real_effect(label: str) -> None:
    LEDGER.write_text((LEDGER.read_text() if LEDGER.exists() else "")
                      + f"{time.time():.6f} {label}\n")
    req = urllib.request.Request(HOOK_URL, data=json.dumps({"effect": label}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    urllib.request.urlopen(req, timeout=3).read()

class GateClient:
    def __init__(self, addr=GATE_ADDR):
        self.s = socket.create_connection(addr, timeout=5)
        self.r = self.s.makefile("r")
        self.lock = threading.Lock()

    def _c(self, req):
        with self.lock:
            self.s.sendall((json.dumps(req) + "\n").encode())
            return json.loads(self.r.readline())["verdict"]

    def submit(self, run, key, do, approval):
        v = self._c({"op": "submit", "run_id": run, "effect_key": key, "needs_approval": approval})
        if v == "release":
            do()
        return v

    def decide(self, run, key, ok):
        return self._c({"op": "decide", "run_id": run, "effect_key": key, "approved": ok})

class St(TypedDict):
    notes: Annotated[list, operator.add]


def build_graph(effect_node, approval_node):
    g = StateGraph(St)
    g.add_node("approval", approval_node)
    g.add_node("effect", effect_node)
    g.add_edge(START, "approval")
    g.add_edge(START, "effect")
    g.add_edge("approval", END)
    g.add_edge("effect", END)

    return g.compile(checkpointer=InMemorySaver())

def run_unmediated() -> dict:
    HITS.clear()
    if LEDGER.exists():
        LEDGER.unlink()

    def approval_node(state: St) -> St:
        interrupt("Approve charge_card?")
        return {"notes": ["gate:resumed"]}

    def effect_node(state: St) -> St:
        do_real_effect("charge_card:unmediated")
        return {"notes": ["effect:posted"]}

    g = build_graph(effect_node, approval_node)
    cfg = {"configurable": {"thread_id": "hook-unmed"}}
    t0 = time.time()
    first = g.invoke({"notes": []}, cfg)
    t_pause = time.time()
    paused = bool(first.get("__interrupt__"))
    hits_during_pause = len(HITS)
    time.sleep(0.5)
    g.invoke(Command(resume="reject"), cfg)
    t_reject = time.time()
    hit_t = HITS[0]["t"] if HITS else None

    return {"arm": "unmediated", "paused": paused, "posts_total": len(HITS),
            "posts_during_pause": hits_during_pause,
            "post_before_reject": (hit_t is not None and hit_t < t_reject),
            "t_invoke": t0, "t_pause": t_pause, "t_post": hit_t, "t_reject": t_reject}

def run_mediated(gate: GateClient) -> dict:
    HITS.clear()
    if LEDGER.exists():
        LEDGER.unlink()

    def approval_node(state: St) -> St:
        interrupt("Approve charge_card?")
        return {"notes": ["gate:resumed"]}

    def effect_node(state: St) -> St:
        v = gate.submit("hook-med", "charge_card", lambda: do_real_effect("charge_card:mediated"),
                        approval=True)
        return {"notes": [f"effect:{v}"]}

    g = build_graph(effect_node, approval_node)
    cfg = {"configurable": {"thread_id": "hook-med"}}
    hits_during_pause = len(HITS)
    time.sleep(0.5)
    verdict = gate.decide("hook-med", "charge_card", False)
    g.invoke(Command(resume="reject"), cfg)

    return {"arm": "mediated", "posts_total": len(HITS),
            "posts_during_pause": hits_during_pause, "gate_verdict_after_reject": verdict}

def main() -> int:
    hook = start_hook()
    srv = subprocess.Popen([str(GATE_BIN), f"{GATE_ADDR[0]}:{GATE_ADDR[1]}"],
                           stderr=subprocess.DEVNULL)
    time.sleep(0.5)
    try:
        um = run_unmediated()
        gate = GateClient()
        md = run_mediated(gate)
    finally:
        srv.terminate()
        hook.shutdown()

    print("=" * 74)
    print("WEBHOOK LEAK DEMO -- real HTTP POST to a live endpoint (LangGraph)")
    print("  graph = documented parallel fan-out + documented interrupt HITL;")
    print("  the only addition is a tool with a real external effect (HTTP POST).")
    print("-" * 74)
    dp = (um["t_post"] - um["t_pause"]) if um["t_post"] else None
    rp = (um["t_reject"] - um["t_post"]) if um["t_post"] else None
    print("UNMEDIATED (no gate):")
    print(f"  run paused for approval ......... {um['paused']}")
    print(f"  POSTs that reached the endpoint . {um['posts_total']}")
    print(f"  ...of those, during the pause ... {um['posts_during_pause']}")
    if um["t_post"]:
        when = (f"in the same superstep as the interrupt (concurrent, within "
                f"{abs(dp)*1000:.0f} ms of the pause)" if dp <= 0
                else f"{dp*1000:.0f} ms into the approval pause")
        print(f"  POST reached the endpoint {when},")
        print(f"    {rp*1000:.0f} ms BEFORE the human reject")
    print(f"  effect committed before reject .. {um['post_before_reject']}")
    print("MEDIATED (through SoundGate):")
    print(f"  POSTs that reached the endpoint . {md['posts_total']}")
    print(f"  gate verdict after reject ....... {md['gate_verdict_after_reject']}")
    print("-" * 74)
    ok = (um["paused"] and um["posts_during_pause"] >= 1 and um["post_before_reject"]
          and md["posts_total"] == 0 and md["gate_verdict_after_reject"] == "refused_rejected")
    print("VERDICT:", "PASS -- unmediated effect hit a real endpoint during the pause,"
                      " before reject; SoundGate delivered zero POSTs." if ok else "FAIL -- see timeline.")
    print(json.dumps({"unmediated": um, "mediated": md}, default=str))
    return 0 if ok else 1

if __name__ == "__main__":
    raise SystemExit(main())