"""E-E2E-TTL: bounded-hold policy as a client-side watchdog (keyless).

R2's liveness objection: a held effect can starve if the approver never
answers. Sec. 5.4's answer: no new mechanism is needed -- a hold is resolved
by an ordinary authenticated Decide, so a decide-by-deadline policy is a
watchdog that issues Decide(approved=false) when a configured TTL expires,
converting silent starvation into a visible, bounded rejection. This script
executes exactly that against the live gate WITH the HMAC decision channel
enabled, so the watchdog is an authenticated principal, not a backdoor.

Asserted sequence:
  1. An approval-gated effect submits -> held_for_approval; nothing executes.
  2. No approver responds. After TTL=0.5 s the watchdog fires an
     HMAC-authenticated Decide(approved=false) -> refused_rejected.
  3. The rejection is STICKY (P2): the effect's resubmission refuses, and a
     late human APPROVAL (valid MAC, arriving after the TTL) also refuses --
     the deadline decision is final, exactly like any other rejection.
  4. An unauthenticated late approval is refused_unauthenticated: the
     watchdog path does not weaken the decision channel.
  5. Control: a fresh gated effect approved BEFORE its TTL releases normally
     -- the watchdog only converts expiry, it does not blanket-reject.

Run:  cargo build --release && python3 e2e/e2e_ttl.py
"""
import hashlib
import hmac as pyhmac
import json
import os
import socket
import subprocess
import threading
import time
from pathlib import Path

ADDR = ("127.0.0.1", 8810)
BIN = Path(__file__).resolve().parents[1] / "target" / "release" / "soundgate"
SECRET = b"ttl-demo-secret"
TTL_S = 0.5

EXECUTED = []


def tag(run_id: str, key: str, approved: bool) -> str:
    msg = f"{run_id}\n{key}\n{'1' if approved else '0'}".encode()
    return pyhmac.new(SECRET, msg, hashlib.sha256).hexdigest()


class GateClient:
    def __init__(self, addr=ADDR):
        self.sock = socket.create_connection(addr, timeout=5.0)
        self.rf = self.sock.makefile("r")
        self.lock = threading.Lock()

    def _call(self, req: dict) -> str:
        with self.lock:
            self.sock.sendall((json.dumps(req) + "\n").encode())
            r = json.loads(self.rf.readline())
            self.last = r
            return r["verdict"]

    def submit(self, run_id, key, needs_approval=True):
        v = self._call({"op": "submit", "run_id": run_id, "effect_key": key,
                        "needs_approval": needs_approval})
        if v == "release":
            EXECUTED.append((run_id, key))
        return v

    def decide(self, run_id, key, approved, mac=None):
        req = {"op": "decide", "run_id": run_id, "effect_key": key,
               "approved": approved}
        if mac is not None:
            req["mac"] = mac
        return self._call(req)


class TtlWatchdog:
    """~15-line policy layer: pending identities auto-reject after TTL."""

    def __init__(self, gate: GateClient, ttl_s: float):
        self.gate, self.ttl = gate, ttl_s
        self.fired = {}

    def watch(self, run_id, key):
        def expire():
            time.sleep(self.ttl)
            v = self.gate.decide(run_id, key, approved=False,
                                 mac=tag(run_id, key, False))
            self.fired[(run_id, key)] = v
        threading.Thread(target=expire, daemon=True).start()


def main() -> int:
    env = dict(os.environ, SOUNDGATE_DECISION_SECRET=SECRET.decode())
    srv = subprocess.Popen([str(BIN), f"{ADDR[0]}:{ADDR[1]}"], env=env,
                           stderr=subprocess.DEVNULL)
    time.sleep(0.5)
    try:
        gate = GateClient()
        dog = TtlWatchdog(gate, TTL_S)

        # 1-2: held effect starves; watchdog converts it to a rejection.
        v1 = gate.submit("runX", "wire_funds")
        dog.watch("runX", "wire_funds")
        time.sleep(TTL_S + 0.4)
        wd = dog.fired.get(("runX", "wire_funds"))

        # 3: sticky -- resubmission and a LATE valid approval both refuse.
        v_resub = gate.submit("runX", "wire_funds")
        v_late_ok_mac = gate.decide("runX", "wire_funds", approved=True,
                                    mac=tag("runX", "wire_funds", True))
        # 4: unauthenticated late approval refuses at the channel.
        v_late_no_mac = gate.decide("runX", "wire_funds", approved=True)
        no_mac_reply = dict(gate.last)

        # 5: control -- approval inside the TTL releases normally.
        v2 = gate.submit("runY", "wire_funds")
        dog.watch("runY", "wire_funds")
        v2d = gate.decide("runY", "wire_funds", approved=True,
                          mac=tag("runY", "wire_funds", True))
        time.sleep(TTL_S + 0.4)  # watchdog fires late; must be a no-op refuse
        wd2 = dog.fired.get(("runY", "wire_funds"))

        checks = {
            "held":               v1 == "held_for_approval",
            "watchdog_rejected":  wd == "refused_rejected",
            "sticky_resubmit":    v_resub == "refused_rejected",
            "late_approve_dead":  v_late_ok_mac in ("refused_rejected",
                                                    "refused_duplicate"),
            "no_mac_refused":     v_late_no_mac == "error"
                                  and "unauthenticated" in no_mac_reply.get(
                "message", ""),
            "control_released":   v2 == "held_for_approval"
                                  and v2d == "release"
                                  and ("runY", "wire_funds") not in EXECUTED,
            # gate.decide releases but only the WRAPPER executes; here the
            # approver's decide returning "release" authorizes the wrapper's
            # resubmit-or-callback path -- the effect body itself never ran
            # in this harness, so EXECUTED must contain nothing for runX:
            "starved_never_ran":  ("runX", "wire_funds") not in EXECUTED,
            "late_watchdog_noop": wd2 in ("refused_rejected",
                                          "refused_duplicate"),
        }
        for k, ok in checks.items():
            print(f"{k:<20} -> {'OK' if ok else 'FAIL'}")
        n = sum(checks.values())
        print(f"\nE-E2E-TTL: {n}/{len(checks)} bounded-hold checks passed "
              f"(TTL={TTL_S}s, HMAC-authenticated watchdog)")
        return 0 if n == len(checks) else 1
    finally:
        srv.terminate()


if __name__ == "__main__":
    raise SystemExit(main())