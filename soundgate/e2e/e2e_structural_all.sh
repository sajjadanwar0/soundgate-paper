#!/usr/bin/env bash
# e2e_structural_all.sh -- B1: run EVERY framework repair inside a loopback-only
# network namespace, gate as sole reachable endpoint, proving complete mediation
# is STRUCTURALLY enforced (kernel-imposed) across the whole evaluation.
#
# Per framework, in a fresh net namespace:
#   (1) BYPASS PROBE: an unwrapped external connect must fail (no route out).
#   (2) FULL INTEGRATION: the keyless repair harness runs; the gate it spawns
#       inherits the namespace, so gate+framework+wrapper+tools sit behind one
#       egress wall; loopback (framework->gate) is the only link.
#
# v2: the bypass probe is a bash /dev/tcp check inside a single-quoted heredoc,
# so nothing passes through nested shell quoting (v1's multi-line Python string
# was mangled by the quoting and SyntaxError'd). PY/HARNESS are passed as
# positional args to `bash -s`, not interpolated.
#
# Usage (from soundgate/):  ./e2e/e2e_structural_all.sh | tee evidence/e2e_structural_all.txt
set -uo pipefail
cd "$(dirname "$0")/.."          # -> soundgate/
cargo build --release
sudo -v                          # cache sudo creds once

run_one() {                      # $1 label  $2 venv-python  $3 harness  $4 preflight-module
    local label="$1" pyrel="$2" harnessrel="$3" mod="$4"
    local PY H
    PY="$(realpath -s "$pyrel" 2>/dev/null)"     # -s: keep venv symlink (canonicalizing escapes the venv)
    H="$(realpath "$harnessrel" 2>/dev/null)"
    echo "======================================================================"
    echo "== $label =="
    [ -x "$PY" ] || { echo "  SKIP: venv python not found: $pyrel"; return 2; }
    [ -f "$H" ]  || { echo "  SKIP: harness not found: $harnessrel"; return 2; }
    "$PY" -c "import $mod" 2>/dev/null || echo "  preflight WARN: '$mod' not importable (continuing; in-ns run shows the real error)"

    sudo unshare --net bash -s "$PY" "$H" <<'INNER'
        set -uo pipefail
        PY="$1"; H="$2"
        ip link set lo up
        echo "  [ns] loopback up; no other interface, no route out:"
        ip -brief addr | sed 's/^/      /'
        echo "  [ns] BYPASS PROBE (external connect must fail):"
        if timeout 3 bash -c 'exec 3<>/dev/tcp/1.1.1.1/443' 2>/tmp/_bp_err; then
            echo "    UNEXPECTED: external network reachable inside namespace"; bp=1
        else
            echo "    unmediated external connect refused: $(cat /tmp/_bp_err)"; bp=0
        fi
        echo "  [ns] FULL INTEGRATION (must pass its own N/N):"
        "$PY" "$H"; hp=$?
        echo "  [ns] result: bypass_refused=$([ $bp -eq 0 ] && echo yes || echo NO) harness_rc=$hp"
        [ $bp -eq 0 ] && [ $hp -eq 0 ]
INNER
    local rc=$?
    if [ $rc -eq 0 ]; then echo "  >> $label: STRUCTURAL PASS (egress refused + repair passed)"
    else echo "  >> $label: FAIL (rc=$rc) -- inspect the [ns] lines above"; fi
    return $rc
}

declare -A RESULT
run_one "FW-A LangGraph"     ../probes/.venv/bin/python        e2e/e2e_langgraph.py     langgraph;       RESULT[A]=$?
run_one "FW-B LlamaIndex"    ../probes/.venv/bin/python        e2e/e2e_llamaindex.py    llama_index;     RESULT[B]=$?
run_one "FW-C MSAF"          ../probes/.venv/bin/python        e2e/e2e_msaf.py          agent_framework; RESULT[C]=$?
run_one "FW-D OpenAI Agents" ../probes/.venv/bin/python        e2e/e2e_openai_agents.py agents;          RESULT[D]=$?
run_one "FW-E CrewAI"        ../probes/.venv-crewai/bin/python e2e/e2e_crewai.py        crewai;          RESULT[E]=$?

echo "======================================================================"
echo "STRUCTURAL-MEDIATION SUMMARY (0=structural pass, 2=skipped, other=fail):"
for k in A B C D E; do printf "  FW-%s: %s\n" "$k" "${RESULT[$k]:-?}"; done
echo "A structural pass means: inside the namespace an unwrapped tool's egress is"
echo "kernel-refused AND the framework repair still passes -- complete mediation"
echo "enforced by the OS, not by wrapper discipline."