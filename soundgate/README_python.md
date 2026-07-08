# SOUNDGATE for Python

Use the SOUNDGATE effect-admission gate from Python LLM-agent frameworks
(LangGraph, LlamaIndex, CrewAI, OpenAI Agents SDK, …). Two options:

## Option A — pure-Python client (zero build)

No Rust toolchain needed. Run the `soundgate` gate binary, then:

```python
from soundgate_client import GateClient
gate = GateClient(("127.0.0.1", 8796))            # secret=b"..." if the gate has one
v = gate.submit("run1", "send_email", needs_approval=True)
if v.released:
    send_the_email()
```

Files: `soundgate_client.py`. This talks the exact JSON/TCP protocol of the
gate server and computes the same HMAC-SHA256 decision tag.

## Option B — native PyO3 extension (`pip install soundgate`)

A compiled Rust extension with an identical API, plus an optional in-process
mode. Build:

```bash
pip install maturin
cd soundgate && maturin develop --release --features python
```

```python
from soundgate import GateClient, Gate, decision_tag
gate = GateClient("127.0.0.1:8796")     # external gate — recommended
# or, in-process (shares the agent's address space; see below):
g = Gate(); g.submit("run1", "x", True)
```

See `INSTALL_pyo3.md` for the three crate edits and build details.

## Which mode?

| | Isolation | Latency | Deploy | Use when |
|---|---|---|---|---|
| `GateClient` (external) | **Full** — gate is a separate process; namespace/eBPF mediation holds | one socket round-trip (~53 µs) | run the gate binary | **default / production** |
| `Gate` (in-process) | Reduced — gate shares the agent's memory | function call | none | single-process / low-stakes |

The external client preserves the paper's environment-external reference-monitor
model. The in-process `Gate` is faster and simpler but forgoes that isolation.

## API (both clients)

- `submit(run_id, effect_key, needs_approval=False) -> Verdict`
- `decide(run_id, effect_key, approved) -> Verdict`  (signed if a secret is set)
- `cancel(run_id) -> Verdict`
- `ping() -> Verdict`
- `Verdict`: `.released`, `.held`, `.refused`, and `v == "release"`
- `decision_tag(secret, run_id, effect_key, approved) -> str`

## Verified

`test_protocol.py` drives the pure-Python client against a mock gate that
reimplements the admission core, checking all four properties (hold-until-
decided, reject-stickiness, dedup-on-replay, fence-on-cancel), cross-run key
independence, HMAC-authenticated decisions, forged-MAC rejection, and the
decision-tag byte format. All pass. The PyO3 `GateClient` sends the identical
protocol and reuses `hmac.rs`, so the same guarantees apply.