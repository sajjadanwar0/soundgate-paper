#!/usr/bin/env bash
# start_soundgate_cluster.sh -- bring up a 3-node replicated SOUNDGATE cluster
# and bootstrap Raft membership {0,1,2}. Complete and self-contained; no
# external cluster tooling. Modeled on the SOUNDGATE effect protocol, not S-Bus.
#
#   node 0: raft/admin http 127.0.0.1:9101   effect tcp 127.0.0.1:9201
#   node 1: raft/admin http 127.0.0.1:9102   effect tcp 127.0.0.1:9202
#   node 2: raft/admin http 127.0.0.1:9103   effect tcp 127.0.0.1:9203
#
# Usage (from the soundgate/ crate root):
#   ./scripts/start_soundgate_cluster.sh            # reuse existing sled data
#   ./scripts/start_soundgate_cluster.sh --fresh    # wipe raft-data-* first
# Logs: node0.log node1.log node2.log in the crate root.
set -euo pipefail

FRESH=0; [ "${1:-}" = "--fresh" ] && FRESH=1
BIN="target/release/soundgate_raft"
HTTP=(9101 9102 9103)
EFFECT=(9201 9202 9203)

echo "== building (release, replication feature) =="
cargo build --release --features replication 2>&1 | tail -3
[ -x "$BIN" ] || { echo "build failed: $BIN missing"; exit 1; }

echo "== clearing ports + old processes =="
for p in "${HTTP[@]}" "${EFFECT[@]}"; do
  pids=$(lsof -ti :"$p" 2>/dev/null || true)
  [ -n "$pids" ] && echo "$pids" | xargs kill -9 2>/dev/null || true
done
pkill -f "soundgate_raft" 2>/dev/null || true
sleep 1

if [ "$FRESH" = 1 ]; then
  echo "== --fresh: wiping raft-data-* =="
  rm -rf raft-data-0 raft-data-1 raft-data-2
fi

echo "== launching 3 nodes =="
for i in 0 1 2; do
  SOUNDGATE_RAFT_NODE_ID=$i \
  SOUNDGATE_RAFT_HTTP="127.0.0.1:${HTTP[$i]}" \
  SOUNDGATE_RAFT_EFFECT="127.0.0.1:${EFFECT[$i]}" \
  SOUNDGATE_RAFT_URL="http://127.0.0.1:${HTTP[$i]}" \
  SOUNDGATE_RAFT_DATA="raft-data-$i" \
  RUST_LOG=info \
    "$BIN" > "node$i.log" 2>&1 &
  echo "  node $i: http ${HTTP[$i]} effect ${EFFECT[$i]} pid $!"
done

echo "== waiting for HTTP endpoints =="
for i in 0 1 2; do
  for _ in $(seq 1 50); do
    curl -sf "http://127.0.0.1:${HTTP[$i]}/leader" >/dev/null 2>&1 && break
    sleep 0.2
  done
done
sleep 1

N0="http://127.0.0.1:${HTTP[0]}"
echo "== bootstrapping Raft on node 0 =="
curl -sf -X POST "$N0/admin/init" && echo
sleep 1
echo "== adding learners 1 and 2 =="
curl -sf -X POST "$N0/admin/add-learner" -H 'content-type: application/json' \
     -d "{\"node_id\":1,\"addr\":\"http://127.0.0.1:${HTTP[1]}\"}" && echo
curl -sf -X POST "$N0/admin/add-learner" -H 'content-type: application/json' \
     -d "{\"node_id\":2,\"addr\":\"http://127.0.0.1:${HTTP[2]}\"}" && echo
sleep 1
echo "== promoting to voting membership {0,1,2} =="
curl -sf -X POST "$N0/admin/change-membership" -H 'content-type: application/json' \
     -d '{"members":[0,1,2]}' && echo
sleep 1

echo "== cluster leader =="
curl -sf "$N0/leader" && echo
echo
echo "cluster up. effect ports: 0->9201 1->9202 2->9203"
echo "benchmark:  ./scripts/bench_raft.sh"
echo "stop:       ./scripts/stop_soundgate_cluster.sh"