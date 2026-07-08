# agentprobe — model-free control-plane probes

Measures whether agent-framework **stop primitives** (approval gates,
cancellation, timeouts) provide the barrier semantics their names imply.
No API keys, no LLMs: nodes/steps are plain Python functions, because the
questions are about *framework control flow*, not any model.

## Layout (src-layout, uv-managed)
```
probes/
├── pyproject.toml
├── src/agentprobe/
│   ├── _harness.py            # event log + pre-registered violation records
│   ├── langgraph_probes.py    # FW-A: sibling leak, replay, cancel, timeout
│   └── llamaindex_probes.py   # FW-B: parallel approval leak, timeout
├── tests/test_harness.py
└── results/                   # committed evidence (regenerate any time)
```

## Run (uv)
```bash
uv sync
uv run agentprobe-langgraph   | tee results/langgraph.txt
uv run agentprobe-llamaindex  | tee results/llamaindex.txt
uv run pytest
```

## Adding a framework (build phase)
1. `uv add <framework>` (moves the pin into pyproject + uv.lock).
2. Add `src/agentprobe/<fw>_probes.py` using the same `_harness` API:
   build a minimal workflow, represent effects as `LOG.log(...)`, set a
   violation predicate, return `ProbeResult`.
3. Register a console script in `pyproject.toml`.
4. Commit the generated `results/<fw>.txt`.

## Violation predicates (fixed before running = pre-registration)
See each probe's docstring; a result is one bit — does the primitive hold.
