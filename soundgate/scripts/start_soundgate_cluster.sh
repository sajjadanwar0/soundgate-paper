#!/usr/bin/env bash
# start_soundgate_cluster.sh -- bring up / tear down the 3-voter soundgate Raft
# cluster used by Table `tab:load` (Raft-3), the netem sweep, and the fault-
# injection suite. Run from the soundgate/ crate root.
#
#   ./scripts/start_soundgate_cluster.sh up [--fresh]   # start 3 nodes + bootstrap
#   ./scripts/start_soundgate_cluster.sh down           # stop nodes (keep data)
#   ./scripts/start_soundgate_cluster.sh status         # leader + per-node metrics
#
# Node i (i = 0,1,2): raft/admin HTTP on 127.0.0.1:910(i+1),
# effect protocol on 127.0.0.1:920(i+1), data in ./raft-data-i,
# log in ./raft-node-i.log, pid in ./raft-node-i.pid.
# Matches the numbering in raft_failover.txt ("node 0" = effect 9201).
#
# Env overrides:
#   BIN=path            node binary (default target/release/soundgate_raft;
#                       built with --features replication if missing)
#   MOCK_BIN=script.py  run `python3 script.py` per node instead of BIN.
#                       Same env contract. HARNESS SELF-TEST ONLY -- receipts
#                       from a mock cluster are receipts about the harness,
#                       never about soundgate.
set -uo pipefail

HTTP=(9101 9102 9103)
EFFECT=(9201 9202 9203)
BIN="${BIN:-target/release/soundgate_raft}"
MOCK_BIN="${MOCK_BIN:-}"
CURL="curl -sf --max-time 2"

say() { printf '%s\n' "$*" >&2; }

node_alive() {  # true if the node's recorded pid is a live, non-zombie process
  local pidf="./raft-node-$1.pid" pid st
  [ -f "${pidf}" ] || return 1
  pid=$(cat "${pidf}")
  kill -0 "${pid}" 2>/dev/null || return 1
  st=$(ps -o stat= -p "${pid}" 2>/dev/null | tr -d ' ' | cut -c1)
  [ "${st}" != "Z" ]   # zombie = dead; SIGSTOPped (T) = alive
}

node_up() {  # node_up <id> -- no-op if that node is already running
  local id="$1"
  if node_alive "${id}"; then
    say "node ${id}: already running (pid $(cat "./raft-node-${id}.pid"))"
    return 0
  fi
  SOUNDGATE_RAFT_NODE_ID="$id" \
  SOUNDGATE_RAFT_HTTP="127.0.0.1:${HTTP[$id]}" \
  SOUNDGATE_RAFT_EFFECT="127.0.0.1:${EFFECT[$id]}" \
  SOUNDGATE_RAFT_URL="http://127.0.0.1:${HTTP[$id]}" \
  SOUNDGATE_RAFT_DATA="./raft-data-${id}" \
    "${LAUNCH[@]}" >>"./raft-node-${id}.log" 2>&1 &
  echo $! > "./raft-node-${id}.pid"
  say "node ${id}: pid $(cat "./raft-node-${id}.pid") (http ${HTTP[$id]}, effect ${EFFECT[$id]})"
}

wait_http() {  # wait until node <id>'s admin HTTP answers, or die
  local id="$1" t=0
  while ! ${CURL} "http://127.0.0.1:${HTTP[$id]}/leader" >/dev/null 2>&1; do
    t=$((t+1)); [ "$t" -gt 40 ] && { say "node ${id}: HTTP never came up (see raft-node-${id}.log)"; exit 1; }
    sleep 0.25
  done
}

current_leader() {  # print leader node id, or empty
  local p out
  for p in "${HTTP[@]}"; do
    out=$(${CURL} "http://127.0.0.1:${p}/leader" 2>/dev/null \
      | python3 -c "import sys,json;v=json.load(sys.stdin).get('leader');print('' if v is None else v)" 2>/dev/null) || continue
    [ -n "${out}" ] && { printf '%s' "${out}"; return 0; }
  done
  return 1
}

