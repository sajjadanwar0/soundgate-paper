# `soundgate/python-bindings/`

Python usage material for the gate. **None of this is compiled into the
`pip install soundgate` wheel** — the wheel is built from `../pyproject.toml`,
`../src/python.rs`, and `../README_python.md`. These are the client, the
framework integration, examples, tests, and the packaging docs.

## Files

| File | What it is |
|---|---|
| `README_python.md` | The PyPI landing README (ships in the wheel). |
| `soundgate_client.py` | Zero-build pure-Python client (same API as the PyO3 `GateClient`). |
| `soundgate_langgraph.py` | LangGraph integration helpers (`mediate_no_approval`, `mediate_with_approval`). |
| `example_mediated_tool.py` | Minimal framework-agnostic wrapper pattern. |
| `smoke_test.py` | End-to-end check against a running gate (`import soundgate`). |
| `test_protocol.py` | Validates the wire protocol + HMAC against a mock gate. |
| `test_langgraph_flow.py` | Validates the LangGraph helpers against a mock gate. |
| `python.rs` | The PyO3 bindings source (belongs at `../src/python.rs`). |
| `pyproject.toml` | maturin build config (belongs at `../pyproject.toml`, next to `Cargo.toml`). |

## Run the tests (no LangGraph, no keys, no Rust needed)

```bash
cd soundgate/python-bindings
python test_protocol.py          # protocol + HMAC + P1–P4
python test_langgraph_flow.py    # spins up a mock gate; approve runs, replay/reject blocked
```

## Live smoke test (needs the gate running)

```bash
./../target/release/soundgate 127.0.0.1:8796   &   # or in another terminal
python smoke_test.py
```