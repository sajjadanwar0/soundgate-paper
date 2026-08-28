#!/usr/bin/env bash
# faultinject_raft.sh -- broader fault injection for the replicated soundgate
# deployment (reviewer-requested; extends the single leader-kill scenario of
# raft_failover.txt). Run from the soundgate/ crate root:
#
#     ./scripts/faultinject_raft.sh            # all scenarios
#     ./scripts/faultinject_raft.sh S2 S3      # a subset
#
# Scenarios (each on a fresh cluster; receipt in evidence/faultinject_<S>.txt):
#   S1 follower-kill        : hold survives a follower crash; quorum 2/3 still
#                             decides; restarted follower catches up.
#   S2 leader-kill-mid-hold : hold taken on old leader; leader killed; the SAME
#                             (run,key) is decided exactly once on the new
#                             leader; re-decide refuses; released fence survives.
#   S3 leader-pause         : SIGSTOP the leader (GC-pause nemesis); new leader
#                             decides the pending hold; SIGCONT the old leader;
#                             no second release anywhere.
#   S4 follower-state-loss  : follower stopped, data dir DELETED, restarted.
#                             SAFETY is pass/fail (fence, ledger, admits);
#                             resync liveness is MEASURED per trigger:
#                             quiescent incumbent / first new write / leader
#                             change. FAIL only if NO trigger resyncs or
#                             safety breaks.
#   S5 quorum-loss          : both followers killed; the lone leader must NOT
#                             release a fresh effect (fail-closed without
#                             quorum); on recovery the cluster admits again and
#                             the stalled id has released at most once.
#
# Safety ledger (every scenario): across every response captured cluster-wide,
# "release" for a given (run_id,effect_key) appears AT MOST ONCE. A second
# release of the same identity anywhere is an automatic FAIL.
#
# The cluster is the REAL binary via ./scripts/start_soundgate_cluster.sh.
# (MOCK_BIN exercises the harness itself only; receipts then say MOCK.)
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1   # soundgate/ crate root

HTTP=(9101 9102 9103)
EFFECT=(9201 9202 9203)
CLUSTER=./scripts/start_soundgate_cluster.sh
EV=evidence
CURL="curl -sf --max-time 2"
mkdir -p "${EV}"
STAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
MODE_NOTE=""; [ -n "${MOCK_BIN:-}" ] && MODE_NOTE=" [MOCK -- harness self-test, not a soundgate receipt]"

# ---- tiny line-JSON client over the effect protocol ------------------------
sg_req() {  # sg_req <effect_port> <json>  -> one response line or CONN_ERROR:...
  python3 - "$1" "$2" <<'PY'
import json, socket, sys
port, payload = int(sys.argv[1]), sys.argv[2]
try:
    s = socket.create_connection(("127.0.0.1", port), timeout=3)
    s.settimeout(6)
    s.sendall(payload.encode() + b"\n")
    buf = b""
    while not buf.endswith(b"\n"):
        chunk = s.recv(4096)
        if not chunk: break
        buf += chunk
    print(buf.decode().strip() or "CONN_ERROR:empty")
except Exception as e:
    print(f"CONN_ERROR:{type(e).__name__}:{e}")
PY
}
submit() { sg_req "$1" "{\"op\":\"submit\",\"run_id\":\"$2\",\"effect_key\":\"$3\",\"needs_approval\":$4}"; }
decide() { sg_req "$1" "{\"op\":\"decide\",\"run_id\":\"$2\",\"effect_key\":\"$3\",\"approved\":$4}"; }