wait_leader() {
  local t=0 lid
  while :; do
    lid=$(current_leader || true)
    [ -n "${lid:-}" ] && { printf '%s' "${lid}"; return 0; }
    t=$((t+1)); [ "$t" -gt 60 ] && { say "no leader after 15s"; return 1; }
    sleep 0.25
  done
}

cmd="${1:-up}"; shift || true

case "${cmd}" in
  up)
    if [ "${1:-}" = "--fresh" ]; then
      say "== fresh start: wiping data dirs, logs, pids =="
      "$0" down >/dev/null 2>&1 || true
      rm -rf ./raft-data-0 ./raft-data-1 ./raft-data-2 ./mock-raft-shared
      rm -f  ./raft-node-*.log ./raft-node-*.pid
    fi
    if [ -n "${MOCK_BIN}" ]; then
      LAUNCH=(python3 "${MOCK_BIN}")
      say "== MOCK cluster (${MOCK_BIN}) -- harness self-test only =="
    else
      if [ ! -x "${BIN}" ]; then
        say "== building ${BIN} (--features replication) =="
        cargo build --release --features replication --bin soundgate_raft || exit 1
      fi
      LAUNCH=("${BIN}")
    fi
    for i in 0 1 2; do node_up "$i"; done
    for i in 0 1 2; do wait_http "$i"; done
    # Bootstrap is idempotent-ish: on a --fresh cluster init succeeds; on a
    # restarted one it 409s and we just wait for the existing leader.
    if ${CURL} -X POST "http://127.0.0.1:${HTTP[0]}/admin/init" >/dev/null 2>&1; then
      say "== init ok on node 0; adding learners, then voters =="
      sleep 0.5
      for i in 1 2; do
        ${CURL} -X POST "http://127.0.0.1:${HTTP[0]}/admin/add-learner" \
          -H 'content-type: application/json' \
          -d "{\"node_id\":${i},\"addr\":\"http://127.0.0.1:${HTTP[$i]}\"}" >/dev/null \
          || { say "add-learner ${i} failed"; exit 1; }
      done
      sleep 0.5
      ${CURL} -X POST "http://127.0.0.1:${HTTP[0]}/admin/change-membership" \
        -H 'content-type: application/json' -d '{"members":[0,1,2]}' >/dev/null \
        || { say "change-membership failed"; exit 1; }
    else
      say "== init returned conflict (already initialized); reusing existing state =="
    fi
    lid=$(wait_leader) || exit 1
    say "== cluster up; leader: node ${lid} (effect ${EFFECT[$lid]}) =="
    ;;
  down)
    for i in 0 1 2; do
      if [ -f "./raft-node-${i}.pid" ]; then
        pid=$(cat "./raft-node-${i}.pid")
        kill -CONT "${pid}" 2>/dev/null || true   # in case a fault left it SIGSTOPped
        kill "${pid}" 2>/dev/null || true
      fi
    done
    sleep 0.3
    for i in 0 1 2; do
      [ -f "./raft-node-${i}.pid" ] && kill -9 "$(cat "./raft-node-${i}.pid")" 2>/dev/null
      rm -f "./raft-node-${i}.pid"
    done
    say "== cluster down =="
    ;;
  status)
    lid=$(current_leader || true)
    say "leader: ${lid:-<none>}"
    for i in 0 1 2; do
      m=$(${CURL} "http://127.0.0.1:${HTTP[$i]}/metrics" 2>/dev/null \
        | python3 -c "import sys,json;m=json.load(sys.stdin);print('last_log_index=%s last_applied=%s' % (m.get('last_log_index'), (m.get('last_applied') or {}).get('index')))" 2>/dev/null) \
        || m="DOWN"
      say "node ${i}: ${m}"
    done
    ;;
  *) say "usage: $0 up [--fresh] | down | status"; exit 2 ;;
esac
