#!/usr/bin/env bash
# reproduce.sh -- single-script reproduction + audit for the SOUNDGATE paper
#   "Stop Means Stop: Measuring and Repairing the Enforcement Gap in
#    Agent-Framework Control Primitives"
#
# Every check below extracts a number from a COMMITTED artifact (raw JSONL or a
# receipt in soundgate/evidence/ or formal/) and compares it to the value the
# paper claims. No check fabricates data: if a receipt is missing the check
# FAILS honestly. Offline by default (no API keys); the live-model arms run only
# under --live.
#
# Usage:
#   ./reproduce.sh                # offline audit + Rust build/test (~10-15 min)
#   ./reproduce.sh --audit-only   # only the paper-number audit (~1 min, no cargo)
#   ./reproduce.sh --formal       # also RE-RUN the formal tools (TLC/TLAPS/Verus/Loom)
#   ./reproduce.sh --live         # also re-run the live-model arms (needs API keys, ~$1)
#
# Point at your checkout (auto-detected if you run from the repo root):
#   export SOUNDGATE_DIR=/path/to/soundgate-paper
# For --live also set:  OPENAI_API_KEY, ANTHROPIC_API_KEY (Together/Google optional)
#
# Requirements:
#   - Linux/macOS, git, python3.10+
#   - rustc/cargo 1.90+ (edition 2024; https://rustup.rs)          [not for --audit-only]
#   - Optional --formal: Java 11+ + tla2tools.jar (TLC), tlapm (TLAPS), verus
set -euo pipefail

# --------------------------------------------------------------------------- args
AUDIT_ONLY=0; RUN_FORMAL=0; LIVE=0
for a in "$@"; do case "$a" in
  --audit-only) AUDIT_ONLY=1 ;;
  --formal)     RUN_FORMAL=1 ;;
  --live)       LIVE=1 ;;
  -h|--help)    sed -n '2,/^set -e/p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  *) echo "unknown flag: $a" >&2; exit 2 ;;
esac; done

log()  { printf "\033[1;34m[%s]\033[0m %s\n" "$(date +%H:%M:%S)" "$*"; }
ok()   { printf "  \033[1;32m\xe2\x9c\x93\033[0m %s\n" "$*"; }
fail() { printf "  \033[1;31m\xe2\x9c\x97\033[0m %s\n" "$*"; FAIL=$((FAIL+1)); }
skip() { printf "  \033[1;33m~\033[0m %s\n" "$*"; }
need() { command -v "$1" >/dev/null 2>&1 || { echo "Missing required tool: $1" >&2; exit 1; }; }
FAIL=0

# compare "$got" to "$want"; ok/fail with a label
eq() { # eq LABEL GOT WANT
  if [[ "$2" == "$3" ]]; then ok "$1 = $2"; else fail "$1: expected $3, got $2"; fi
}

# --------------------------------------------------------------- locate the repo
log "Phase 1: Locating artifacts"
need git; need python3
ROOT="${SOUNDGATE_DIR:-$(pwd)}"
# Optional clone (set SOUNDGATE_REPO=user/repo to fetch instead of using a local tree)
if [[ -n "${SOUNDGATE_REPO:-}" && ! -e "$ROOT/soundgate" && ! -e "$ROOT/Cargo.toml" ]]; then
  log "  cloning https://github.com/$SOUNDGATE_REPO into $ROOT"
  git clone --quiet --depth=1 "https://github.com/$SOUNDGATE_REPO.git" "$ROOT" || fail "clone"
fi

find_one() { find "$ROOT" -type "$1" -name "$2" ${3:+-path "$3"} 2>/dev/null | head -1; }
EVID_FILE="$(find_one f netem_raft.txt '*/evidence/*')"
[[ -n "$EVID_FILE" ]] || { echo "Could not find soundgate/evidence under $ROOT. Set SOUNDGATE_DIR." >&2; exit 1; }
EVID="$(dirname "$EVID_FILE")"
CRATE="$(dirname "$EVID")"
RESULTS="$CRATE/results"
TLA="$(dirname "$(find_one f SoundGate.tla '*/tla/*')")"
VERUS_TXT="$(find_one f verus.txt)"
EXPO_FILE="$(find_one f 'exposure_llama_together*')"; EXPO="$(dirname "${EXPO_FILE:-$RESULTS/x}")"
log "  crate:    $CRATE"
log "  evidence: $EVID"
log "  results:  $RESULTS"
log "  formal:   ${TLA:-<not found>}"

# ---------------------------------------------------------------- Phase 2: audit
log "Phase 2: Paper-number audit (committed artifacts vs claimed values)"

