#!/usr/bin/env python3
"""Sustained-load soak of the durable (WAL, group-commit) gate under repeated crashes.

IEEE Access Access-2026-43496, final files (2026-10-02): answers Reviewer 1,
item 6 (longer-running experiments under sustained workloads and repeated
failures).

What it does
  * Runs the reference server in WAL mode with decision authentication on and
    online WAL compaction enabled.
  * W worker threads drive closed-loop agent "runs" over their own connections.
    A run mixes ungated releases, a replay of a released key, approval holds
    decided approve or reject (HMAC-tagged), a resubmission of a rejected key,
    cancellation with a late zombie submit and decide (30% of runs), and a
    `close` followed by a late submit. Effect keys repeat across runs, so
    cross-run scoping is exercised. Workers pause --think-ms between runs.
  * A killer SIGKILLs the server at random intervals and restarts it from its
    WAL; every segment boundary is one more SIGKILL and restart.
  * State is checkpointed at each segment boundary, so the soak resumes after
    an interruption of the harness itself (run the same command again).

Safety oracles, checked on every reply across all restarts
  O1  no (run, key) receives two `release` replies;
  O2  no `release` for an identity after a `refused_rejected` reply for it;
  O3  no `release` in a run after its cancel or close was acknowledged.
Runs are unique per worker and segment, so O1-O3 are tracked per run; a
reservoir of released identities is re-probed after the final crash, where
every one must be refused. A wrapper performs an effect only on a received
`release`, so O1-O3 are exactly "no double, rejected, or fenced effect
executes". Requests in flight at a crash have unknown outcome and are retried;
strict expected-verdict checks apply to runs that saw no restart.

Exit status is non-zero on any oracle violation, any strict mismatch in a run
that saw no restart, a restart that never answers, a closed run that keeps a
per-identity WAL record after the final recovery, or fresh work refused.

Usage (from soundgate/):
  cargo build --release --locked
  python3 scripts/soak_wal.py --minutes 30 --state /tmp/soak --out evidence/soak_wal.txt
"""
import argparse
import hashlib
import hmac
import json
import os
import random
import signal
import socket
import subprocess
import sys
import threading
import time
from collections import Counter

SECRET = b"soak-decision-secret"
KEYS = ["pay", "mail", "ticket", "deploy", "refund", "notify", "charge", "invite"]


def tag(run, key, approved):
    msg = f"{run}\n{key}\n{'1' if approved else '0'}".encode()
    return hmac.new(SECRET, msg, hashlib.sha256).hexdigest()


class Down(Exception):
    pass


class Server:
    def __init__(self, binary, port, wal, compact_min):
        self.binary, self.port, self.wal = binary, port, wal
        self.env = dict(os.environ, SOUNDGATE_DECISION_SECRET=SECRET.decode(),
                        SOUNDGATE_WAL_COMPACT_MIN=str(compact_min))
        self.proc = None
        self.log = open(wal + ".server.log", "a")
        self.lock = threading.Lock()

    def start(self):
        self.proc = subprocess.Popen([self.binary, f"127.0.0.1:{self.port}", self.wal],
                                     env=self.env, stdout=self.log, stderr=self.log)

    def kill(self):
        if self.proc and self.proc.poll() is None:
            self.proc.send_signal(signal.SIGKILL)
            self.proc.wait()

    def wait_ready(self, timeout=60.0):
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=1.0) as s:
                    s.sendall(b'{"op":"ping"}\n')
                    if b"pong" in s.makefile("rb").readline():
                        return time.monotonic() - t0
            except OSError:
                time.sleep(0.01)
        return None

    def rss_kib(self):
        try:
            with open(f"/proc/{self.proc.pid}/status") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        return int(line.split()[1])
        except (OSError, AttributeError):
            pass
        return None


class Conn:
    def __init__(self, port):
        self.port, self.s, self.rf = port, None, None

    def call(self, req):
        try:
            if self.s is None:
                self.s = socket.create_connection(("127.0.0.1", self.port), timeout=30.0)
                self.s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                self.rf = self.s.makefile("rb")
            self.s.sendall((json.dumps(req, separators=(",", ":")) + "\n").encode())
            line = self.rf.readline()
            if not line:
                raise Down()
            return json.loads(line)["verdict"]
        except (OSError, ValueError, KeyError, Down):
            self.close()
            raise Down()

    def close(self):
        try:
            if self.s:
                self.s.close()
        except OSError:
            pass
        self.s = self.rf = None


