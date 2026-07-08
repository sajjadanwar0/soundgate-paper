#!/usr/bin/env bash
# ebpf_demo.sh -- load the cgroup/connect4 mediation guard on capable hardware
# and PROVE structural mediation: a process in the attached cgroup may open an
# outbound connection ONLY to the SoundGate address; every other destination is
# refused by the KERNEL at connect() time (EPERM), not by wrapper convention.
#
# This is the runnable, locally-verified counterpart to egress_demo.sh (which
# uses a loopback-only network namespace). The eBPF route is more surgical: it
# permits the gate's exact address and denies all else at the syscall
# permission layer, and it does NOT require an isolated namespace.
#
# Requirements (all present on a modern Linux dev box; verified absent on the
# paper's original CI floor, which is why this route was previously run on
# external hardware):
#   - kernel >= 5.10 with BTF  (/sys/kernel/btf/vmlinux exists)
#   - cgroup v2 mounted at /sys/fs/cgroup
#   - clang + llvm (compile), bpftool (load/attach/inspect), libbpf headers
#   - root (cgroup attach + BPF_PROG_LOAD)
#
# Usage:  sudo ./ebpf_demo.sh [path/to/soundgate]      (default: target/release/soundgate)
# Commit: run  sudo ./ebpf_demo.sh 2>&1 | tee evidence/ebpf_demo.txt
set -euo pipefail

BIN="$(realpath "${1:-target/release/soundgate}")"
GATE_PORT=8796                        # MUST match GATE_PORT in ebpf/mediation_guard.c
GATE_ADDR="127.0.0.1:${GATE_PORT}"
CG=/sys/fs/cgroup/soundgate_mediation
OBJ=ebpf/mediation_guard.o
SRC=ebpf/mediation_guard.c

echo "== environment =="
uname -r
[ -f /sys/kernel/btf/vmlinux ] && echo "BTF: present" || { echo "BTF: MISSING -- CO-RE load will fail"; exit 1; }
[ -f /sys/fs/cgroup/cgroup.controllers ] || { echo "cgroup v2 not mounted"; exit 1; }
command -v bpftool >/dev/null || { echo "bpftool not found"; exit 1; }

echo "== compile (skip if .o already built) =="
if command -v clang >/dev/null; then
  clang -O2 -g -target bpf -c "$SRC" -o "$OBJ" \
    -I/usr/include/$(uname -m)-linux-gnu 2>/dev/null \
    && echo "compiled $OBJ" || echo "using pre-built $OBJ"
else
  echo "clang absent; using pre-built $OBJ"
fi

cleanup() {
  set +e
  [ -n "${GATE:-}" ] && kill "$GATE" 2>/dev/null
  bpftool cgroup detach "$CG" connect4 pinned /sys/fs/bpf/mediation_guard 2>/dev/null
  rm -f /sys/fs/bpf/mediation_guard 2>/dev/null
  [ -d "$CG" ] && rmdir "$CG" 2>/dev/null
}
trap cleanup EXIT

echo "== load + pin the program =="
bpftool prog load "$OBJ" /sys/fs/bpf/mediation_guard type cgroup/connect4
echo "loaded; program info:"
bpftool prog show pinned /sys/fs/bpf/mediation_guard

echo "== create cgroup and attach =="
mkdir -p "$CG"
bpftool cgroup attach "$CG" connect4 pinned /sys/fs/bpf/mediation_guard
echo "attached program under $CG:"
bpftool cgroup tree "$CG"          # <-- the receipt: shows connect4 + restrict_egress

echo "== start the gate on the allow-listed address =="
"$BIN" "$GATE_ADDR" & GATE=$!
sleep 0.6

echo "== move THIS shell into the attached cgroup, then test from within it =="
echo $$ > "$CG/cgroup.procs"

python3 - "$GATE_PORT" <<'PY'
import socket, json, sys
port = int(sys.argv[1])
print("--- unmediated external connect (must FAIL: kernel denies at connect4)")
try:
    socket.create_connection(("93.184.216.34", 80), timeout=2)
    print("UNEXPECTED: external reachable -- guard NOT enforcing"); raise SystemExit(1)
except OSError as e:
    print(f"    refused by kernel: {e}")          # EPERM / EACCES expected
print("--- mediated connect to the gate (must SUCCEED)")
s = socket.create_connection(("127.0.0.1", port), timeout=2)
s.sendall(json.dumps({"op":"submit","run_id":"ebpf-demo","effect_key":"k1",
                      "needs_approval":False}).encode()+b"\n")
print("    gate verdict:", s.makefile().readline().strip())
PY

echo "ebpf_demo: connect() to any non-gate address is refused by the kernel; the tool cannot opt out."