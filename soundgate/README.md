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
  `wal_recovery_barrier.rs` (byte-prefix crash-recovery sweep, see below),
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

## Durable mode: the WAL and the recovery barrier (0.1.4)
With a second argument the server logs every acknowledged event (`released`,
`rejected`, `cancelled`, `closed`) as one JSON line, fsyncs it before
replying, and replays the log at startup. Since 0.1.4 a **recovery barrier**
runs before the listener opens:

1. the log is opened and exclusively locked for the life of the process, so a
   second gate on the same file is refused;
2. every newline-terminated record must parse, otherwise the gate refuses to
   start (a merged or corrupt line is never skipped);
3. an unterminated tail is completed with its newline if it is a whole record,
   or truncated away if it is a torn fragment (a fragment was never
   acknowledged, so no admitted decision is lost);
4. the repair is fsynced, the records are replayed, and only then does the
   gate serve. A failed append stops the process (fail-closed) instead of
   leaving a fragment for the next append to land on.

The barrier closes the defect reported by Cenab Batu Bora (Georgia Tech),
*A Restart Is Not Permission: When an Agent Gate Forgets "No"* (Apart Research
incident-response sprint, September 2026): in 0.1.3 a torn final fragment was
skipped but left in place, the next acknowledged decision was appended on the
same line, and the second restart skipped the merged line, so a rejection or a
release could vanish while its bytes stayed on disk. His byte-prefix sweep is
now `tests/wal_recovery_barrier.rs`: every byte prefix of a three-record log,
one decision acknowledged after the first restart, a crash, and the second
restart must still enforce it. On the 0.1.3 recovery code the sweep loses the
decision in 260 of 268 histories (every cut that is not a record boundary);
on 0.1.4 it loses none.

```bash
cargo test --test wal_recovery_barrier -- --nocapture
```

## Run the gate from Python
See `python-bindings/README_python.md`: the PyO3 extension
(`maturin develop --release --features python`) or the zero-build
`soundgate_client.py`.