class Shared:
    """Counters, violations and the reservoir of released identities."""

    def __init__(self, st, rng):
        self.lock = threading.Lock()
        self.st, self.rng = st, rng

    def add(self, k, n=1):
        with self.lock:
            self.st[k] = self.st.get(k, 0) + n

    def violation(self, v):
        with self.lock:
            if len(self.st["violations"]) < 50:
                self.st["violations"].append(v)
            self.st["violation_count"] += 1

    def released(self, run, key):
        with self.lock:
            st = self.st
            st["identities_released"] += 1
            st["reservoir_seen"] += 1
            if len(st["reservoir"]) < 2000:
                st["reservoir"].append([run, key])
            else:
                j = self.rng.randrange(st["reservoir_seen"])
                if j < 2000:
                    st["reservoir"][j] = [run, key]


def worker(wid, seg, inc, port, sh, stop, seed, think):
    rng = random.Random(seed)
    conn = Conn(port)
    reconnects = 0
    run_no = 0
    while not stop.is_set():
        run_no += 1
        run = f"i{inc}-s{seg}-w{wid}-r{run_no}"
        released, rejected, fenced = set(), set(), [False]
        start = reconnects
        bad = []

        def call(req, key=None):
            nonlocal reconnects
            while True:
                try:
                    v = conn.call(req)
                    break
                except Down:
                    reconnects += 1
                    sh.add("reconnects")
                    time.sleep(0.05)
            sh.add("ops")
            if v == "release":
                if key in released:
                    sh.violation(f"O1 double release {run}/{key}")
                if key in rejected:
                    sh.violation(f"O2 release after reject {run}/{key}")
                if fenced[0]:
                    sh.violation(f"O3 release in fenced run {run}/{key}")
                released.add(key)
                sh.released(run, key)
            elif v == "refused_rejected" and key is not None:
                rejected.add(key)
            elif req["op"] in ("cancel", "close") and v == "ack":
                fenced[0] = True
            return v

        def expect(got, want, what):
            if got != want:
                bad.append(f"{run} {what}: got {got}, want {want}")

        keys = rng.sample(KEYS, k=rng.randint(3, 6))
        free, gated = keys[:-2], keys[-2:]
        for k in free:
            expect(call({"op": "submit", "run_id": run, "effect_key": k}, k), "release", f"submit {k}")
        k = rng.choice(free)
        expect(call({"op": "submit", "run_id": run, "effect_key": k}, k), "refused_duplicate", f"replay {k}")
        pending = []
        for k in gated:
            expect(call({"op": "submit", "run_id": run, "effect_key": k, "needs_approval": True}, k),
                   "held_for_approval", f"hold {k}")
            r = rng.random()
            if r < 0.6:
                v = call({"op": "decide", "run_id": run, "effect_key": k, "approved": True,
                          "mac": tag(run, k, True)}, k)
                if v == "refused_duplicate" and reconnects > start and k not in released:
                    # holds are not durable: a crash lost it; resubmit re-holds
                    call({"op": "submit", "run_id": run, "effect_key": k, "needs_approval": True}, k)
                    v = call({"op": "decide", "run_id": run, "effect_key": k, "approved": True,
                              "mac": tag(run, k, True)}, k)
                expect(v, "release", f"approve {k}")
            elif r < 0.85:
                expect(call({"op": "decide", "run_id": run, "effect_key": k, "approved": False,
                             "mac": tag(run, k, False)}, k), "refused_rejected", f"reject {k}")
                expect(call({"op": "submit", "run_id": run, "effect_key": k}, k),
                       "refused_rejected", f"resubmit rejected {k}")
            else:
                pending.append(k)
        if rng.random() < 0.3:
            expect(call({"op": "cancel", "run_id": run}), "ack", "cancel")
            expect(call({"op": "submit", "run_id": run, "effect_key": "zombie"}, "zombie"),
                   "refused_cancelled", "zombie submit")
            for k in pending:
                expect(call({"op": "decide", "run_id": run, "effect_key": k, "approved": True,
                             "mac": tag(run, k, True)}, k), "refused_cancelled", f"late approve {k}")
            sh.add("runs_cancelled")
        expect(call({"op": "close", "run_id": run}), "ack", "close")
        expect(call({"op": "submit", "run_id": run, "effect_key": keys[0]}, keys[0]),
               "refused_cancelled", "submit after close")
        sh.add("runs")
        if reconnects > start:
            sh.add("runs_spanning_restart")
            sh.add("strict_mismatch_explained_by_restart", len(bad))
        else:
            sh.add("runs_strict")
            for b in bad:
                sh.violation("STRICT " + b)
        if think > 0:
            time.sleep(think)
    conn.close()