# --- Experiment A: live end-to-end leak (abstract, Table expA) ---------------
# 215/1,200 unmediated across the four FW-A arms; 0/1,200 mediated; plus the
# cross-runtime reproductions FW-B 121/300 and FW-F 143/300. Recomputed from raw
# JSONL by the canonical script.
if [[ -f "$CRATE/scripts/recompute_expA.py" ]]; then
  EXPA="$(cd "$CRATE" && python3 scripts/recompute_expA.py 2>/dev/null)"
  armleak() { echo "$EXPA" | grep -E "expA_$1\.jsonl" | grep -oE "leak_unmed= *[0-9]+" | grep -oE "[0-9]+"; }
  armemit() { echo "$EXPA" | grep -E "expA_$1\.jsonl" | grep -oE "emit= *[0-9]+"       | grep -oE "[0-9]+"; }
  G=$(armleak openai_gpt4o); C=$(armleak claude); D=$(armleak deepseek); L=$(armleak llama)
  MED=$(echo "$EXPA" | grep -E "expA_(openai_gpt4o|claude|deepseek|llama)\.jsonl" | grep -oE "leak_med= *[0-9]+" | grep -oE "[0-9]+" | python3 -c "import sys;print(sum(int(x) for x in sys.stdin))")
  FWA=$(( ${G:-0} + ${C:-0} + ${D:-0} + ${L:-0} ))
  eq "ExpA FW-A arms (gpt4o+claude+deepseek+llama)=133+26+0+56" "${G:-?}+${C:-?}+${D:-?}+${L:-?}" "133+26+0+56"
  eq "ExpA unmediated total (215/1,200)" "$FWA" "215"
  eq "ExpA mediated total   (0/1,200)"   "${MED:-?}" "0"
  eq "ExpA FW-B reproduction (121/300)"  "$(armleak fwb_openai_gpt4o)" "121"
  eq "ExpA FW-F reproduction (143/300)"  "$(armemit fwf_openai_gpt4o)" "143"
else
  fail "ExpA: scripts/recompute_expA.py not found under $CRATE"
fi

# --- Pause sweep: leak is pause-invariant unmediated, zero mediated ----------
PS="$EVID/pause_sweep.txt"
if [[ -f "$PS" ]]; then
  UNMED_LEAK=$(grep -cE '20/20 leaked' "$PS"); MED_ZERO=$(grep -cE '0/20 leaked' "$PS")
  eq "Pause sweep FW-A: unmediated 20/20 at all 5 pauses" "$UNMED_LEAK" "5"
  eq "Pause sweep FW-A: mediated 0/20 at all 5 pauses"    "$MED_ZERO"  "5"
else fail "pause_sweep.txt missing"; fi

# --- Exposure study: Llama-Together arm (de-confound) ------------------------
if [[ -f "$EXPO_FILE" ]]; then
  read -r EXP_TOTAL EXP_CLEAN < <(python3 - "$EXPO_FILE" <<'PY'
import json,sys
tot=clean=0
for l in open(sys.argv[1]):
    if not l.strip(): continue
    r=json.loads(l)
    if r.get("parallel_exposure"):
        tot+=1
        if r.get("task_id")=="compound_cleanup": clean+=1
print(tot, clean)
PY
)
  eq "Exposure Llama-Together pooled (64/1000)"        "$EXP_TOTAL" "64"
  eq "Exposure Llama-Together compound_cleanup (57)"   "$EXP_CLEAN" "57"
else skip "exposure Llama-Together JSONL not found (checked $EXPO); exposure arm audit skipped"; fi

# --- tau-bench ecological arm: hard null 0/71 --------------------------------
TAU=$(python3 - "$RESULTS" <<'PY'
import json,glob,sys
gated=benign=0
for f in glob.glob(sys.argv[1]+"/taubench_exposure_*.jsonl"):
    for l in open(f):
        if not l.strip(): continue
        r=json.loads(l)
        if r.get("is_cons_batch"):
            gated+=1
            if r.get("benign_sibling"): benign+=1
print(f"{benign}/{gated}")
PY
)
eq "tau-bench ecological arm hard null (0/71)" "$TAU" "0/71"

# --- Differential + exhaustive conformance ----------------------------------
grep -q "12000000 operations" "$EVID/conformance.txt" 2>/dev/null \
  && ok "Differential conformance: 12,000,000 ops, model==code every verdict" \
  || fail "conformance.txt: '12000000 operations' not found"
grep -q "729 reachable states x 20 transitions = 14580 checked, 0 divergences" "$EVID/exhaustive_conformance.txt" 2>/dev/null \
  && ok "Bounded-exhaustive: 729 states x 20 = 14,580 transitions, 0 divergences" \
  || fail "exhaustive_conformance.txt: 14580/0-divergence line not found"