verdict() { python3 -c "import sys,json
try: print(json.loads(sys.argv[1]).get('verdict','<none>'))
except Exception: print('<unparsed>')" "$1"; }

leader_id() {
  local p out
  for p in "${HTTP[@]}"; do
    out=$(${CURL} "http://127.0.0.1:${p}/leader" 2>/dev/null \
      | python3 -c "import sys,json;v=json.load(sys.stdin).get('leader');print('' if v is None else v)" 2>/dev/null) || continue
    [ -n "${out}" ] && { printf '%s' "${out}"; return 0; }
  done
  return 1
}
wait_new_leader() {  # wait_new_leader <exclude_id> -> prints id; up to 15s
  local ex="$1" t=0 lid
  while :; do
    lid=$(leader_id || true)
    if [ -n "${lid:-}" ] && [ "${lid}" != "${ex}" ]; then printf '%s' "${lid}"; return 0; fi
    t=$((t+1)); [ "$t" -gt 60 ] && return 1
    sleep 0.25
  done
}
metric() {  # metric <node_id> <last_log_index|applied>
  local m; m=$(${CURL} "http://127.0.0.1:${HTTP[$1]}/metrics" 2>/dev/null) || { echo ""; return; }
  python3 -c "import sys,json;m=json.loads(sys.argv[1])
k=sys.argv[2]
print(m.get('last_log_index') if k=='last_log_index' else (m.get('last_applied') or {}).get('index'))" "${m}" "$2" 2>/dev/null
}
wait_caught_up() {  # wait_caught_up <node_id>: applied(node) >= last_log_index(leader)
  local id="$1" t=0 lid tgt app
  while :; do
    lid=$(leader_id || true); [ -z "${lid:-}" ] && { sleep 0.25; t=$((t+1)); [ "$t" -gt 80 ] && return 1; continue; }
    tgt=$(metric "${lid}" last_log_index); app=$(metric "${id}" applied)
    if [ -n "${tgt}" ] && [ -n "${app}" ] && [ "${app}" != "None" ] && [ "${tgt}" != "None" ] \
       && [ "${app}" -ge "${tgt}" ] 2>/dev/null; then return 0; fi
    t=$((t+1)); [ "$t" -gt 80 ] && return 1
    sleep 0.25
  done
}
node_pid() { cat "./raft-node-$1.pid" 2>/dev/null; }
dump_metrics() {  # append every node's raw /metrics JSON to the receipt
  local i m
  for i in 0 1 2; do
    m=$(${CURL} "http://127.0.0.1:${HTTP[$i]}/metrics" 2>/dev/null) || m="<unreachable>"
    log "# metrics[node ${i}] ${m}"
  done
}

# ---- receipt + ledger ------------------------------------------------------
R=""     # current receipt file
LEDGER="" # current ledger file (one line per response: "<id> <verdict>")
log() { printf '%s\n' "$*" | tee -a "${R}" >&2; }
step() { # step <label> <id> <response> <expect-substring-of-verdict>
  local label="$1" id="$2" resp="$3" want="$4" v
  v=$(verdict "${resp}")
  printf '%s %s\n' "${id}" "${v}" >> "${LEDGER}"
  log "# ${label} -> ${resp}   (expect ${want})"
  case "${v}" in *"${want}"*) return 0 ;; *) log "# ^ MISMATCH: got '${v}'"; return 1 ;; esac
}
step_not_release() { # step_not_release <label> <id> <response>
  local label="$1" id="$2" resp="$3" v
  v=$(verdict "${resp}")
  printf '%s %s\n' "${id}" "${v}" >> "${LEDGER}"
  log "# ${label} -> ${resp}   (expect anything but release)"
  [ "${v}" != "release" ]
}
ledger_ok() {  # no (id) with >1 release
  python3 - "${LEDGER}" <<'PY'
import collections, sys
c = collections.Counter()
for line in open(sys.argv[1]):
    parts = line.split()
    if len(parts) == 2 and parts[1] == "release":
        c[parts[0]] += 1
bad = {k: v for k, v in c.items() if v > 1}
if bad:
    print("DOUBLE-RELEASE:", bad); sys.exit(1)
print("single-release ledger: OK (%d distinct released ids)" % len(c))
PY
}
fresh() { "${CLUSTER}" down >/dev/null 2>&1 || true; "${CLUSTER}" up --fresh >/dev/null 2>&1 || { echo "cluster up failed" >&2; exit 1; }; }
begin() { # begin <S> <title>
  R="${EV}/faultinject_$1.txt"; LEDGER=$(mktemp)
  : > "${R}"
  log "# soundgate raft fault-injection receipt${MODE_NOTE}; ${STAMP}"
  log "# scenario $1: $2"
  fresh
  L0=$(leader_id) || { log "# RESULT: FAIL -- no initial leader"; return 1; }
  log "# initial leader: node ${L0} (effect ${EFFECT[$L0]})"
}
finish() { # finish <S> <0-if-ok>
  local s="$1" ok="$2" led i
  for i in 0 1 2; do
    [ -f "./raft-node-${i}.log" ] && cp "./raft-node-${i}.log" "${EV}/faultinject_${s}_node${i}.log"
  done
  led=$(ledger_ok) || ok=1
  log "# ${led}"
  if [ "${ok}" -eq 0 ]; then log "# RESULT: PASS"; PASS+=("$s"); else log "# RESULT: FAIL"; FAIL+=("$s"); fi
  rm -f "${LEDGER}"
}

