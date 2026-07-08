"""E-E2E-RECOVERY10X: WAL recovery at 10x the paper's measured log (keyless).

Sec. 5.5 reports recovery replaying the 170,600-event (10.5 MB) accounting
WAL in 1.9 s on the container floor (~90k events/s) before the listener
opens. R4 asks for recovery at scale. This script synthesizes a WAL ten
times that size in the gate's exact durable-event format (the format of the
committed e2e/e2e_test.wal: released / cancelled records), starts the gate
on it, and measures the fail-closed window -- process spawn to first
successful ping -- since nothing is admitted until the state is restored.

State is then verified, not assumed: a replayed identity from the log
refuses as a duplicate, a cancelled run's late submission refuses at the
fence, and fresh work releases.

Log shape mirrors the accounting run's population at 10x: 1,706,000 events,
of which 1,700,000 are unique releases across 2,000 runs and 6,000 are
run-cancellation fences (so fence compaction and the released-set both get
exercised at scale).

Run:  cargo build --release && python3 e2e/e2e_recovery10x.py
"""
import json
import os
import socket
import subprocess
import tempfile
import time
from pathlib import Path

ADDR = ("127.0.0.1", 8812)
BIN = Path(__file__).resolve().parents[1] / "target" / "release" / "soundgate"

N_RELEASED = 1_700_000
N_RUNS = 2_000
N_CANCELLED = 6_000


def synthesize(path: Path) -> tuple[int, float]:
    t0 = time.time()
    with open(path, "w") as f:
        for i in range(N_RELEASED):
            f.write(json.dumps({"ev": "released",
                                "run_id": f"r{i % N_RUNS}",
                                "effect_key": f"k{i}"}) + "\n")
        for j in range(N_CANCELLED):
            f.write(json.dumps({"ev": "cancelled",
                                "run_id": f"c{j}"}) + "\n")
    return N_RELEASED + N_CANCELLED, time.time() - t0


def wait_listening(addr, deadline_s=600.0) -> float:
    """Poll until the listener accepts and answers ping; return wall time."""
    t0 = time.time()
    while time.time() - t0 < deadline_s:
        try:
            s = socket.create_connection(addr, timeout=0.5)
            s.sendall(b'{"op":"ping"}\n')
            line = s.makefile("r").readline()
            s.close()
            if json.loads(line)["verdict"] == "pong":
                return time.time() - t0
        except OSError:
            time.sleep(0.1)
    raise TimeoutError("gate never opened its listener")


def call(sock_rf, req):
    sock, rf = sock_rf
    sock.sendall((json.dumps(req) + "\n").encode())
    return json.loads(rf.readline())["verdict"]


def main() -> int:
    wal = Path(tempfile.mkdtemp()) / "recovery10x.wal"
    n, gen_s = synthesize(wal)
    size_mb = os.path.getsize(wal) / 1e6
    print(f"synthesized WAL: {n:,} events, {size_mb:.1f} MB "
          f"(generated in {gen_s:.1f}s)")

    srv = subprocess.Popen([str(BIN), f"{ADDR[0]}:{ADDR[1]}", str(wal)],
                           stderr=subprocess.DEVNULL)
    try:
        recovery_s = wait_listening(ADDR)
        rate = n / recovery_s
        print(f"recovery (spawn -> first pong, fail-closed window): "
              f"{recovery_s:.1f} s  (~{rate/1000:.0f}k events/s)")

        sock = socket.create_connection(ADDR, timeout=5.0)
        rf = sock.makefile("r")
        c = (sock, rf)
        v_dup = call(c, {"op": "submit", "run_id": "r0",
                         "effect_key": "k0", "needs_approval": False})
        v_fence = call(c, {"op": "submit", "run_id": "c0",
                           "effect_key": "anything", "needs_approval": False})
        v_fresh = call(c, {"op": "submit", "run_id": "fresh",
                           "effect_key": "new_work", "needs_approval": False})
        checks = {
            "replayed_identity_refused_duplicate": v_dup == "refused_duplicate",
            "cancelled_run_fence_survives":        v_fence == "refused_cancelled",
            "fresh_work_releases":                 v_fresh == "release",
        }
        for k, ok in checks.items():
            print(f"{k:<38} -> {'OK' if ok else 'FAIL'}")
        ok_all = all(checks.values())
        print(f"\nE-E2E-RECOVERY10X: {n:,} events / {size_mb:.1f} MB replayed "
              f"in {recovery_s:.1f} s; state checks "
              f"{sum(checks.values())}/{len(checks)}")
        return 0 if ok_all else 1
    finally:
        srv.terminate()
        try:
            wal.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())