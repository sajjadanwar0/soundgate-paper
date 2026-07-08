#!/usr/bin/env bash
# raft_failover.sh -- prove the replicated gate survives leader loss:
#   (1) availability: a NEW leader is elected within the election window and the
#       effect protocol keeps admitting, and
#   (2) durability/no-double-release: an identity RELEASED before the crash is
#       refused as a duplicate on the NEW leader -- the replicated fence
#       survived the failover. This is the direct answer to "the gate is a
#       single point of failure."
#
# Prereq: ./scripts/start_soundgate_cluster.sh   (3-voter quorum up)
# Output: raft_failover.txt
#
# NOTE: written but not run in this environment (no toolchain). If a step
# misbehaves, the manual commands in REPLICATION notes reproduce it by hand.
set -uo pipefail
OUT="raft_failover.txt"
HTTP=(9101 9102 9103)
EFFECT=(9201 9202 9203)

send() {  # $1 = effect port, $2 = json op ; prints the verdict line
  python3 - "$1" "$2" <<'PY'
import socket,sys
port=int(sys.argv[1]); op=sys.argv[2].encode()+b"\n"
try:
    s=socket.create_connection(("127.0.0.1",port),timeout=3)
    s.sendall(op); print(s.recv(4096).decode().strip()); s.close()
except Exception as e:
    print(f'{{"verdict":"unreachable","err":"{e}"}}')
PY
}

leader_of() {  # prints current leader id by polling every node
  for i in 0 1 2; do
    lid=$(curl -sf "http://127.0.0.1:${HTTP[$i]}/leader" 2>/dev/null \
          | python3 -c "import sys,json;print(json.load(sys.stdin).get('leader',''))" 2>/dev/null || true)
    [ -n "$lid" ] && [ "$lid" != "None" ] && [ "$lid" != "null" ] && { echo "$lid"; return; }
  done
  echo ""
}

: > "$OUT"
log(){ echo "$*" | tee -a "$OUT"; }

log "# soundgate raft failover receipt; $(date -u +%FT%TZ)"

L0=$(leader_of)
[ -n "$L0" ] || { log "no leader -- is the cluster up?"; exit 1; }
log "# initial leader: node $L0 (effect ${EFFECT[$L0]})"

# (1) Establish a fence on the cluster BEFORE the crash.
ID='{"op":"submit","run_id":"r_failover","effect_key":"charge_card","needs_approval":false}'
R1=$(send "${EFFECT[$L0]}" "$ID")
log "# pre-crash submit  -> $R1        (expect release)"

# (2) Kill the leader process (found via its http port).
LPID=$(lsof -ti :"${HTTP[$L0]}" 2>/dev/null | head -1)
[ -n "$LPID" ] || { log "could not find leader pid on port ${HTTP[$L0]}"; exit 1; }
log "# killing leader node $L0 (pid $LPID) ..."
T_KILL=$(date +%s.%N)
kill -9 "$LPID" 2>/dev/null || true

# (3) Availability: poll for a NEW leader distinct from the killed one.
NEWL=""
for _ in $(seq 1 100); do          # up to ~10s; election window is ~0.5-1s
  cand=$(leader_of)
  if [ -n "$cand" ] && [ "$cand" != "$L0" ]; then NEWL="$cand"; break; fi
  sleep 0.1
done
T_NEW=$(date +%s.%N)
if [ -z "$NEWL" ]; then
  log "# FAIL: no new leader elected after killing node $L0"
  exit 1
fi
ELECT=$(python3 -c "print(f'{$T_NEW-$T_KILL:.2f}')")
log "# new leader elected: node $NEWL  (effect ${EFFECT[$NEWL]})  in ${ELECT}s"

# (4) Durability / no double-release: re-submit the SAME identity to the new
#     leader. The fence must have replicated, so this is a duplicate -- NOT a
#     second release. This is the safety-critical assertion.
R2=$(send "${EFFECT[$NEWL]}" "$ID")
log "# post-failover re-submit (same id) -> $R2   (expect refused_duplicate)"

# (5) Liveness: the new leader still admits FRESH effects.
FRESH='{"op":"submit","run_id":"r_after","effect_key":"send_email","needs_approval":false}'
R3=$(send "${EFFECT[$NEWL]}" "$FRESH")
log "# post-failover fresh submit        -> $R3   (expect release)"

log ""
if echo "$R2" | grep -q refused_duplicate && echo "$R3" | grep -q release; then
  log "# RESULT: PASS -- new leader in ${ELECT}s; pre-crash fence survived"
  log "#         (no double-release across failover); cluster still admitting."
else
  log "# RESULT: CHECK -- verdicts not as expected; inspect nodeN.log"
fi
log "# send me raft_failover.txt"