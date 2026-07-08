"""End-to-end: replay the violation scenarios, but every side effect must be
admitted by the live Rust soundgate over TCP. Shows each previously-confirmed
violation is now blocked, and the G1 counterexample (cross-run key collision)
is fixed. Keyless.

Protocol note: "decide" REQUIRES run_id -- effect identity is
(run_id, effect_key); a key-only decision is ambiguous across concurrent runs
and was the root cause of the G1 counterexample.
"""
import json, os, signal, socket, subprocess, time

ADDR = ("127.0.0.1", 8799)
ADDR_WAL = ("127.0.0.1", 8798)
WAL_PATH = "e2e/e2e_test.wal"

def call(sock_file, sock, req):
    sock.sendall((json.dumps(req) + "\n").encode())
    return json.loads(sock_file.readline())["verdict"]

def connect(addr=ADDR, retries=20):
    last = None
    for _ in range(retries):
        try:
            s = socket.create_connection(addr, timeout=1.0)
            return s, s.makefile("r")
        except OSError as e:
            last = e
            time.sleep(0.1)
    raise last

def main():
    srv = subprocess.Popen(["target/release/soundgate"], stderr=subprocess.DEVNULL)
    time.sleep(0.5)
    try:
        s, f = connect()

        # Scenario 1 -- PARALLEL APPROVAL LEAK + REJECT-AFTER-EFFECT
        # Gate is awaiting approval; sibling effect tries to fire during the pause.
        gate = call(f, s, {"op":"submit","run_id":"r1","effect_key":"gate_email","needs_approval":True})
        sibling = call(f, s, {"op":"submit","run_id":"r1","effect_key":"sibling_email","needs_approval":True})
        # Human REJECTS the run's action:
        d1 = call(f, s, {"op":"decide","run_id":"r1","effect_key":"gate_email","approved":False})
        d2 = call(f, s, {"op":"decide","run_id":"r1","effect_key":"sibling_email","approved":False})
        s1_ok = (gate=="held_for_approval" and sibling=="held_for_approval"
                 and d1=="refused_rejected" and d2=="refused_rejected")
        print(f"S1 parallel-approval + reject : gate={gate} sibling={sibling} "
              f"reject1={d1} reject2={d2} -> {'BLOCKED (fixed)' if s1_ok else 'LEAK'}")

        # Scenario 2 -- RESUME REPLAY DOUBLE-EXECUTION
        first = call(f, s, {"op":"submit","run_id":"r2","effect_key":"charge_card","needs_approval":False})
        replay = call(f, s, {"op":"submit","run_id":"r2","effect_key":"charge_card","needs_approval":False})
        s2_ok = (first=="release" and replay=="refused_duplicate")
        print(f"S2 resume replay              : first={first} replay={replay} "
              f"-> {'BLOCKED (fixed)' if s2_ok else 'DOUBLE-EXEC'}")

        # Scenario 3 -- CANCELLATION / TIMEOUT ZOMBIE
        ack = call(f, s, {"op":"cancel","run_id":"r3"})
        zombie = call(f, s, {"op":"submit","run_id":"r3","effect_key":"post_webhook","needs_approval":False})
        s3_ok = (ack=="ack" and zombie=="refused_cancelled")
        print(f"S3 cancel/timeout zombie      : cancel_ack={ack} zombie_submit={zombie} "
              f"-> {'BLOCKED (fixed)' if s3_ok else 'ORPHAN'}")

        # Scenario 4 -- G1 COUNTEREXAMPLE: CROSS-RUN KEY REUSE
        # r2 already released "charge_card" above. A DIFFERENT run reusing the
        # same key is a different logical effect and must release; its own
        # replay must then dedup. Pre-fix behavior: refused_duplicate here.
        other = call(f, s, {"op":"submit","run_id":"r5","effect_key":"charge_card","needs_approval":False})
        other_replay = call(f, s, {"op":"submit","run_id":"r5","effect_key":"charge_card","needs_approval":False})
        # And a rejection in one run must not bleed into another (r1 rejected
        # "gate_email"; r6 reuses the key):
        no_bleed = call(f, s, {"op":"submit","run_id":"r6","effect_key":"gate_email","needs_approval":False})
        s4_ok = (other=="release" and other_replay=="refused_duplicate" and no_bleed=="release")
        print(f"S4 cross-run key reuse (G1)   : other_run={other} its_replay={other_replay} "
              f"reject_no_bleed={no_bleed} -> {'SCOPED (fixed)' if s4_ok else 'CROSS-RUN COLLISION'}")

        # Contrast -- a normal, approved, unique effect on a live run still flows
        ok = call(f, s, {"op":"submit","run_id":"r4","effect_key":"send_ok","needs_approval":True})
        okd = call(f, s, {"op":"decide","run_id":"r4","effect_key":"send_ok","approved":True})
        c_ok = (ok=="held_for_approval" and okd=="release")
        print(f"C  legitimate approved effect : submit={ok} approve={okd} "
              f"-> {'RELEASED (correct)' if c_ok else 'WRONGLY BLOCKED'}")

        # Scenario 5 -- DURABILITY: fences survive a gate crash (WAL).
        # A second gate runs with a write-ahead log; we release an effect and
        # cancel a run, KILL the process uncleanly, restart it on the same
        # log, and check that the replay fence and the cancellation fence
        # both survived -- while fresh legitimate work still flows.
        if os.path.exists(WAL_PATH):
            os.remove(WAL_PATH)
        srv2 = subprocess.Popen(
            ["target/release/soundgate", f"{ADDR_WAL[0]}:{ADDR_WAL[1]}", WAL_PATH],
            stderr=subprocess.DEVNULL)
        try:
            s2, f2 = connect(ADDR_WAL)
            pre_rel = call(f2, s2, {"op":"submit","run_id":"r7","effect_key":"pay_once","needs_approval":False})
            pre_can = call(f2, s2, {"op":"cancel","run_id":"r8"})
            srv2.send_signal(signal.SIGKILL)  # crash, not shutdown
            srv2.wait()
            srv2 = subprocess.Popen(
                ["target/release/soundgate", f"{ADDR_WAL[0]}:{ADDR_WAL[1]}", WAL_PATH],
                stderr=subprocess.DEVNULL)
            s2, f2 = connect(ADDR_WAL)
            replay = call(f2, s2, {"op":"submit","run_id":"r7","effect_key":"pay_once","needs_approval":False})
            zombie = call(f2, s2, {"op":"submit","run_id":"r8","effect_key":"late_effect","needs_approval":False})
            fresh  = call(f2, s2, {"op":"submit","run_id":"r9","effect_key":"new_work","needs_approval":False})
            s5_ok = (pre_rel=="release" and pre_can=="ack"
                     and replay=="refused_duplicate" and zombie=="refused_cancelled"
                     and fresh=="release")
            print(f"S5 crash + restart (WAL)      : pre={pre_rel}/{pre_can} post_replay={replay} "
                  f"post_zombie={zombie} fresh={fresh} -> {'DURABLE (fences survived)' if s5_ok else 'STATE LOST'}")
        finally:
            srv2.terminate()

        allok = s1_ok and s2_ok and s3_ok and s4_ok and c_ok and s5_ok
        print(f"\nALL SCENARIOS: {'6/6 -- violations blocked/scoped, fences durable, legitimate effects released' if allok else 'FAILURE'}")
        if not allok:
            raise SystemExit(1)
    finally:
        srv.terminate()

if __name__ == "__main__":
    main()