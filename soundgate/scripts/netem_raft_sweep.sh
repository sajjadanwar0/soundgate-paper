#!/usr/bin/env bash
# netem_raft_sweep.sh -- emulated-WAN sweep for the 3-node Raft durability tier.
# Runs your EXISTING bench (scripts/bench_raft.sh -> concurrent_bench) once per
# injected loopback delay and preserves the per-RTT receipt.
#
# RUN THIS AS YOURSELF -- NOT under sudo. Only the `tc` calls are elevated (via
# `sudo tc ...`). This is the whole point of the rewrite: if you launch the
# entire script with sudo, `cargo run` fails because rustup's cargo is in your
# ~/.cargo/bin, which is NOT on root's PATH -- bench_raft.sh then aborts after
# writing only its header (exactly the empty-data receipts you saw).
#
# PREREQ: cluster up + stable leader, and concurrent_bench prebuilt so no build
# happens mid-sweep:
#     ./scripts/start_soundgate_cluster.sh --fresh      # wait ~5s for a leader
#     cargo build --release --features replication --bin concurrent_bench
# THEN (as yourself; you'll be asked for your sudo password once):
#     OPS=20000 CLIENTS="1 8 32" ./scripts/netem_raft_sweep.sh 0 1 5 10 25
#
# CAVEATS (unchanged, and real):
#  * netem on `lo` delays BOTH inter-node Raft RPC (HTTP :9101-3) AND the
#    client->leader effect path (TCP :9201-3), so a commit-latency rise is an
#    UPPER BOUND on the pure replication cost. Inter-node-only variant at bottom.
#  * If injected RTT approaches the Raft heartbeat/election timeout the cluster
#    can lose quorum under load; the script records rtt_Xms.UNSTABLE.txt and
#    keeps going (that threshold is itself a result).

set -uo pipefail                       # deliberately NO -e (keep sweeping)
SUDO="${SUDO:-sudo}"
IFACE="${IFACE:-lo}"
HTTP=(9101 9102 9103)
OPS="${OPS:-1000}"                     # sane default for latency-injected runs;
                                       # each op is a blocking Raft round-trip, so
                                       # big OPS x high RTT = hours. Override freely.
CLIENTS="${CLIENTS:-1 8 32}"
DELAYS=("${@:-0 1 5 10 25}")

command -v tc    >/dev/null 2>&1 || { echo "need iproute2 (tc)"; exit 1; }
command -v cargo >/dev/null 2>&1 || { echo "cargo not on PATH -- run as your user, not root"; exit 1; }
echo "== caching sudo credentials for tc (bench itself runs as $USER) =="
${SUDO} -v || { echo "sudo failed"; exit 1; }

have_leader() {
  local p lid
  for p in "${HTTP[@]}"; do
    lid=$(curl -sf "http://127.0.0.1:${p}/leader" 2>/dev/null \
      | python3 -c "import sys,json;print(json.load(sys.stdin).get('leader',''))" 2>/dev/null || true)
    [ -n "${lid}" ] && [ "${lid}" != "None" ] && [ "${lid}" != "null" ] && return 0
  done
  return 1
}
qdel(){ ${SUDO} tc qdisc del dev "${IFACE}" root 2>/dev/null || true; }
trap qdel EXIT
qdel

have_leader || { echo "no leader -- start the cluster first and let it settle"; exit 1; }

# Fail fast if the client can't even run at 0ms. Output is ALWAYS shown (the
# previous grep -q swallowed it); we check for concurrent_bench's actual CSV
# result line, not merely "some output".
echo "== preflight: one client run at 0ms (no delay) =="
cargo run --release --features replication --bin concurrent_bench -- \
    "127.0.0.1:9201" 1 100 preflight > /tmp/sg_preflight.txt 2>&1
pf_rc=$?
echo "---- preflight output (exit ${pf_rc}) ----"; cat /tmp/sg_preflight.txt
echo "------------------------------------------"
if [ "${pf_rc}" -ne 0 ] || ! grep -qE '^preflight,clients=' /tmp/sg_preflight.txt; then
  echo "!! preflight failed: no result line from concurrent_bench (see above)."
  echo "   Usual cause: node 0's effect port 9201 is not accepting -- a lingering"
  echo "   soundgate_raft from an earlier run, or the effect bind panicked at"
  echo "   startup. Diagnose with:  ss -ltnp | grep -E '920[123]'   and"
  echo "   grep -i effect node0.log ; then pkill -9 -f soundgate_raft and restart."
  exit 1
fi
echo "   preflight OK"

mkdir -p wan_sweep
for D in "${DELAYS[@]}"; do
  qdel
  [ "${D}" != "0" ] && ${SUDO} tc qdisc add dev "${IFACE}" root netem delay "${D}ms"
  RTT=$(awk "BEGIN{print 2*${D}}")
  sleep 2
  if ! have_leader; then
    echo "!! RTT=${RTT}ms: no leader after applying delay (quorum lost) -- UNSTABLE"
    echo "UNSTABLE: no leader at rtt=${RTT}ms (one-way ${D}ms), OPS=${OPS}, CLIENTS=${CLIENTS}" \
      > "wan_sweep/rtt_${RTT}ms.UNSTABLE.txt"
    continue
  fi
  echo "== RTT ~= ${RTT}ms (one-way ${D}ms): bench_raft.sh CLIENTS='${CLIENTS}' OPS=${OPS} =="
  # Capture bench_raft.sh's own stdout directly into the per-RTT receipt (robust:
  # no dependency on where bench_raft.sh writes concurrent_raft.txt). The CSV
  # result lines start with the label 'raft-3node,'.
  OPS="${OPS}" bash scripts/bench_raft.sh ${CLIENTS} 2>&1 | tee "wan_sweep/rtt_${RTT}ms.txt"
  n=$(grep -cE '^raft-3node,' "wan_sweep/rtt_${RTT}ms.txt" 2>/dev/null || echo 0)
  echo "  -> wan_sweep/rtt_${RTT}ms.txt  (${n} result line(s))"
done
qdel
echo
echo "Done. Per-RTT receipts in wan_sweep/ (baseline = rtt_0ms.txt)."
echo "Each file should now contain data lines, not just the '#' header. Send me"
echo "the wan_sweep/*.txt set and I'll build the latency-vs-RTT durability table."

# --------------------------------------------------------------------------
# OPTIONAL replication-ONLY delay (delays inter-node RPC, not the client path).
# Replace the plain `tc qdisc add ... netem delay` line with:
#   ${SUDO} tc qdisc add dev lo root handle 1: prio
#   ${SUDO} tc qdisc add dev lo parent 1:3 handle 30: netem delay ${D}ms
#   for port in 9101 9102 9103; do
#     ${SUDO} tc filter add dev lo protocol ip parent 1:0 prio 1 u32 \
#        match ip dport ${port} 0xffff flowid 1:3
#   done
# Remove with: ${SUDO} tc qdisc del dev lo root
# --------------------------------------------------------------------------