PASS=(); FAIL=()

# ---------------------------------------------------------------- S1 --------
s1() {
  begin S1 "follower crash: hold survives, quorum decides, follower catches up" || { finish S1 1; return; }
  local ok=0 lp=${EFFECT[$L0]} f id="s1-run:pay"
  step "submit needs_approval on leader" "${id}" "$(submit "${lp}" s1-run pay true)" held_for_approval || ok=1
  for f in 0 1 2; do [ "$f" != "$L0" ] && break; done   # first follower
  log "# killing follower node ${f} (pid $(node_pid "$f"))"
  kill -9 "$(node_pid "$f")" 2>/dev/null; sleep 0.5
  step "decide approve on leader with 2/3 alive" "${id}" "$(decide "${lp}" s1-run pay true)" release || ok=1
  step "fresh submit still admits (2/3)" "s1-run:fresh" "$(submit "${lp}" s1-run fresh false)" release || ok=1
  log "# restarting follower node ${f}"
  "${CLUSTER}" up >/dev/null 2>&1 || true   # idempotent: relaunches only the dead node
  sleep 1
  wait_caught_up "${f}" && log "# follower ${f} caught up (applied >= leader last_log_index)" \
                        || { log "# follower ${f} did NOT catch up in 20s"; dump_metrics; ok=1; }
  step "duplicate of decided id refuses" "${id}" "$(submit "$(printf '%s' "${EFFECT[$(leader_id)]}")" s1-run pay true)" refused_duplicate || ok=1
  finish S1 "${ok}"
}

# ---------------------------------------------------------------- S2 --------
s2() {
  begin S2 "leader crash with a hold in flight: decided exactly once on new leader" || { finish S2 1; return; }
  local ok=0 lp=${EFFECT[$L0]} id="s2-run:refund" t0 t1 nl
  step "pre-crash submit (auto) releases" "s2-run:pre" "$(submit "${lp}" s2-run pre false)" release || ok=1
  step "submit needs_approval -> held" "${id}" "$(submit "${lp}" s2-run refund true)" held_for_approval || ok=1
  log "# killing leader node ${L0} (pid $(node_pid "${L0}")) with the hold in flight ..."
  t0=$(date +%s.%N); kill -9 "$(node_pid "${L0}")" 2>/dev/null
  nl=$(wait_new_leader "${L0}") || { log "# no new leader in 15s"; finish S2 1; return; }
  t1=$(date +%s.%N)
  log "# new leader elected: node ${nl} (effect ${EFFECT[$nl]}) in $(python3 -c "print(f'{${t1}-${t0}:.2f}s')")"
  step "decide the in-flight hold on NEW leader" "${id}" "$(decide "${EFFECT[$nl]}" s2-run refund true)" release || ok=1
  step_not_release "re-decide same id (no second release)" "${id}" "$(decide "${EFFECT[$nl]}" s2-run refund true)" || ok=1
  step "pre-crash released id still fenced" "s2-run:pre" "$(submit "${EFFECT[$nl]}" s2-run pre false)" refused_duplicate || ok=1
  step "fresh submit admits on new leader" "s2-run:post" "$(submit "${EFFECT[$nl]}" s2-run post false)" release || ok=1
  finish S2 "${ok}"
}

