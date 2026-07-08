# `probes-js/` — the probe design on LangGraph.js (Node)

The same measurement on **LangGraph.js**, to separate *framework* semantics from
*host-language* concurrency semantics: the sibling leak reproducing on both the
Python and Node schedulers is evidence it is a design pattern, not a Python
accident.

## Layout
- `langgraph_probes.mjs` — the FW-F probes (Node/LangGraph.js).
- `e2e_langgraph_js.mjs` — end-to-end repair driving the Rust gate from Node.
- `experiment_a_js.mjs` — the FW-F Experiment-A arm (143/300 in the paper).
- `package.json` / `package-lock.json` — pinned deps.

## Run (offline, no keys)
```bash
npm ci
node langgraph_probes.mjs
node e2e_langgraph_js.mjs            # requires the gate binary running (see ../soundgate)
```