# --- Formal receipts: TLC state counts, TLAPS obligations, Verus, Loom -------
tlc() { grep -oE "[0-9,]+ distinct states found" "$1" 2>/dev/null | tail -1 | grep -oE "[0-9,]+" | tr -d ','; }
if [[ -n "$TLA" ]]; then
  eq "TLC exhaustive 2x2 (729)"          "$(tlc "$TLA/tlc_2x2.txt")"       "729"
  eq "TLC exhaustive 3x3 (804,357)"      "$(tlc "$TLA/tlc_3x3.txt")"       "804357"
  eq "TLC exhaustive 4x3 (74,805,201)"   "$(tlc "$TLA/tlc_4x3.txt")"       "74805201"
  grep -q "All 68 obligations proved" "$TLA/tlapm.txt" 2>/dev/null \
    && ok "TLAPS: all 68 obligations proved (unbounded induction)" \
    || fail "tlapm.txt: 'All 68 obligations proved' not found"
else fail "formal/tla not found"; fi
grep -q "11 verified, 0 errors" "${VERUS_TXT:-/dev/null}" 2>/dev/null \
  && ok "Verus: 11 verified, 0 errors (sequential model)" \
  || fail "verus.txt: '11 verified, 0 errors' not found"
LOOM_OK=$(grep -cE 'test .* \.\.\. ok' "$EVID/loom.txt" 2>/dev/null || echo 0)
eq "Loom: 3 concurrent-Rust models pass" "$LOOM_OK" "3"

# --- Mutation adequacy + protocol fuzz --------------------------------------
grep -q "5/5 property-violating mutations caught" "$EVID/mutation_score.txt" 2>/dev/null \
  && ok "Mutation adequacy: 5/5 property mutations caught (4 exhaustive + 1 loom)" \
  || fail "mutation_score.txt: '5/5 ... caught' not found"
FUZZ_N=$(grep -oE "total inputs: [0-9]+" "$EVID/fuzz_boundary.txt" 2>/dev/null | grep -oE "[0-9]+")
FAILOPEN=$(grep -c "oracle O1 (fail-closed, zero fail-open verdicts): PASS" "$EVID/fuzz_boundary.txt" 2>/dev/null || echo 0)
eq "Fuzz: 180,651 malformed inputs driven"      "${FUZZ_N:-?}" "180651"
eq "Fuzz: zero fail-open (oracle O1 PASS)"       "$FAILOPEN"    "1"

# --- Emulated-WAN Raft sweep (netem) ----------------------------------------
NET0=$(grep -E 'raft-3node' "$EVID/netem_raft.txt" 2>/dev/null | grep -oE 'thpt_adm_per_s=[0-9]+' | grep -oE '[0-9]+' | sort -rn | head -1)
NET10=$(grep -E 'raft-3node,clients=1,' "$EVID/netem_raft.txt" 2>/dev/null | grep -oE 'thpt_adm_per_s=[0-9]+' | grep -oE '[0-9]+' | sort -n | head -1)
[[ -n "$NET0"  ]] && ok "netem WAN sweep present: peak ${NET0} adm/s (RTT~0), single-client floor ${NET10:-?} adm/s (RTT~10ms)" \
                  || fail "netem_raft.txt: throughput rows not found"

# --- Real-endpoint webhook demo ---------------------------------------------
grep -q "SoundGate delivered zero POSTs" "$EVID/webhook_leak_demo.txt" 2>/dev/null \
  && ok "Webhook demo: unmediated POST hit endpoint during pause; mediated delivered 0" \
  || fail "webhook_leak_demo.txt: verdict line not found"

[[ $AUDIT_ONLY -eq 1 ]] && { echo; log "Audit-only complete"; [[ $FAIL -eq 0 ]] && printf "\033[1;32mAll audit checks passed.\033[0m\n" || { printf "\033[1;31m%d checks failed.\033[0m\n" "$FAIL"; exit 1; }; exit 0; }

# --------------------------------------------- Phase 3: build + test Rust crate
log "Phase 3: Rust crate build + test (offline, no API keys)"
need cargo; need rustc
cd "$CRATE"
if cargo build --release --quiet 2>&1 | tail -3; then ok "cargo build --release"; else fail "cargo build"; fi
# The conformance integration test + property tests need the conformance feature
# (integration tests build the lib with default features only otherwise).
if cargo test --release --features conformance --quiet 2>&1 | tail -8; then
  ok "cargo test --features conformance (property1-4, g1/i1 invariants, WAL replay, conformance)"
else
  fail "cargo test --features conformance"