# ---------------------------------------------------------------- S3 --------
s3() {
  begin S3 "leader pause (SIGSTOP): decision moves; resumed leader cannot double-release" || { finish S3 1; return; }
  local ok=0 lp=${EFFECT[$L0]} id="s3-run:deploy" nl
  step "submit needs_approval -> held" "${id}" "$(submit "${lp}" s3-run deploy true)" held_for_approval || ok=1
  log "# SIGSTOP leader node ${L0} (pid $(node_pid "${L0}")) -- GC-pause nemesis"
  kill -STOP "$(node_pid "${L0}")"
  nl=$(wait_new_leader "${L0}") || { kill -CONT "$(node_pid "${L0}")"; log "# no new leader in 15s"; finish S3 1; return; }
  log "# new leader elected while old one is frozen: node ${nl}"
  step "decide pending hold on NEW leader" "${id}" "$(decide "${EFFECT[$nl]}" s3-run deploy true)" release || ok=1
  log "# SIGCONT old leader node ${L0} -- it wakes with stale leadership"
  kill -CONT "$(node_pid "${L0}")"; sleep 2
  step_not_release "decide same id at OLD leader's effect port" "${id}" "$(decide "${lp}" s3-run deploy true)" || ok=1
  step_not_release "duplicate submit of decided id (any live port)" "${id}" "$(submit "${EFFECT[$(leader_id)]}" s3-run deploy true)" || ok=1
  finish S3 "${ok}"
}

# ---------------------------------------------------------------- S4 --------
s4() {
  begin S4 "follower total state loss: safety must hold; resync liveness measured per trigger" || { finish S4 1; return; }
  local ok=0 lp=${EFFECT[$L0]} f id="s4-run:invoice" nl resync=""
  step "submit+auto-release on leader" "${id}" "$(submit "${lp}" s4-run invoice false)" release || ok=1
  for f in 0 1 2; do [ "$f" != "$L0" ] && break; done
  log "# stopping follower node ${f} and DELETING ./raft-data-${f}"
  kill -9 "$(node_pid "$f")" 2>/dev/null; sleep 0.3
  rm -rf "./raft-data-${f}"
  log "# restarting follower node ${f} from empty state"
  "${CLUSTER}" up >/dev/null 2>&1 || true
  sleep 1
  # Phase A (measured; quiescent log): does the incumbent leader re-probe a
  # state-lost voter when no new traffic arrives? Recorded either way.
  if wait_caught_up "${f}"; then
    resync="incumbent-quiescent"
    log "# MEASURED: resync under incumbent leader with quiescent log: OK"
  else
    log "# MEASURED: resync under incumbent leader with quiescent log: STALLED (20s)"
    log "#   leader's replication watermark for node ${f} stays at its pre-loss index; no log transfer occurs"
    dump_metrics
  fi
  # Phase B (measured): does the FIRST new committed write trigger the resync?
  if [ -z "${resync}" ]; then
    step "probe write under incumbent leader" "s4-run:probe" "$(submit "${lp}" s4-run probe false)" release || ok=1
    if wait_caught_up "${f}"; then
      resync="first-write"
      log "# MEASURED: first new committed write triggered full resync"
    else
      log "# MEASURED: still no resync 20s after a committed write"; dump_metrics
    fi
  fi
  # Phase C: leader change (always exercised; doubles as the re-election fence test)
  log "# killing current leader node ${L0} to force re-election over the rebuilt follower"
  kill -9 "$(node_pid "${L0}")" 2>/dev/null
  nl=$(wait_new_leader "${L0}") || { log "# no new leader in 15s"; finish S4 1; return; }
  log "# post-loss leader: node ${nl}"
  if wait_caught_up "${f}"; then
    [ -z "${resync}" ] && { resync="leader-change"; log "# MEASURED: leader change triggered full resync"; }
  else
    log "# node ${f} STILL lagging after leader change"; dump_metrics; ok=1
  fi
  [ -z "${resync}" ] && ok=1
  log "# resync trigger: ${resync:-NONE (liveness failure)}"
  step "released id from before the state loss is STILL fenced" "${id}" "$(submit "${EFFECT[$nl]}" s4-run invoice false)" refused_duplicate || ok=1
  step "fresh submit admits" "s4-run:fresh" "$(submit "${EFFECT[$nl]}" s4-run fresh false)" release || ok=1
  finish S4 "${ok}"
}

