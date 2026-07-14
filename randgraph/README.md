# R1 — Randomized-workflow barrier sweep

Kills the "handcrafted probes" objection (hostile review batch 3) by replacing
authored witnesses with 1,000 seeded random workflows and showing the sibling
leak is exactly a *structural schedulability law*, not an artifact of probe
construction.

## Protocol

1. `gen.py --n 1000 --seed 7` — seeded random out-tree workflows
   (3–8 nodes, in-degree ≤ 1 to keep join semantics out of the sweep — a
   deliberate scope restriction, state it in the paper), exactly one approval
   gate placed uniformly at random, 1–3 effect nodes, remainder reads. Each
   effect is pre-classified by its relation to the gate: ancestor /
   descendant / concurrent-{earlier,same,later}-wave (wave = depth from START).
2. `run_fwa.py` — compiles each spec to a real LangGraph `StateGraph`
   (checkpointer + `interrupt()` in the gate node, timestamped in-process
   effect log), runs `invoke()` → snapshot at pause → `Command(resume="approve")`
   → final log. Keyless, model-free, deterministic.
3. `analyze.py` — leak rate per structural bucket with Wilson 95% CIs,
   plus two incidental checks: gate-node re-execution count on resume
   (FW-A's documented replay behavior) and per-effect execution counts.

## Verified result (this exact code, langgraph==1.2.7, seed=7, N=1000)

The committed `results_fwa.jsonl` was generated on 2026-07-10;
`env_versions.txt` records the exact package versions used.

| relation      | leak / n   | rate | Wilson 95% CI  |
|---------------|-----------|------|----------------|
| conc_same     | 577/577   | 1.00 | [0.993, 1.000] |
| conc_later    | 0/331     | 0.00 | [0.000, 0.011] |
| descendant    | 0/363     | 0.00 | [0.000, 0.010] |

`conc_earlier` (298) and `ancestor` (363) effects all executed strictly
*before* the gate node was entered (every dt < 0, median ≈ −1.05 ms) — outside
the B1 window by construction; report them as pre-gate, never as leaks.
All 1,000 graphs paused at the gate; the gate node body ran exactly twice in
all 1,000 (resume re-executes from node start — the documented FW-A replay
behavior, reconfirmed at scale); all 1,932 effect nodes executed exactly once.

## Reading for the paper

Three sentences, one new cell:

- Every same-superstep concurrent effect leaked (577/577) — Table 2's ✓
  becomes a quantified law over random topologies.
- Every gate-descendant effect held (0/363) — internal control: the sweep is
  not rigged, the framework enforces topological ordering correctly.
- **New finding**: later-wave concurrent effects never executed during the
  pause (0/331) — the interrupt halts the Pregel loop after the raising
  superstep, so the leak window is *exactly* the superstep that raises the
  pause, sharpening §3.3's mechanism reading into a measured boundary.

## What the committed run shows

The sweep drives 1,000 seeded random workflows (3–8 nodes, one gate, 1–3
effects, in-degree ≤ 1) through the real FW-A runtime and classifies every
effect by its graph relation to the paused gate. In the committed
`results_fwa.jsonl`:

- effects **concurrent** with the gate's superstep execute during the pause in
  **577/577** cases (Wilson [0.99, 1.00]);
- **gate-descendant** effects are withheld until the decision — **0/363**;
- effects on concurrent branches scheduled in **later** supersteps never
  execute during the pause — **0/331**.

The leak is exactly the schedulability predicate of the pausing superstep,
independent of topology — establishing that the sibling leak is deterministic,
not an artifact of the authored probes. These three fractions are what
`reproduce.sh --audit-only` checks.

## Reproduce

```bash
python3 gen.py --n 1000 --seed 7 && python3 run_fwa.py && python3 analyze.py
```

~1 minute, no API keys. `env_versions.txt` records the exact package versions
of the committed run. The generator targets the runtime whose topology is
user-specified (FW-A/LangGraph); the other execution models are covered by the
per-framework witnesses in `probes/` and `probes-js/`.
