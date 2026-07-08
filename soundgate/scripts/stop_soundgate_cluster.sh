#!/usr/bin/env bash
# stop_soundgate_cluster.sh -- tear down the 3-node replicated cluster.
set -uo pipefail
for p in 9101 9102 9103 9201 9202 9203; do
  pids=$(lsof -ti :"$p" 2>/dev/null || true)
  [ -n "$pids" ] && echo "$pids" | xargs kill -9 2>/dev/null && echo "killed :$p" || true
done
pkill -f "soundgate_raft" 2>/dev/null || true
echo "cluster stopped (sled data in raft-data-* preserved; use start --fresh to wipe)."