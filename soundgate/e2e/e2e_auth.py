import hashlib, hmac, json, os, socket, subprocess, time
from pathlib import Path

BIN = Path(__file__).resolve().parents[1] / "target" / "release" / "soundgate"
SECRET = b"correct-horse-battery-staple"
ADDR = ("127.0.0.1", 8810)

def tag(run, key, approved):
    msg = f"{run}\n{key}\n{'1' if approved else '0'}".encode()
    return hmac.new(SECRET, msg, hashlib.sha256).hexdigest()

def call(sock, rf, req):
    sock.sendall((json.dumps(req) + "\n").encode())
    return json.loads(rf.readline())

def main():
    env = dict(os.environ, SOUNDGATE_DECISION_SECRET=SECRET.decode())
    srv = subprocess.Popen([str(BIN), f"{ADDR[0]}:{ADDR[1]}"],
                           env=env, stderr=subprocess.PIPE, text=True)
    time.sleep(0.5)
    s = socket.create_connection(ADDR, timeout=5); rf = s.makefile("r")
    run, key = "pay-run", "refund"
    results = {}

    v = call(s, rf, {"op": "submit", "run_id": run, "effect_key": key,
                     "needs_approval": True})
    results["held"] = v["verdict"]

    v = call(s, rf, {"op": "decide", "run_id": run, "effect_key": key,
                     "approved": True})
    results["forged_no_mac"] = ((v.get("verdict","") + " " + v.get("message","")).strip())[:40]

    v = call(s, rf, {"op": "decide", "run_id": run, "effect_key": key,
                     "approved": True, "mac": "00" * 32})
    results["forged_bad_mac"] = ((v.get("verdict","") + " " + v.get("message","")).strip())[:40]

    v = call(s, rf, {"op": "decide", "run_id": run, "effect_key": key,
                     "approved": False, "mac": "de" * 32})
    results["forged_reject"] = ((v.get("verdict","") + " " + v.get("message","")).strip())[:40]

    v = call(s, rf, {"op": "submit", "run_id": run, "effect_key": key,
                     "needs_approval": True})
    results["still_held_after_forgeries"] = v["verdict"]

    v = call(s, rf, {"op": "decide", "run_id": run, "effect_key": key,
                     "approved": True, "mac": tag(run, key, True)})
    results["legit_approve"] = v["verdict"]

    srv.terminate()
    out = srv.stderr.read()
    auth_on = "decision authenticity ENABLED" in out

    print(f"server: {'decision authenticity ENABLED' if auth_on else 'AUTH OFF (unexpected)'}\n")
    print(f"  held effect                     : {results['held']}")
    print(f"  forged approve (no mac)         : {results['forged_no_mac']}")
    print(f"  forged approve (bad mac)        : {results['forged_bad_mac']}")
    print(f"  forged reject  (bad mac)        : {results['forged_reject']}")
    print(f"  still held after 3 forgeries    : {results['still_held_after_forgeries']}")
    print(f"  legitimate approve (valid mac)  : {results['legit_approve']}")

    ok = (auth_on
          and results["held"] == "held_for_approval"
          and "unauthenticated" in results["forged_no_mac"]
          and "unauthenticated" in results["forged_bad_mac"]
          and "unauthenticated" in results["forged_reject"]
          and results["still_held_after_forgeries"] == "held_for_approval"
          and results["legit_approve"] == "release")
    print(f"\nE-AUTH: forged decisions refused; effect held through every forgery; "
          f"only the secret-holder released it -> "
          f"{'decision channel authenticated' if ok else 'UNEXPECTED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())