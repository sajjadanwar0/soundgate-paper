# soundgate — artifact monorepo

Companion artifact for *"Stop Means Stop: Measuring and Repairing the
Enforcement Gap in Agent-Framework Control Primitives."*

Three independent components, one repository:

- **`probes/`** — model-free Python probes that *measure* framework
  control-plane semantics: LangGraph, LlamaIndex, Microsoft Agent Framework,
  OpenAI Agents SDK, CrewAI. Managed with **uv**. No API keys.
- **`probes-js/`** — the same probe design on **LangGraph.js** (Node), to
  separate framework semantics from host-language concurrency semantics.
- **`soundgate/`** — the Rust *reference gate* that repairs the measured
  violations, plus a Python end-to-end harness that drives it.

```
soundgate-monorepo/
├── README.md                      # this file
├── STEP-BY-STEP.md                # every command, end to end
├── paper/                         # IEEE Computer Society manuscript
│   ├── soundgate.tex          # single file: bibliography inline (no .bib)
│   └── figures/
├── probes/                        # Python measurement suite (uv)
│   ├── pyproject.toml             # per-framework extras + [tool.uv] conflicts
│   ├── uv.lock                    # frozen resolution (committed)
│   ├── README.md
│   ├── src/agentprobe/
│   │   ├── __init__.py
│   │   ├── _harness.py            # shared: event log, tally, ProbeResult
│   │   ├── langgraph_probes.py    # FW-A
│   │   ├── llamaindex_probes.py   # FW-B
│   │   ├── msaf_probes.py         # FW-C
│   │   ├── openai_agents_probes.py# FW-D (scripted-model stub, keyless)
│   │   └── crewai_probes.py       # FW-E (isolated venv; see pyproject)
│   ├── tests/
│   │   ├── test_harness.py
│   │   └── test_probe_verdicts.py # regression guards: pinned verdict maps
│   ├── scripts/
│   │   └── check_crewai_verdicts.py # same guard, for the isolated crewai venv
│   └── results/                   # committed probe outputs (evidence)
│       ├── MATRIX.md              # consolidated 6-framework matrix
│       ├── langgraph_py.txt  llamaindex.txt  msaf.txt
│       ├── openai_agents.txt crewai.txt      langgraph_js.txt
│       ├── reps/                  # 5x determinism logs per suite
│       └── env/                   # exact freezes verdicts were recorded under
├── corpus/                        # Phase 2: public incident corpus (prevalence evidence, no keys)
│   ├── pyproject.toml             # zero-dep uv project
│   ├── README.md
│   ├── src/corpus/{seeds,render,enrich}.py
│   └── results/{INCIDENTS.md, incidents.jsonl, incidents_enriched.jsonl}
├── probes-js/                     # FW-F LangGraph.js suite (Node >= 18)
│   ├── package.json               # `npm run probe`
│   ├── package-lock.json
│   └── langgraph_probes.mjs
└── soundgate/                     # Rust gate + e2e (Cargo)
    ├── Cargo.toml
    ├── Cargo.lock
    ├── README.md
    ├── src/
    │   ├── lib.rs                 # gate core: identity=(run_id,effect_key); 11 tests
    │   └── main.rs                # line-delimited JSON TCP server
    ├── benches/
    │   └── admission.rs           # Criterion per-effect latency (build phase)
    └── e2e/
        └── e2e_test.py            # replays violations through the live gate
```

## Quickstart (no API keys anywhere)

### 1. Measure — Python suites (uv)
```bash
cd probes
uv sync --extra msaf --extra openai-sdk
uv run --no-sync agentprobe-langgraph    # FW-A
uv run --no-sync agentprobe-llamaindex   # FW-B
uv run --no-sync agentprobe-msaf         # FW-C
uv run --no-sync agentprobe-openai       # FW-D
uv run --no-sync pytest

# FW-E in its own env (crewai downgrades 8 pinned packages; kept isolated)
UV_PROJECT_ENVIRONMENT=.venv-crewai uv sync --extra crewai
CREWAI_DISABLE_TELEMETRY=true OTEL_SDK_DISABLED=true \
  UV_PROJECT_ENVIRONMENT=.venv-crewai uv run --no-sync agentprobe-crewai
```

### 2. Measure — LangGraph.js suite (Node)
```bash
cd probes-js
npm ci
npm run probe                            # FW-F
```

### 3. Repair (Rust)
```bash
cd soundgate
cargo test --release          # 11/11: 7 property tests + 4 G1 regression tests
cargo build --release
python3 e2e/e2e_test.py        # live gate: 5/5 blocked/scoped (incl. G1 cross-run) + contrast
```

### 4. Build the paper
```bash
cd paper
latexmk -pdf soundgate.tex     # needs IEEEtran.cls (TeX Live full, or `tlmgr install ieeetran`)
```

## Headline matrix (details: `probes/results/MATRIX.md`)

| Axis                       | LangGraph | LlamaIndex | MS AF | OpenAI SDK | CrewAI | LangGraph.js |
|----------------------------|-----------|------------|-------|------------|--------|--------------|
| Sibling leak while pending | V         | V          | V     | V          | n/a*   | V            |
| Reject after effect        | V         | V          | V     | V          | V*     | V            |
| Resume replay (1→2)        | V         | NP         | clean | clean      | NP     | V            |
| Cancel (thread)            | V         | NP         | V     | V          | V      | n/a          |
| Cancel (pure async)        | clean     | NP         | clean | clean      | NP     | **V**        |
| Timeout                    | V(host)   | clean      | V(host)| clean/R   | V(A4b) | V(native)    |

\* CrewAI OSS has no pre-execution approval; its row is the by-design
post-hoc variant. A4b = new class: timeout blocks caller past deadline and
the effect lands anyway. R = unsound configuration refused at construction.

## Reproducibility notes
- Every result in the paper comes from a committed file under
  `probes/results/` or `soundgate/e2e/`. Regenerate with the commands above.
- Framework versions are pinned per extra in `probes/pyproject.toml` and
  frozen in `probes/uv.lock` / `probes-js/package-lock.json`; the exact
  closures the recorded verdicts were captured under are in
  `probes/results/env/`.
- Verdicts reproduced identically across 5/5 reps per suite (30/30 for the
  FW-A core probes), and the FW-C/FW-D/FW-E suites additionally reproduced
  from a from-scratch `uv sync` of the lockfile in a separate directory.
- The probes are deterministic and model-free: no network, no LLM, no keys.