# `probes/` — model-free differential probes (C1)

**Measures** the control-plane gap directly, with no model in the loop: scripted
plan shapes are driven through each framework and the framework's *own* behavior
(does the sibling effect execute during a pause? does a cancelled tool still
land?) is recorded deterministically.

## Frameworks (FW-A … FW-E)
- `src/agentprobe/langgraph_probes.py` — FW-A (LangGraph)
- `src/agentprobe/llamaindex_probes.py` — FW-B (LlamaIndex Workflows)
- `src/agentprobe/msaf_probes.py` — FW-C (Microsoft Agent Framework)
- `src/agentprobe/openai_agents_probes.py` — FW-D (OpenAI Agents SDK)
- `src/agentprobe/crewai_probes.py` — FW-E (CrewAI; isolated venv, see pyproject)
- `src/agentprobe/_harness.py` — shared event log / tally / `ProbeResult`

## Layout
- `results/MATRIX.md` — the cross-framework violation matrix (Table 2).
- `results/*.txt` — committed per-framework probe transcripts.
- `tests/` — regression guards: pinned verdict maps (`test_probe_verdicts.py`).
- `scripts/check_crewai_verdicts.py` — the same guard for the isolated CrewAI venv.

## Run (offline, no keys)
```bash
uv sync
uv run pytest                       # verdict regression guards
uv run python -m agentprobe.langgraph_probes    # a single framework's probes
```
Managed with **uv**; `uv.lock` is committed for a frozen resolution. CrewAI runs
in a separate venv because of dependency conflicts (see `pyproject.toml`).