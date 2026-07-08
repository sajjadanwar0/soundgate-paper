#!/usr/bin/env python3
"""pipelined_bench.py -- measure the replicated gate's TRUE admission throughput.

concurrent_bench.rs is closed-loop (one op in flight per client), so it cannot
tell "the server serializes" from "the client under-drives it." This generator
keeps a fixed WINDOW of ops in flight on each of M connections, so the server is
never starved. If throughput here is high but concurrent_bench is low, the drop
was a closed-loop measurement effect; if throughput here is ALSO low, the server
is serializing and needs the store fix / deeper tuning.

Usage:
  python3 pipelined_bench.py HOST:PORT [total_ops] [connections] [window]
Examples:
  python3 pipelined_bench.py 127.0.0.1:9201 20000            # 1 conn, window 256
  python3 pipelined_bench.py 127.0.0.1:9201 40000 4 256      # 4 conns, window 256
Each op is a unique submit (unique run_id) so none are refused as duplicates.
"""
import socket, sys, threading, time, itertools

def parse():
    if len(sys.argv) < 2 or ":" not in sys.argv[1]:
        print(__doc__); sys.exit(1)
    host, port = sys.argv[1].split(":", 1)
    if not port.isdigit():
        print(f"error: port must be a number, got '{port}'.\n"
              f"Substitute your leader's EFFECT port: node 0 -> 9201, "
              f"1 -> 9202, 2 -> 9203.\n"
              f"e.g. python3 {sys.argv[0]} 127.0.0.1:9201 20000 1 256",
              file=sys.stderr)
        sys.exit(2)
    total = int(sys.argv[2]) if len(sys.argv) > 2 else 20000
    conns = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    window = int(sys.argv[4]) if len(sys.argv) > 4 else 256
    return host, int(port), total, conns, window

def worker(host, port, n, window, cid, out, lat):
    """Send n ops on one connection keeping `window` in flight; time each."""
    s = socket.create_connection((host, port), timeout=30)
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    rf = s.makefile("rb")
    sent = recv = 0
    send_ts = {}
    inflight = 0
    latencies = []
    counter = itertools.count()
    def send_one():
        nonlocal sent, inflight
        i = next(counter)
        rid = f"c{cid}_{i}"
        msg = ('{"op":"submit","run_id":"%s","effect_key":"k","needs_approval":false}\n' % rid).encode()
        send_ts[sent] = time.perf_counter()
        s.sendall(msg); sent += 1; inflight += 1
    # prime the window
    while inflight < window and sent < n:
        send_one()
    # steady state: for each reply, send the next
    while recv < n:
        line = rf.readline()
        if not line:
            break
        t = time.perf_counter()
        latencies.append((t - send_ts.pop(recv, t)) * 1e6)  # us
        recv += 1; inflight -= 1
        if sent < n:
            send_one()
    s.close()
    out[cid] = recv
    lat.extend(latencies)

def main():
    host, port, total, conns, window = parse()
    per = total // conns
    out = {}; lat = []
    threads = [threading.Thread(target=worker, args=(host, port, per, window, c, out, lat))
               for c in range(conns)]
    t0 = time.perf_counter()
    for th in threads: th.start()
    for th in threads: th.join()
    wall = time.perf_counter() - t0
    done = sum(out.values())
    lat.sort()
    def pct(p):
        return lat[min(len(lat)-1, int(len(lat)*p))] if lat else 0.0
    print(f"pipelined,conns={conns},window={window},ops={done},wall_s={wall:.3f},"
          f"thpt_adm_per_s={done/wall:.0f},"
          f"p50_us={pct(0.50):.1f},p95_us={pct(0.95):.1f},p99_us={pct(0.99):.1f}")

if __name__ == "__main__":
    main()