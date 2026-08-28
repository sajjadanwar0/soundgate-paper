#!/usr/bin/env bash
# r1_2_runs.sh -- staged runner for the R1-2 extension (more naturalistic +
# longer multi-turn live evaluation). Run from the repo root. Keys come from
# soundgate/.env (never paste keys anywhere else).
#
#   ./scripts/r1_2_runs.sh selftest              # free; no API
#   ./scripts/r1_2_runs.sh probe deepseek        # ~5 episodes; calibrates cost
#   ./scripts/r1_2_runs.sh probe openai
#   ./scripts/r1_2_runs.sh probe anthropic       # needs ANTHROPIC_MODEL=<id from your console>
#   CAP=4000000 ./scripts/r1_2_runs.sh full deepseek
#   CAP=2000000 ./scripts/r1_2_runs.sh full openai
#   CAP=1200000 ANTHROPIC_MODEL=<id> ./scripts/r1_2_runs.sh full anthropic
#   ./scripts/r1_2_runs.sh depth                 # long-conversation arm (openai)
#
# PROTOCOL (precision over spend):
#  1. selftest (free).  2. probe ONE provider; read the provider dashboard
#  delta; divide by 5 for cost/episode.  3. Set CAP (agent-side token ceiling;
#  the harness stops cleanly at the cap) and run `full`.  The cap covers the
#  AGENT model only -- the tau-bench user simulator bills separately, roughly
#  the same order; watch the dashboard.  4. Receipts land in
#  soundgate/evidence/taubench_ext_<provider>_<env>.txt; paste them back.
set -euo pipefail
cd "$(dirname "$0")/.."
E2E=soundgate/e2e
EV=soundgate/evidence
RES=soundgate/results
mkdir -p "$EV" "$RES"
[ -f soundgate/.env ] && set -a && . soundgate/.env && set +a

agent_args() {  # agent_args <provider> -> MODEL PROVIDER USERM USERP
  case "$1" in
    openai)    echo "gpt-4o openai gpt-4o-mini openai";;
    deepseek)  echo "deepseek-chat deepseek deepseek-chat deepseek";;
    anthropic) [ -n "${ANTHROPIC_MODEL:-}" ] || { echo "set ANTHROPIC_MODEL=<model id from your console>" >&2; exit 2; }
               echo "${ANTHROPIC_MODEL} anthropic gpt-4o-mini openai";;
    *) echo "unknown provider $1" >&2; exit 2;;
  esac
}

run_env() {  # run_env <provider> <env> <start> <end> <cap> <tag>
  read -r MODEL PROV USERM USERP < <(agent_args "$1")
  python3 "$E2E/taubench_exposure.py" run \
    --env "$2" --provider "$PROV" --model "$MODEL" \
    --user-provider "$USERP" --user-model "$USERM" \
    --start "$3" --end "$4" --max-agent-tokens "$5" \
    --out "$RES/taubench_ext_$1_$2.jsonl" --append \
    --receipt "$EV/taubench_ext_$1_$2.txt"
}

cmd="${1:-}"; shift || true
case "$cmd" in
  selftest)
    python3 "$E2E/taubench_exposure.py" run --self-test
    python3 "$E2E/naturalistic_exposure.py" --selftest
    python3 "$E2E/naturalistic_exposure.py" --live --provider mock --n 2 \
      --preamble-turns 12 --out /tmp/depth_selftest.jsonl >/dev/null
    echo "depth-arm mock e2e: OK"
    ;;
  probe)
    p="${1:?probe which provider?}"
    echo "== PROBE: 5 retail episodes on $p; then read the $p dashboard delta =="
    run_env "$p" retail 0 5 300000 probe
    echo "== now: dashboard delta / 5 = cost per episode; choose CAP and run 'full' =="
    ;;
  full)
    p="${1:?full which provider?}"; : "${CAP:?set CAP=<agent-token ceiling>}"
    echo "== FULL: $p retail 5..115 then airline 0..50, agent-token cap $CAP per environment (2x CAP across both) =="
    run_env "$p" retail 5 115 "$CAP" full
    run_env "$p" airline 0 50 "$CAP" full
    echo "== receipts: $EV/taubench_ext_${p}_retail.txt, $EV/taubench_ext_${p}_airline.txt =="
    ;;
  depth)
    echo "== DEPTH ARM: 5 multi-effect ops x 25 runs, 12-pair read-only preamble, gpt-4o =="
    ( cd "$E2E" && python3 naturalistic_exposure.py --live --provider openai \
        --model gpt-4o --n 25 --preamble-turns 12 \
        --out "../results/naturalistic_depth_gpt4o.jsonl" ) \
      | tee "$EV/naturalistic_depth_gpt4o.txt"
    echo "== compare HEADLINE above against the depth-0 study (500/500 parallel) =="
    ;;
  *) echo "usage: $0 selftest | probe <provider> | full <provider> | depth"; exit 2;;
esac