def wal_census(path):
    kinds, closed, ident_runs = Counter(), set(), set()
    with open(path) as f:
        for line in f:
            if not line.strip():
                continue
            ev = json.loads(line)
            kinds[ev["ev"]] += 1
            if ev["ev"] == "closed":
                closed.add(ev["run_id"])
            elif ev["ev"] in ("released", "rejected"):
                ident_runs.add(ev["run_id"])
    return dict(sorted(kinds.items())), len(closed & ident_runs)


def save(path, st):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--binary", default="target/release/soundgate")
    ap.add_argument("--minutes", type=float, default=30.0)
    ap.add_argument("--segment", type=float, default=60.0, help="seconds per checkpointed segment")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--think-ms", type=float, default=40.0)
    ap.add_argument("--kill-min", type=float, default=20.0)
    ap.add_argument("--kill-max", type=float, default=40.0)
    ap.add_argument("--compact-min", type=int, default=4096)
    ap.add_argument("--port", type=int, default=8899)
    ap.add_argument("--seed", type=int, default=20261002)
    ap.add_argument("--state", required=True, help="directory for WAL + checkpoint (resumable)")
    ap.add_argument("--out", default="evidence/soak_wal.txt")
    a = ap.parse_args()

    os.makedirs(a.state, exist_ok=True)
    wal = os.path.join(a.state, "gate.wal")
    ckpt = os.path.join(a.state, "state.json")
    if os.path.exists(ckpt):
        st = json.load(open(ckpt))
        print(f"resuming after {st['segments_done']} segment(s), {st['elapsed_s']:.0f}s", flush=True)
    else:
        st = {"segments_done": 0, "elapsed_s": 0.0, "ops": 0, "runs": 0, "runs_strict": 0,
              "runs_spanning_restart": 0, "runs_cancelled": 0, "reconnects": 0, "restarts": 0,
              "ready_s": [], "rss_kib_min": None, "rss_kib_max": 0, "wal_bytes_max": 0,
              "identities_released": 0, "reservoir": [], "reservoir_seen": 0,
              "strict_mismatch_explained_by_restart": 0, "violations": [], "violation_count": 0,
              "started": time.strftime("%Y-%m-%d %H:%M:%S %Z")}
    # Each harness start is a new incarnation. Run ids carry it, because the WAL
    # can be ahead of the checkpoint: runs of an interrupted segment are already
    # durable (and closed), and reusing their ids would meet their fences.
    st["incarnation"] = st.get("incarnation", 0) + 1
    rng = random.Random(a.seed + 7919 * st["segments_done"] + 104729 * st["incarnation"])
    sh = Shared(st, rng)
    srv = Server(a.binary, a.port, wal, a.compact_min)

    def restart(count):
        srv.start()
        ready = srv.wait_ready()
        if ready is None:
            sh.violation("LIVENESS restart never answered")
        elif count:
            st["ready_s"].append(round(ready, 4))
            st["restarts"] += 1
        return ready

    restart(st["segments_done"] > 0)
    while st["elapsed_s"] < a.minutes * 60 and st["violation_count"] == 0:
        seg = st["segments_done"]
        seg_len = min(a.segment, a.minutes * 60 - st["elapsed_s"])
        stop, done = threading.Event(), threading.Event()
        t0 = time.monotonic()
        ws = [threading.Thread(target=worker, args=(i, seg, st["incarnation"], a.port, sh, stop, a.seed + 1000 * seg + 100000 * st["incarnation"] + i,
                                                     a.think_ms / 1000.0), daemon=True)
              for i in range(a.workers)]

        def killer():
            while not done.is_set():
                if done.wait(rng.uniform(a.kill_min, a.kill_max)):
                    return
                with srv.lock:
                    srv.kill()
                    restart(True)

        def sampler():
            while not done.wait(2.0):
                with srv.lock:
                    rss = srv.rss_kib()
                    if rss:
                        st["rss_kib_min"] = rss if st["rss_kib_min"] is None else min(st["rss_kib_min"], rss)
                        st["rss_kib_max"] = max(st["rss_kib_max"], rss)
                    if os.path.exists(wal):
                        st["wal_bytes_max"] = max(st["wal_bytes_max"], os.path.getsize(wal))

        aux = [threading.Thread(target=killer, daemon=True), threading.Thread(target=sampler, daemon=True)]
        for t in ws + aux:
            t.start()
        while time.monotonic() - t0 < seg_len and st["violation_count"] == 0:
            time.sleep(0.5)
        done.set()
        for t in aux:
            t.join()
        stop.set()                      # workers finish (and close) their current run
        for t in ws:
            t.join(timeout=120)
        st["elapsed_s"] += time.monotonic() - t0
        st["segments_done"] += 1
        with srv.lock:                  # segment boundary: one more crash
            srv.kill()
        save(ckpt, st)
        print(f"segment {seg} done: elapsed {st['elapsed_s']:.0f}s ops {st['ops']} runs {st['runs']} "
              f"restarts {st['restarts']} violations {st['violation_count']}", flush=True)
        if st["elapsed_s"] < a.minutes * 60 and st["violation_count"] == 0:
            restart(True)

    # Final crash recovery: replay, compaction at recovery, then probes.
    restart(True)
    final_rss = srv.rss_kib()
    kinds, closed_with_ident = wal_census(wal)
    probe = Conn(a.port)
    refused = 0
    for run, key in st["reservoir"]:
        v = probe.call({"op": "submit", "run_id": run, "effect_key": key})
        if v == "release":
            sh.violation(f"RECOVERY re-released {run}/{key}")
        else:
            refused += 1
    fresh = probe.call({"op": "submit", "run_id": "post-soak-fresh", "effect_key": "k"})
    probe.close()
    srv.kill()
    viol = list(st["violations"])
    if closed_with_ident:
        viol.append(f"BOUNDED {closed_with_ident} closed run(s) keep per-identity records")
    if fresh != "release":
        viol.append(f"LIVENESS fresh work after final recovery got {fresh}")
    nviol = st["violation_count"] + (1 if closed_with_ident else 0) + (1 if fresh != "release" else 0)
    ready = sorted(st["ready_s"])

    def pct(p):
        return ready[min(len(ready) - 1, int(p * (len(ready) - 1)))] if ready else float("nan")

    lines = [
        "soundgate WAL soak (sustained load + repeated SIGKILL/restart)",
        f"started={st['started']} host={os.uname().nodename} kernel={os.uname().release} cpus={os.cpu_count()}",
        f"config: minutes={a.minutes} segment_s={a.segment} workers={a.workers} think_ms={a.think_ms} "
        f"kill_every=U[{a.kill_min},{a.kill_max}]s plus every segment boundary "
        f"compact_min={a.compact_min} hmac=on seed={a.seed}",
        f"elapsed_s={st['elapsed_s']:.0f} segments={st['segments_done']} ops={st['ops']} "
        f"runs={st['runs']} ops_per_s={st['ops'] / max(st['elapsed_s'], 1):.0f}",
        f"runs: strict={st['runs_strict']} spanning_restart={st['runs_spanning_restart']} "
        f"cancelled={st['runs_cancelled']} reconnects={st['reconnects']}",
        f"identities_released={st['identities_released']}",
        f"restarts={st['restarts']}",
        f"ready_s p50={pct(0.5):.3f} p95={pct(0.95):.3f} max={(ready[-1] if ready else float('nan')):.3f}",
        f"rss_kib min={st['rss_kib_min']} max={max(st['rss_kib_max'], final_rss or 0)} final={final_rss}",
        f"wal_bytes max={st['wal_bytes_max']} final={os.path.getsize(wal)}",
        f"final_wal_records {kinds}",
        f"closed_runs_with_identity_records={closed_with_ident}",
        f"post_recovery_probe: {refused}/{len(st['reservoir'])} sampled released identities refused; fresh={fresh}",
        f"strict_mismatch_explained_by_restart={st['strict_mismatch_explained_by_restart']}",
        f"oracle_violations={sum(1 for v in viol if v[:2] in ('O1', 'O2', 'O3'))}",
        f"VERDICT {'PASS' if nviol == 0 else 'FAIL'} ({nviol} violation(s))",
    ]
    lines += [f"  violation: {v}" for v in viol[:20]]
    lines.append("ready_s per restart: " + " ".join(f"{x:.3f}" for x in st["ready_s"]))
    text = "\n".join(lines) + "\n"
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w") as f:
        f.write(text)
    sys.stdout.write(text)
    return 1 if nviol else 0


if __name__ == "__main__":
    sys.exit(main())
