#!/usr/bin/env bash
# bench_raft.sh -- measure replicated (3-node Raft) admission throughput and
# emit the receipt for Table 6's new "Raft-3node" row. Reuses the EXISTING
# concurrent_bench.rs client unchanged (it just speaks the effect protocol),
# so the mem / WAL / WAL-GC / Raft rows are all produced by the same harness.
#
# Prereq: ./scripts/start_soundgate_cluster.sh   (cluster up, membership {0,1,2})
# Output: concurrent_raft.txt  (+ the leader's raft metrics, for provenance)
set -euo pipefail

HTTP=(9101 9102 9103)
EFFECT=(9201 9202 9203)
OPS="${OPS:-20000}"                     # per client; match your WAL sweep
CLIENTS=("${@:-1 8 32 128}")            # override: ./bench_raft.sh 1 8 32
OUT="concurrent_raft.txt"

# Find the current leader id from any node.
leader_id=""
for i in 0 1 2; do
  lid=$(curl -sf "http://127.0.0.1:${HTTP[$i]}/leader" 2>/dev/null \
        | python3 -c "import sys,json; print(json.load(sys.stdin).get('leader',''))" 2>/dev/null || true)
  [ -n "$lid" ] && [ "$lid" != "None" ] && [ "$lid" != "null" ] && { leader_id="$lid"; break; }
done
[ -n "$leader_id" ] || { echo "no leader yet -- is the cluster up and membership set?"; exit 1; }
LEADER_EFFECT="127.0.0.1:${EFFECT[$leader_id]}"
echo "leader = node $leader_id ; effect port $LEADER_EFFECT"

# Provenance: record that this really is a 3-voter quorum, not a lone node.
echo "# soundgate raft 3-node throughput; $(date -u +%FT%TZ)" | tee "$OUT"
echo "# leader=node$leader_id  ops_per_client=$OPS" | tee -a "$OUT"
echo "# --- leader raft metrics (quorum evidence) ---" | tee -a "$OUT"
curl -sf "http://127.0.0.1:${HTTP[$leader_id]}/metrics" \
  | python3 -c "import sys,json;m=json.load(sys.stdin);print('#',{k:m.get(k) for k in ('current_leader','vote','last_log_index','last_applied','membership_config')})" \
  | tee -a "$OUT"

# The sweep. concurrent_bench prints one CSV line per run; label = raft-3node.
# shellcheck disable=SC2068
for C in ${CLIENTS[@]}; do
  echo ">> C=$C"
  cargo run --release --features replication --bin concurrent_bench -- \
      "$LEADER_EFFECT" "$C" "$OPS" raft-3node \
    | tee -a "$OUT"
done

echo
echo "wrote $OUT"
echo "send me concurrent_raft.txt -- I verify it is a real 3-voter quorum"
echo "(current_leader set, membership_config has 3 voters) before it enters Table 6."