# Experiment 2 — naturalistic-scale exposure

**Addresses:** the base-rate concern (reviewers B-6 / D-4 / R-F): the authored
tasks create the leak conditions, and τ-bench's retail/airline episodes are
serialize-heavy, so "how often does the shape arise on *naturalistic* tasks?"
is open. This measures it on code-agent (SWE-bench-style) and web-agent
(WebArena-style) tasks, scored **identically** to the exposure/τ-bench arms.

**Status:** the harness + scorer are **built and self-tested offline** (no keys).
The headline number needs a **live run with your API keys** (the `--live` cell),
exactly like the exposure arms.

## Run
```bash
python3 naturalistic_exposure.py --selftest        # validates the scorer (no keys)  -> PASSES

# headline (needs keys): drive a real model on naturalistic tasks
OPENAI_API_KEY=... python3 naturalistic_exposure.py --live --provider openai \
    --model gpt-4o --source code --n 100 --out results/naturalistic_code_gpt4o.jsonl

# or score existing SWE-bench/WebArena agent logs without re-running:
python3 naturalistic_exposure.py --trace your_agent_runs.jsonl --out results/scored.jsonl
```

Point `--tasks tasks.jsonl` at real SWE-bench / WebArena prompts for the
headline; the built-in `--source {code,web}` templates are for a quick run.

## What the receipt must show (for the paper)
A pooled `benign_sibling` exposure rate over N≥100 naturalistic runs per source,
per model — the naturalistic analog of the exposure table. Any non-trivial rate
strengthens "latent but reachable"; a near-zero rate is *also* publishable (it
extends the τ-bench serialization finding to code/web tasks). Either way the
base-rate question stops resting on τ-bench alone.

Rows share the taubench_exposure schema, so `reproduce.sh` can audit the pooled
rate the same way it audits the `0/71` τ-bench null.