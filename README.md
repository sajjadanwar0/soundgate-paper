# SOUNDGATE

Companion artifact for **"Stop Means Stop: Measuring and Repairing the
Enforcement Gap in Agent-Framework Control Primitives."**

Production LLM-agent frameworks expose control primitives — human-in-the-loop
approval gates, run cancellation, execution timeouts — whose names and docs
imply *barrier* semantics: while a run is paused/cancelled/timed-out, no gated
side effect executes. This artifact **measures** that the implied contract does
not hold across six frameworks, and **repairs** it with SOUNDGATE, a small
environment-external effect gate (Rust) whose four properties are mechanically
verified over a model and differentially tested against the deployed code.

## Reproduce in one command

```bash
./reproduce.sh --audit-only     # ~1 min: check every paper number against its committed receipt
./reproduce.sh                  # full offline reproduction (+ cargo build/test/bench)
./reproduce.sh --formal         # also re-run TLC / TLAPS / Verus / Loom (best-effort)
./reproduce.sh --live           # also re-run the live-model arms (needs API keys; see .env.example)
```

The offline path needs **no API keys**. Every check compares a committed
artifact (raw JSONL or an `evidence/` receipt) to the value claimed in the
paper; a missing or drifted receipt fails loudly.

## Repository layout

| Folder | What it is | Stack | Keys? |
|---|---|---|---|
| [`probes/`](probes/) | Model-free differential probes that **measure** the control-plane gap across LangGraph, LlamaIndex, MS Agent Framework, OpenAI Agents SDK, CrewAI | Python (uv) | No |
| [`probes-js/`](probes-js/) | The same probe design on **LangGraph.js** (Node), separating framework semantics from host-language concurrency | Node | No |
| [`probes-temporal/`](probes-temporal/) | The Section-3 predicates on **Temporal**, the durable-execution contrast arm (excluded from every recurrence denominator) | Python (uv) | No |
| [`exposure/`](exposure/) | The **model exposure** study: do real models emit the leak-triggering plan shape, and at what rate | Python (uv) | For live re-run |
| [`corpus/`](corpus/) | The verified **public-incident corpus** and the tracker sweep behind the occurrence lower bound | Python (uv) | No |
| [`soundgate/`](soundgate/) | The Rust **reference gate** that repairs the violations, its evidence receipts, the end-to-end integrations, eBPF/namespace mediation, and the Python (PyO3) bindings | Rust + Python | For live e2e |
| [`formal/`](formal/) | **Mechanized verification**: TLA+/TLC + TLAPS models and Verus model, with checker receipts | TLA+ / Verus | No |
| [`randgraph/`](randgraph/) | The **randomized structural sweep**: 1,000 generated workflows establishing the leak is deterministic, not incidental | Python (uv) | No |
| [`prevalence/`](prevalence/) | The **multi-effect prevalence** analysis over τ-bench gold solutions (how many tasks cross an approval gate twice) | Python | No |
| [`scripts/`](scripts/) | The static **mediation linter** (`mediation_lint.py`) | Python | No |
| `paper/` | The manuscript (`soundgate.tex`) | LaTeX | — |

Each folder has its own `README.md` with exact commands.

## Python package (use the gate from Python agents)

The gate is language-independent (line-JSON over TCP). For Python-first
frameworks it also ships as a PyO3 extension and a zero-build pure-Python
client — see [`soundgate/README.md`](soundgate/README.md) and
`soundgate/python-bindings/`.

## What's committed as evidence

Raw per-run JSONL (`*/results/`) and per-claim receipts
(`soundgate/evidence/`, `formal/`) are checked in on purpose: they are the
artifact. `reproduce.sh --audit-only` re-derives the paper's headline numbers
from them.

## Citation

```bibtex
@misc{khan2026soundgate,
  title  = {Stop Means Stop: Measuring and Repairing the Enforcement Gap
            in Agent-Framework Control Primitives},
  author = {Khan, Sajjad},
  year   = {2026},
  note   = {Artifact: https://github.com/sajjadanwar0/soundgate}
}
```

## License

MIT — see [LICENSE](LICENSE).