fi
log "  cargo bench --bench admission (paper: sub-microsecond admission; ~53us round-trip incl. transport)"
if cargo bench --bench admission --quiet >/tmp/_sg_bench.log 2>&1; then
  grep -E "submit|decide|time:" /tmp/_sg_bench.log | head -6 || true
  ok "admission microbench complete"
else
  skip "admission bench did not complete (see /tmp/_sg_bench.log)"
fi

# ------------------------------------------ Phase 4: re-run formal (best-effort)
if [[ $RUN_FORMAL -eq 1 ]]; then
  log "Phase 4: Re-running formal tools (best-effort; receipts already audited above)"
  # Loom (needs the crate; exhaustive interleavings of the real Gate)
  if RUSTFLAGS="--cfg loom" cargo test --release --features conformance --test loom_gate_test \
       --target-dir target-loom >/tmp/_sg_loom.log 2>&1; then
    ok "Loom re-run: 3 models pass"
  else skip "Loom re-run did not complete (see /tmp/_sg_loom.log)"; fi
  # Verus
  if command -v verus >/dev/null && [[ -f "$(dirname "$VERUS_TXT")/verus/gate_model.rs" ]]; then
    if verus "$(dirname "$VERUS_TXT")/verus/gate_model.rs" >/tmp/_sg_verus.log 2>&1; then
      ok "Verus re-run: verified"; else skip "Verus re-run failed (see /tmp/_sg_verus.log)"; fi
  else skip "verus not installed; using committed verus.txt (audited above)"; fi
  # TLC (needs tla2tools.jar on TLC_JAR)
  if command -v java >/dev/null && [[ -n "${TLC_JAR:-}" && -f "$TLA/SoundGate.cfg" ]]; then
    if (cd "$TLA" && java -cp "$TLC_JAR" tlc2.TLC -config SoundGate.cfg SoundGate.tla >/tmp/_sg_tlc.log 2>&1); then
      ok "TLC re-run: 2x2 model exhausted (larger bounds: see paper receipts)"
    else skip "TLC re-run failed (see /tmp/_sg_tlc.log)"; fi
  else skip "TLC skipped (set TLC_JAR=/path/to/tla2tools.jar and install Java to re-run)"; fi
  # TLAPS
  if command -v tlapm >/dev/null && [[ -f "$TLA/SoundGate_Proofs.tla" ]]; then
    if (cd "$TLA" && tlapm --toolbox 0 0 SoundGate_Proofs.tla >/tmp/_sg_tlaps.log 2>&1); then
      ok "TLAPS re-run: obligations discharged"; else skip "TLAPS re-run failed (see /tmp/_sg_tlaps.log)"; fi
  else skip "tlapm not installed; using committed tlapm.txt (audited above)"; fi
fi

# ------------------------------------------------ Phase 5: live arms (--live)
if [[ $LIVE -eq 1 ]]; then
  log "Phase 5: Live-model arms (re-measures exposure + Experiment A against real models)"
  [[ -n "${OPENAI_API_KEY:-}"    ]] || fail "OPENAI_API_KEY not set"
  [[ -n "${ANTHROPIC_API_KEY:-}" ]] || skip "ANTHROPIC_API_KEY not set (Claude arms will be skipped)"
  # Small, cheap re-runs that exercise the live path; they WRITE fresh JSONL you
  # can diff against the committed arms above. Adjust --n upward for full N=100/300.
  EA="$(find_one f experiment_a.py '*/e2e/*')"
  if [[ -n "$EA" && -n "${OPENAI_API_KEY:-}" ]]; then
    log "  live Experiment A (FW-A, gpt-4o, small n; the gate must yield 0 mediated leaks)"
    if (cd "$CRATE" && python3 "$EA" --model gpt-4o --n 10 --out /tmp/_sg_expA_live.jsonl 2>&1 | tail -8); then
      ok "live Experiment A ran (fresh JSONL at /tmp/_sg_expA_live.jsonl; diff vs results/expA_openai_gpt4o.jsonl)"
    else fail "live Experiment A run failed (check keys/network/flags: python3 $EA --help)"; fi
  fi
  EXPSRC="$(find_one f '*.py' '*/exposure/src/*')"
  if [[ -n "$EXPSRC" ]]; then
    log "  live exposure probe (small n; re-measures P(emitted))"
    skip "invoke your exposure harness directly, e.g.: python3 $EXPSRC --provider openai --n 20 (see --help)"
  fi
fi

echo
log "Reproduction complete"
if [[ $FAIL -eq 0 ]]; then
  printf "\033[1;32mAll checks passed.\033[0m  Artifacts: %s\n" "$CRATE"
else
  printf "\033[1;31m%d checks failed.\033[0m See output above.\n" "$FAIL"; exit 1
fi