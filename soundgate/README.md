# `soundgate/` — the reference gate + evidence + integrations

The Rust **environment-external effect gate** that repairs the four measured
violations, plus everything that exercises and verifies it.

## What it is
A small admission core: every side effect is submitted for a verdict and
performed only on `release`. Four properties, one per measured violation class:
hold-until-decided, reject-cancels, dedup-on-replay, fence-on-cancel. The server
speaks line-delimited JSON over TCP, so any language can drive it.

## Layout
- `src/lib.rs` — admission core (`Gate`: `submit`/`decide`/`cancel`/`close_run`).
- `src/main.rs` — the `soundgate` server (line-JSON/TCP; HMAC-authenticated decisions).
- `src/hmac.rs` — HMAC-SHA256 decision tags (RFC 4231 tested).
- `src/bin/`, `src/raft_gate/` — the replicated (Raft) tier and concurrent bench.
- `benches/admission.rs` — Criterion microbenchmarks (per-op admission latency).
- `tests/` — `conformance.rs` (1.2×10⁷ differential ops), `exhaustive_conformance.rs`
  (729-state bounded-exhaustive), `loom_gate_test.rs` (concurrent interleavings),
  property/invariant unit tests.
- `e2e/` — integrations driving the live gate through each framework
  (`e2e_langgraph.py`, `e2e_llamaindex.py`, `e2e_crewai.py`, `e2e_openai_agents.py`,
  `e2e_msaf.py`), plus injection, partition, recovery, TTL, and auth demos.
- `ebpf/` — structural network-mediation guard (cgroup eBPF `sock_addr` hooks).
- `scripts/` — `recompute_expA.py` (canonical Experiment-A recompute), `fuzz_boundary.py`,
  `mutation_score.py`, `netem_raft_sweep.sh`, Raft cluster/bench helpers.
- `evidence/` — **committed receipts** for every quantitative claim.
- `results/` — raw JSONL: Experiment A (`expA_*.jsonl`), τ-bench ecological arm
  (`taubench_exposure_*.jsonl`), natural-prompt arm.
- `python-bindings/` — PyO3 bindings + pure-Python client + LangGraph integration.

## Build & test (offline, no keys)
```bash
export PATH=/usr/lib/rust-1.89/bin:$PATH      # edition 2024 needs rustc ≥ 1.85
cargo build --release
cargo test  --release --features conformance
cargo bench --bench admission
./target/release/soundgate 127.0.0.1:8796
```

## Run the gate from Python
See `python-bindings/README_python.md`: the PyO3 extension
(`maturin develop --release --features python`) or the zero-build
`soundgate_client.py`.