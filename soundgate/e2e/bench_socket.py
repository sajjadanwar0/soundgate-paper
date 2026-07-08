#!/usr/bin/env python3
"""Socket round-trip latency benchmark for the SoundGate reference server.

Measures end-to-end admission latency over the real line-delimited JSON TCP
protocol (the number that actually bounds deployment overhead, since the
in-process Criterion benchmark excludes the socket). Single client, sequential
requests -- this measures latency, not throughput. A concurrent-client
throughput benchmark is intentionally out of scope.

Reproducible artifact for the paper's Overhead section. Run:
    cd soundgate && cargo build --release
    python3 e2e/bench_socket.py            # default 20000 round-trips
    python3 e2e/bench_socket.py 50000      # custom count

Prints median / mean / p95 / p99 in microseconds and admissions/sec, plus a
one-line environment stamp (fill CPU model into the paper's footnote).
"""
import json
import platform
import socket
import statistics
import subprocess
import sys
import time
from pathlib import Path

ADDR = ("127.0.0.1", 8796)
BIN = Path(__file__).resolve().parents[1] / "target" / "release" / "soundgate"


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20_000
    srv = subprocess.Popen([str(BIN), f"{ADDR[0]}:{ADDR[1]}"],
                           stderr=subprocess.DEVNULL)
    time.sleep(0.4)
    try:
        s = socket.create_connection(ADDR)
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        rf = s.makefile("r")

        # Warm up (JIT-free, but warms caches / connection).
        for i in range(1000):
            s.sendall((json.dumps(
                {"op": "submit", "run_id": "warm",
                 "effect_key": f"w{i}", "needs_approval": False}) + "\n").encode())
            rf.readline()

        # Measure: each iteration is one submit round-trip with a unique key
        # (release path -- the common case). Per-call timing.
        samples = []
        for i in range(n):
            req = json.dumps({"op": "submit", "run_id": "bench",
                              "effect_key": f"k{i}",
                              "needs_approval": False}) + "\n"
            t0 = time.perf_counter_ns()
            s.sendall(req.encode())
            rf.readline()
            samples.append(time.perf_counter_ns() - t0)

        samples.sort()
        us = [x / 1000.0 for x in samples]
        median = statistics.median(us)
        mean = statistics.fmean(us)
        p95 = us[int(0.95 * len(us))]
        p99 = us[int(0.99 * len(us))]
        rate = 1_000_000.0 / mean

        print(f"socket round-trip latency over {n} sequential submits "
              f"(loopback, TCP_NODELAY, single client):")
        print(f"  median {median:.2f} us | mean {mean:.2f} us | "
              f"p95 {p95:.2f} us | p99 {p99:.2f} us")
        print(f"  throughput (1/mean): {rate:,.0f} admissions/sec")
        print(f"  env: {platform.processor() or platform.machine()}, "
              f"Python {platform.python_version()}, {platform.system()}")
    finally:
        srv.terminate()


if __name__ == "__main__":
    main()