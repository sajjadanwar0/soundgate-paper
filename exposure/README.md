# `exposure/` — the model exposure study (C2)

Measures whether real models emit the **leak-triggering parallel plan shape**
under a protocol fixed a priori, and at what rate.

## Design
Ten authored tasks per model, N=100 (N=1000 for the Llama de-confound), scored
model-free for whether a consequential (gated) call is emitted in parallel with
a benign sibling. Native-API anchors for GPT-4o and Claude; native replications
for Gemini and DeepSeek; a provider-direct Llama arm; and an OpenRouter arm
whose near-zero rows are de-confounded on a second serving path.

## Layout
- `src/` — the exposure harness (task set, runner, scorer).
- `results/*.jsonl` — **committed raw runs**, one row per run:
    - `exposure_openai_gpt-4o.jsonl`, `exposure_anthropic_claude-sonnet-4-6.jsonl`
    - native `exposure_gemini_native_*`, `exposure_deepseek_native_*`
    - provider-direct `exposure_llama_together_*` (`*_n1000` is the de-confound)
    - `exposure_openrouter_*`
- `results/EXPOSURE*.md` — per-arm summaries.
- `gemini_diagnostic.py`, `isolate_deepseek.py`, `list_models.py` — provider probes.

## Key numbers (audited by `../reproduce.sh`)
- Llama-Together pooled **64/1000**; `compound_cleanup` **57/100** (conditional 0.90 = 57/63 called).
- GPT-4o pooled ~0.14; per-task, model-disjoint (see `EXPOSURE.md`).

## Re-run (live; needs keys)
```bash
uv sync
uv run ...   # see src/ for the runner entrypoint and flags
```
Offline audit reads the committed JSONL and needs no keys.