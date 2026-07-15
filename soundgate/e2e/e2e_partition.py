import json
import os
import signal
import socket
import subprocess
import tempfile
import threading
import time
from pathlib import Path

ADDR = ("127.0.0.1", 8811)
BIN = Path(__file__).resolve().parents[1] / "target" / "release" / "soundgate"

EFFECTS = []


class FailClosedGateClient:
    def __init__(self, addr=ADDR, timeout=1.0):
        self.addr, self.timeout = addr, timeout
        self.sock = None
        self.rf = None
        self.lock = threading.Lock()

    def _connect(self):
        self.sock = socket.create_connection(self.addr, timeout=self.timeout)
        self.sock.settimeout(self.timeout)
        self.rf = self.sock.makefile("r")

    def _call(self, req: dict) -> str:
        with self.lock:
            try:
                if self.sock is None:
                    self._connect()
                self.sock.sendall((json.dumps(req) + "\n").encode())
                line = self.rf.readline()
                if not line:
                    raise ConnectionError("gate closed the connection")
                return json.loads(line)["verdict"]
            except (OSError, ConnectionError, json.JSONDecodeError):
                self.sock = None
                return "refused_unreachable"

    def mediated_effect(self, run_id, key, do_effect, needs_approval=False):
        v = self._call({"op": "submit", "run_id": run_id, "effect_key": key,
                        "needs_approval": needs_approval})
        if v == "release":
            do_effect()
        return v

    def decide(self, run_id, key, approved):
        return self._call({"op": "decide", "run_id": run_id,
                           "effect_key": key, "approved": approved})

def main() -> int:
    wal = Path(tempfile.mkdtemp()) / "partition.wal"
    g = FailClosedGateClient()

    v_down = g.mediated_effect("runP", "send_invoice",
                               lambda: EFFECTS.append("send_invoice"))
    ok1 = v_down == "refused_unreachable" and EFFECTS == []

    srv = subprocess.Popen([str(BIN), f"{ADDR[0]}:{ADDR[1]}", str(wal)],
                           stderr=subprocess.DEVNULL)
    time.sleep(0.6)
    v_up = g.mediated_effect("runP", "send_invoice",
                             lambda: EFFECTS.append("send_invoice"))
    ok2 = v_up == "release" and EFFECTS == ["send_invoice"]

    os.kill(srv.pid, signal.SIGKILL)
    srv.wait()
    v_killed = g.mediated_effect("runP", "post_webhook",
                                 lambda: EFFECTS.append("post_webhook"))
    ok3 = v_killed == "refused_unreachable" and "post_webhook" not in EFFECTS

    srv2 = subprocess.Popen([str(BIN), f"{ADDR[0]}:{ADDR[1]}", str(wal)],
                            stderr=subprocess.DEVNULL)
    time.sleep(0.8)
    v_fresh = g.mediated_effect("runP", "post_webhook",
                                lambda: EFFECTS.append("post_webhook"))
    v_replay = g.mediated_effect("runP", "send_invoice",
                                 lambda: EFFECTS.append("send_invoice"))
    ok4 = (v_fresh == "release" and v_replay == "refused_duplicate"
           and EFFECTS == ["send_invoice", "post_webhook"])
    srv2.terminate()

    checks = {
        "gate_down_refuses":        ok1,
        "gate_up_releases":         ok2,
        "sigkill_midsession_refuses": ok3,
        "restart_fresh_and_fenced": ok4,
    }

    for k, ok in checks.items():
        print(f"{k:<28} -> {'OK' if ok else 'FAIL'}")
    n = sum(checks.values())
    print(f"\nE-E2E-PARTITION: {n}/{len(checks)} fail-closed checks passed "
          f"(down / SIGKILL mid-session / WAL restart)")

    return 0 if n == len(checks) else 1

if __name__ == "__main__":
    raise SystemExit(main())