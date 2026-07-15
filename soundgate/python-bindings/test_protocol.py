import json, socket, threading, hashlib, hmac as _hmac
from soundgate_client import GateClient, decision_tag

class Core:
    def __init__(self):
        self.released=set(); self.cancelled=set(); self.pending={}; self.rejected=set(); self.closed=set()
    def submit(self, run, key, needs):
        if run in self.cancelled or run in self.closed: return "refused_cancelled"
        i=(run,key)
        if i in self.released: return "refused_duplicate"
        if i in self.rejected: return "refused_rejected"
        if i in self.pending:  return "held_for_approval"
        if needs: self.pending[i]=True; return "held_for_approval"
        self.released.add(i); return "release"
    def decide(self, run, key, approved):
        i=(run,key)
        if i not in self.pending:
            if run in self.cancelled or run in self.closed: return "refused_cancelled"
            if i in self.released: return "refused_duplicate"
            if i in self.rejected: return "refused_rejected"
            return "refused_duplicate"
        del self.pending[i]
        if approved: self.released.add(i); return "release"
        self.rejected.add(i); return "refused_rejected"
    def cancel(self, run): self.cancelled.add(run); return "ack"

def serve(conn, core, secret):
    rf=conn.makefile("r")
    for line in rf:
        line=line.strip()
        if not line: continue
        req=json.loads(line); op=req.get("op")
        if op=="ping": reply={"verdict":"pong"}
        elif op=="submit":
            reply={"verdict":core.submit(req["run_id"],req["effect_key"],req.get("needs_approval",False))}
        elif op=="decide":
            if secret is not None:
                exp=decision_tag(secret,req["run_id"],req["effect_key"],req["approved"])
                if not _hmac.compare_digest(exp, req.get("mac","")):
                    conn.sendall((json.dumps({"verdict":"error","message":"bad mac"})+"\n").encode()); continue
            reply={"verdict":core.decide(req["run_id"],req["effect_key"],req["approved"])}
        elif op=="cancel": reply={"verdict":core.cancel(req["run_id"])}
        else: reply={"verdict":"error","message":"unknown op"}
        conn.sendall((json.dumps(reply)+"\n").encode())

def run_gate(secret=None):
    srv=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    srv.bind(("127.0.0.1",0)); srv.listen(1); port=srv.getsockname()[1]
    core=Core()
    def loop():
        conn,_=srv.accept(); serve(conn,core,secret)
    threading.Thread(target=loop,daemon=True).start()
    return port

def check(name, got, want):
    ok = (got==want)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {got!r}" + ("" if ok else f"  (expected {want!r})"))
    assert ok, name

print("=== Protocol + property behaviour (no-secret gate) ===")
port=run_gate(); g=GateClient(("127.0.0.1",port))
check("ping -> pong", g.ping().kind, "pong")
# P1 hold-until-decided
check("P1 submit(needs_approval) -> held", g.submit("r1","email",True).kind, "held_for_approval")
v=g.decide("r1","email",True); check("P1 approve -> release", v.kind, "release"); check("  .released flag", v.released, True)
# P3 dedup-on-replay
check("P3 resubmit released -> duplicate", g.submit("r1","email",True).kind, "refused_duplicate")
check("P3 no-approval submit -> release", g.submit("r1","deploy",False).kind, "release")
check("P3 resubmit -> duplicate", g.submit("r1","deploy",False).kind, "refused_duplicate")
# P2 reject stickiness
check("P2 submit -> held", g.submit("r1","refund",True).kind, "held_for_approval")
check("P2 reject -> refused_rejected", g.decide("r1","refund",False).kind, "refused_rejected")
check("P2 resubmit rejected -> sticky", g.submit("r1","refund",True).kind, "refused_rejected")
# P4 fence-on-cancel
check("P4 cancel -> ack", g.cancel("r2").kind, "ack")
check("P4 submit into cancelled -> refused_cancelled", g.submit("r2","charge",True).kind, "refused_cancelled")
# cross-run key reuse is independent (the G1 counterexample)
check("cross-run key reuse independent", g.submit("r3","email",False).kind, "release")
g.close()

print("=== HMAC-authenticated decisions ===")
SECRET=b"s3cr3t-key"
port=run_gate(SECRET); g=GateClient(("127.0.0.1",port), secret=SECRET)
check("auth submit -> held", g.submit("rA","wire",True).kind, "held_for_approval")
check("auth approve (valid mac) -> release", g.decide("rA","wire",True).kind, "release")

port2=run_gate(SECRET); bad=GateClient(("127.0.0.1",port2), secret=b"wrong-secret")
bad.submit("rB","wire",True)

try:
    bad.decide("rB","wire",True); print("  [FAIL] forged mac accepted!"); raise SystemExit(1)
except Exception as e:
    print(f"  [PASS] forged mac rejected by gate: {type(e).__name__}")

print("=== decision_tag format matches Rust (msg = run\\nkey\\n{1|0}, sha256 hex) ===")
manual = _hmac.new(SECRET, b"rA\nwire\n1", hashlib.sha256).hexdigest()
check("decision_tag == manual HMAC", decision_tag(SECRET,"rA","wire",True), manual)
check("approved=False uses '0'", decision_tag(SECRET,"rA","wire",False),
      _hmac.new(SECRET, b"rA\nwire\n0", hashlib.sha256).hexdigest())
check("tag is 64 lowercase hex chars", len(decision_tag(SECRET,"x","y",True))==64 and decision_tag(SECRET,"x","y",True).islower(), True)

print("\nALL PROTOCOL + HMAC CHECKS PASSED")