# ---------------------------------------------------------------- S5 --------
s5() {
  begin S5 "quorum loss: lone leader fails closed; recovery admits; no phantom release" || { finish S5 1; return; }
  local ok=0 lp=${EFFECT[$L0]} f1="" f2="" id="s5-run:wire" resp v
  for f in 0 1 2; do [ "$f" != "$L0" ] && { [ -z "${f1}" ] && f1=$f || f2=$f; }; done
  log "# killing BOTH followers (nodes ${f1},${f2}) -- leader retains no quorum"
  kill -9 "$(node_pid "${f1}")" "$(node_pid "${f2}")" 2>/dev/null
  sleep 1.5   # > election timeout (1s) and > mock heartbeat staleness (0.8s)
  resp=$(submit "${lp}" s5-run wire false); v=$(verdict "${resp}")
  printf '%s %s\n' "${id}" "${v}" >> "${LEDGER}"
  log "# submit under lost quorum -> ${resp}   (expect anything but release)"
  [ "${v}" = "release" ] && { log "# ^ RELEASED WITHOUT QUORUM"; ok=1; }
  log "# restarting both followers"
  "${CLUSTER}" up >/dev/null 2>&1 || true
  sleep 1
  wait_caught_up "${f1}" && wait_caught_up "${f2}" \
    && log "# both followers caught up" || { log "# followers did not catch up in 20s"; dump_metrics; ok=1; }
  # The stalled id may or may not have committed during recovery; safety is
  # single-release, checked two ways: the ledger, and a duplicate probe.
  resp=$(submit "${EFFECT[$(leader_id)]}" s5-run wire false); v=$(verdict "${resp}")
  printf '%s %s\n' "${id}" "${v}" >> "${LEDGER}"
  log "# re-submit stalled id after recovery -> ${resp}   (release XOR refused_duplicate; both safe, never two releases)"
  step "fresh submit admits after recovery" "s5-run:fresh" "$(submit "${EFFECT[$(leader_id)]}" s5-run fresh false)" release || ok=1
  finish S5 "${ok}"
}

# ---- run -------------------------------------------------------------------
SCEN=("${@:-S1 S2 S3 S4 S5}"); [ $# -eq 0 ] && SCEN=(S1 S2 S3 S4 S5)
for s in "${SCEN[@]}"; do
  case "$s" in S1) s1;; S2) s2;; S3) s3;; S4) s4;; S5) s5;; *) echo "unknown scenario $s" >&2;; esac
done
"${CLUSTER}" down >/dev/null 2>&1 || true

SUM="${EV}/faultinject_summary.txt"
{
  echo "# soundgate raft fault-injection summary${MODE_NOTE}; ${STAMP}"
  echo "# PASS: ${PASS[*]:-<none>}"
  echo "# FAIL: ${FAIL[*]:-<none>}"
  echo "# invariant: no (run_id,effect_key) released more than once, cluster-wide, in any scenario"
} > "${SUM}"
cat "${SUM}" >&2
[ "${#FAIL[@]}" -eq 0 ]
