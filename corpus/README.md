# `corpus/` — the public-incident corpus (occurrence lower bound)

The verified third-party incident corpus and the tracker sweep behind the
paper's occurrence evidence — a lower bound, never a rate.

## Layout
- `results/incidents.jsonl` — the seed corpus (classified third-party reports).
- `results/incidents_enriched.jsonl` — states enriched from the live trackers.
- `results/sweep_results.jsonl` — the widened keyword sweep (130 candidates).
- `results/INCIDENTS.md`, `SWEEP.md`, `sweep_screened.md` — human-readable views.
- `results/triage_map.json`, `classify_queue.md` — the triage rubric and queue.
- `corpus_sweep.py` — the axis-derived keyword sweep across six trackers.
- `classify_corpus.py`, `triage_corpus.py` — the conservative classification rubric.

## Key numbers (audited by `../reproduce.sh`)
- Thirteen direct third-party incidents across three independent trackers
  (LangGraph, LangGraph.js, LlamaIndex); 130-candidate sweep, 2 confirmed direct.

## Reproduce the classification (offline)
```bash
uv sync
uv run python classify_corpus.py results/incidents.jsonl
```
The GitHub *sweep* (`corpus_sweep.py`) hits the public GitHub search API
unauthenticated; the committed `sweep_results.jsonl` is the frozen result.