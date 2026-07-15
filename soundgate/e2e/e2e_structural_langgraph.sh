#!/usr/bin/env bash
# Usage (repo root, gate built, probes venv present):
#   cargo build --release
#   sudo ./e2e_structural_langgraph.sh [venv-python] [gate-binary]
# Defaults: ../probes/.venv/bin/python  and  target/release/soundgate
# Evidence: tee stdout to evidence/e2e_structural_langgraph.txt
set -euo pipefail
# realpath -s: make absolute WITHOUT resolving symlinks. A venv's bin/python
# is a symlink to the base interpreter; canonicalizing it escapes the venv
# (loses site-packages -> ModuleNotFoundError: langgraph). -s preserves it.
PY="$(realpath -s "${1:-../probes/.venv/bin/python}")"
BIN="$(realpath "${2:-target/release/soundgate}")"
E2E="$(realpath "$(dirname "$0")/e2e_langgraph.py")"
[ -x "$BIN" ] || { echo "gate binary not found: $BIN"; exit 1; }
[ -x "$PY" ]  || { echo "venv python not found: $PY"; exit 1; }
"$PY" - <<'PY' || { echo "PREFLIGHT FAIL: langgraph not importable by $PY -- is this the probes venv?"; exit 1; }
import langgraph  # noqa: F401  (preflight: fail fast outside the namespace)
PY

unshare -n bash -c '
  set -euo pipefail
  ip link set lo up
  echo "=== [namespace] loopback up; no other interface, no route out ==="
  ip -brief addr

  echo "=== [namespace] BYPASS PROBE: unwrapped tool path (must FAIL) ==="
  "'"$PY"'" - <<PY
import socket
try:
    socket.create_connection(("93.184.216.34", 80), timeout=2)
    print("UNEXPECTED: external network reachable"); raise SystemExit(1)
except OSError as e:
    print(f"    unmediated external connect refused by kernel: {e}")
PY

  echo "=== [namespace] FULL FRAMEWORK INTEGRATION (must PASS 3/3) ==="
  # e2e_langgraph.py spawns the gate itself; the child inherits this netns,
  # so gate, framework, wrapper, and tools all live behind the same egress
  # wall. Loopback (framework -> gate) is the ONLY connectivity.
  cd "$(dirname "'"$E2E"'")"/..
  "'"$PY"'" "'"$E2E"'"

  echo "=== [namespace] POST-CHECK: egress still absent after the run ==="
  "'"$PY"'" - <<PY
import socket
try:
    socket.create_connection(("1.1.1.1", 443), timeout=2)
    print("UNEXPECTED: external network reachable"); raise SystemExit(1)
except OSError as e:
    print(f"    still refused by kernel: {e}")
PY
'
echo "e2e_structural: framework integration passed under OS-enforced mediation;"
echo "e2e_structural: the only path out of the namespace is through the gate."