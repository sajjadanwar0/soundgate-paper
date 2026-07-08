#!/usr/bin/env bash
# Structural mediation, demonstrated: run the gate and a tool process inside
# a LOOPBACK-ONLY network namespace. The tool can reach the gate (same-
# namespace loopback) and has NO route to anything else, so an unmediated
# external call fails at the OS level -- bypass is prevented by the kernel,
# not by placement discipline. This is the "network-namespace egress
# allow-listing" route of Sec. 5.1 made runnable. Requires root (or userns).
#
# Usage: sudo ./egress_demo.sh [path/to/soundgate]     (default: target/release/soundgate)
set -euo pipefail
BIN="$(realpath "${1:-target/release/soundgate}")"
unshare -n bash -c '
  set -e
  ip link set lo up
  "'"$BIN"'" 127.0.0.1:8899 & GATE=$!
  sleep 0.5
  python3 - <<PY
import socket, json
print("--- unmediated external call (must FAIL: namespace has no egress)")
try:
    socket.create_connection(("93.184.216.34", 80), timeout=2)
    print("UNEXPECTED: external network reachable"); raise SystemExit(1)
except OSError as e:
    print(f"    blocked by kernel: {e}")
print("--- mediated call through the gate (must SUCCEED)")
s = socket.create_connection(("127.0.0.1", 8899), timeout=2)
s.sendall(json.dumps({"op":"submit","run_id":"ns-demo","effect_key":"k1",
                      "needs_approval":False}).encode()+b"\n")
print("    gate verdict:", s.makefile().readline().strip())
PY
  kill $GATE
'
echo "egress_demo: only path out of the namespace is through the gate."