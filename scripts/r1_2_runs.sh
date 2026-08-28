#!/usr/bin/env bash

set -euo pipefail
cd "$(dirname "$0")/.."
E2E=soundgate/e2e
EV=soundgate/evidence
RES=soundgate/results
mkdir -p "$EV" "$RES"
[ -f soundgate/.env ] && set -a && . soundgate/.env && set +a

agent_args() {
  case "$1" in
    openai)    echo "gpt-4o openai gpt-4o-mini openai";;
    deepseek)  echo "deepseek-chat deepseek deepseek-chat deepseek";;
    anthropic) [ -n "${ANTHROPIC_MODEL:-}" ] || { echo "set ANTHROPIC_MODEL=<model id from your console>" >&2; exit 2; }
               echo "${ANTHROPIC_MODEL} anthropic gpt-4o-mini openai";;
    *) echo "unknown provider $1" >&2; exit 2;;
  esac
}

run_env() {
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
