#!/usr/bin/env python3
"""mock_cluster.py -- a MOCK soundgate raft node for HARNESS SELF-TEST ONLY.

Launched per node by start_soundgate_cluster.sh when MOCK_BIN is set, under the
SAME env contract as the real binary (SOUNDGATE_RAFT_NODE_ID / _HTTP / _EFFECT
/ _DATA). It imitates just enough behavior -- leadership by lowest live id,
quorum >= 2, shared released/held state, catch-up lag, the line-JSON effect
protocol and the admin/metrics HTTP surface -- to exercise every code path of
faultinject_raft.sh (kill, SIGSTOP/SIGCONT, data-dir deletion, quorum loss).

A green run against this mock validates the ORCHESTRATION AND ASSERTION LOGIC
of the fault harness. It says nothing about soundgate itself; real receipts
come from the real binary.
"""
import fcntl, json, os, pathlib, socketserver, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

NODE = int(os.environ["SOUNDGATE_RAFT_NODE_ID"])
HTTP_HOST, HTTP_PORT = os.environ["SOUNDGATE_RAFT_HTTP"].rsplit(":", 1)
EFF_HOST, EFF_PORT = os.environ["SOUNDGATE_RAFT_EFFECT"].rsplit(":", 1)
DATA = pathlib.Path(os.environ.get("SOUNDGATE_RAFT_DATA", f"./raft-data-{NODE}"))
SHARED = pathlib.Path("./mock-raft-shared")
SHARED.mkdir(exist_ok=True)
DATA.mkdir(parents=True, exist_ok=True)
STATE = SHARED / "state.json"
LOCK = SHARED / "lock"
HB = SHARED / f"hb-{NODE}"
APPLIED = DATA / "applied.txt"
HB_STALE = 0.8


def locked(fn):
    with open(LOCK, "a+") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            st = json.loads(STATE.read_text()) if STATE.exists() else {
                "initialized": False, "members": [], "log_index": 0,
                "held": [], "released": [], "rejected": [], "cancelled": []}
            out = fn(st)
            STATE.write_text(json.dumps(st))
            return out
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def alive_ids():
    now, out = time.time(), []
    for i in range(3):
        p = SHARED / f"hb-{i}"
        if p.exists() and now - p.stat().st_mtime < HB_STALE:
            out.append(i)
    return out


def leader():
    a = alive_ids()
    return (min(a) if len(a) >= 2 else None), a


def my_applied():
    try:
        return int(APPLIED.read_text())
    except Exception:
        return 0


def apply_op(st, op):
    ident = (op["run_id"], op["effect_key"]) if "effect_key" in op else None
    key = list(ident) if ident else None
    if op["op"] == "submit":
        if key in st["released"] or key in st["rejected"]:
            return {"verdict": "refused_duplicate"}
        if op["run_id"] in st["cancelled"]:
            return {"verdict": "refused_cancelled"}
        if op.get("needs_approval"):
            if key not in st["held"]:
                st["held"].append(key); st["log_index"] += 1
            return {"verdict": "held_for_approval"}
        st["released"].append(key); st["log_index"] += 1
        return {"verdict": "release"}
    if op["op"] == "decide":
        if key in st["released"] or key in st["rejected"]:
            return {"verdict": "refused_duplicate"}
        if key in st["held"]:
            st["held"].remove(key); st["log_index"] += 1
            if op["approved"]:
                st["released"].append(key)
                return {"verdict": "release"}
            st["rejected"].append(key)
            return {"verdict": "refused_rejected"}
        return {"verdict": "error", "message": "decide for unknown hold"}
    if op["op"] == "cancel":
        st["cancelled"].append(op["run_id"]); st["log_index"] += 1
        return {"verdict": "ack"}
    return {"verdict": "error", "message": "bad op"}


class Effect(socketserver.StreamRequestHandler):
    def handle(self):
        for raw in self.rfile:
            line = raw.decode().strip()
            if not line:
                continue
            try:
                op = json.loads(line)
                if op.get("op") == "ping":
                    resp = {"verdict": "pong"}
                else:
                    lid, _ = leader()
                    if lid is None:
                        resp = {"verdict": "error", "message": "no quorum / no leader"}
                    elif lid != NODE:
                        resp = {"verdict": "error", "message": f"forward to leader {lid}"}
                    else:
                        resp = locked(lambda st: apply_op(st, op))
            except Exception as e:  # noqa: BLE001
                resp = {"verdict": "error", "message": f"bad request: {e}"}
            self.wfile.write((json.dumps(resp) + "\n").encode())


class Admin(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silence
        pass

    def _json(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        lid, _ = leader()
        if self.path == "/leader":
            self._json(200, {"leader": lid, "node_id": NODE})
        elif self.path == "/metrics":
            st = locked(lambda s: dict(s))
            self._json(200, {"current_leader": lid,
                             "last_log_index": st["log_index"],
                             "last_applied": {"index": my_applied()}})
        else:
            self._json(404, {"error": "nope"})

    def do_POST(self):
        n = int(self.headers.get("content-length") or 0)
        _ = self.rfile.read(n)
        if self.path == "/admin/init":
            def init(st):
                if st["initialized"]:
                    return False
                st["initialized"] = True
                st["members"] = [NODE]
                return True
            ok = locked(init)
            self._json(200 if ok else 409,
                       {"status": "initialized"} if ok else {"error": "already"})
        elif self.path in ("/admin/add-learner", "/admin/change-membership"):
            self._json(200, {"status": "ok"})
        else:
            self._json(404, {"error": "nope"})


def background():
    while True:
        HB.touch()
        st = locked(lambda s: dict(s))
        cur = my_applied()
        if cur < st["log_index"]:
            APPLIED.write_text(str(cur + 1))  # gradual catch-up, ~20 idx/s
        time.sleep(0.05)


class EffectServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    threading.Thread(target=background, daemon=True).start()
    eff = EffectServer((EFF_HOST, int(EFF_PORT)), Effect)
    threading.Thread(target=eff.serve_forever, daemon=True).start()
    httpd = ThreadingHTTPServer((HTTP_HOST, int(HTTP_PORT)), Admin)
    httpd.allow_reuse_address = True
    httpd.serve_forever()
