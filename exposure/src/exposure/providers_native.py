"""providers_native.py -- native / provider-direct providers for the three
pathway-confounded models (Gemini, DeepSeek, Llama).

STATUS: WRITTEN AND SMOKE-TESTED FOR CONSTRUCTION ONLY. NOT EXECUTED against
the vendor endpoints -- the environment this file was authored in has no
network route to them. Every record it produces will carry provider names
distinct from "openrouter", so the analyzer keeps these arms separate by
construction. Run the PREFLIGHT below before any battery.

WHY: Sec. 4.1 labels the Gemini/DeepSeek/Llama N=100 rows pathway-confounded
because their only serving path was one OpenRouter integration. De-confounding
requires a second, vendor-controlled path per model:

  gemini_native   -- Google's OWN OpenAI-compatible surface
                     (base_url https://generativelanguage.googleapis.com/v1beta/openai/,
                     key GEMINI_API_KEY). This is the vendor's documented
                     endpoint, i.e. a genuinely native arm.
  deepseek_native -- DeepSeek's OWN API (base_url https://api.deepseek.com,
                     key DEEPSEEK_API_KEY), natively OpenAI-compatible. USE
                     `deepseek-chat` (V3.2 NON-thinking) to match the Table 3
                     OpenRouter row's checkpoint -- this is the clean
                     de-confound. DO NOT use `deepseek-reasoner` here: thinking
                     mode ignores temperature AND requires reasoning_content to
                     be threaded back through multi-turn tool loops or the API
                     400s on turn 2 (our turn() does not preserve it), so the
                     reasoner would fail every 2-turn task and would also
                     measure a different (thinking) checkpoint. DEPRECATION:
                     the `deepseek-chat` alias stops working 2026-07-24, after
                     which it becomes deepseek-v4-flash (a NEWER family); run
                     before then to match V3.2, or label v4-flash as a
                     newer-generation native arm (as with gemini-3.5).
  llama_together  -- there is NO first-party hosted Llama API; this arm is
                     PROVIDER-DIRECT (Together, base_url
                     https://api.together.xyz/v1, key TOGETHER_API_KEY),
                     which removes the OpenRouter translation layer but is
                     NOT vendor-native. The paper must say "provider-direct"
                     for this arm, never "native". VERIFY the current model
                     id (historically meta-llama/Llama-3.3-70B-Instruct-Turbo).

All three reuse the OpenAI-SDK ChatCompletions turn shape already validated
by providers_v2.OpenRouterProvider: no seed, temperature passthrough, tools
passthrough, model-native parallel_tool_calls default. Identical task set,
identical metric, N=100 -- only the serving path changes.

PREFLIGHT (one record each; error=null means the path works):
  export GEMINI_API_KEY=...      DEEPSEEK_API_KEY=...   TOGETHER_API_KEY=...
  uv run python -m exposure.runner --provider gemini_native   --model gemini-3.5-flash --runs 1
  uv run python -m exposure.runner --provider deepseek_native --model deepseek-chat    --runs 1
  uv run python -m exposure.runner --provider llama_together  --model meta-llama/Llama-3.3-70B-Instruct-Turbo --runs 1

BATTERY (mirrors the or_*.jsonl commands; ~1,000 short tool-calling requests
per model):
  uv run python -m exposure.runner --provider gemini_native   --model gemini-3.5-flash --runs 100 --out results/native_gemini.jsonl
  uv run python -m exposure.runner --provider deepseek_native --model deepseek-chat    --runs 100 --out results/native_deepseek.jsonl
  uv run python -m exposure.runner --provider llama_together  --model meta-llama/Llama-3.3-70B-Instruct-Turbo --runs 100 --out results/native_llama.jsonl
  PYTHONPATH=src python3 -m exposure.analyze results/native_*.jsonl --out results/EXPOSURE_NATIVE.md

INTERPRETATION RULES (fixed before execution, so the outcome cannot be
argued backward): if a model's native/provider-direct rate replicates its
OpenRouter interval, the confound is resolved in favor of a model property;
if it diverges, the OpenRouter rows were integration artifacts and Table 3's
dagger caveat was the correct call. Either outcome is reportable; neither
changes GPT-4o's or Claude's anchored findings.
"""
from __future__ import annotations

import os


def _OpenAIProvider():
    from .runner import OpenAIProvider
    return OpenAIProvider


def _mk_oa_compat(name_: str, env_key: str, base_url: str, referer_note: str,
                  extra_body: dict | None = None):
    class _Provider(_OpenAIProvider()):
        name = name_

        def __init__(self, model: str, temperature: float):
            from openai import OpenAI
            from .runner import CLIENT_MAX_RETRIES, CLIENT_TIMEOUT_S

            key = os.environ.get(env_key)
            if not key:
                raise SystemExit(f"{env_key} not set ({referer_note})")
            self.client = OpenAI(
                base_url=base_url,
                api_key=key,
                timeout=CLIENT_TIMEOUT_S,
                max_retries=CLIENT_MAX_RETRIES,
            )
            self.model = model
            self.temperature = temperature
            # Provider-specific request body. DeepSeek V4 (flash/pro) defaults
            # to thinking mode ON, and thinking + tool calls returns HTTP 400
            # on the second turn unless reasoning_content is threaded back
            # (which this runner does not do). Sending {"thinking":{"type":
            # "disabled"}} puts V4-Flash into non-thinking mode -- exactly what
            # the retired `deepseek-chat` alias was -- so the arm runs and
            # matches the non-thinking checkpoint. See DeepSeek thinking-mode
            # docs + issues deepseek-ai/DeepSeek-V3#1376, openclaw#71435.
            self._extra_body = extra_body or {}

        def turn(self, messages: list[dict], tools: list[dict], run_idx: int):
            # Same contract as OpenRouterProvider.turn: no seed (never
            # load-bearing; temperature-1.0 averaged over N runs), tools
            # passed through, model-native parallel_tool_calls default.
            _ = run_idx
            kwargs = dict(
                model=self.model,
                messages=messages,
                tools=tools,
                temperature=self.temperature,
            )
            if self._extra_body:
                kwargs["extra_body"] = self._extra_body
            resp = self.client.chat.completions.create(**kwargs)
            msg = resp.choices[0].message
            messages.append(msg.model_dump(exclude_none=True))
            # Runner contract (runner.py line ~252): calls is a list of
            # 2-tuples (call_id, tool_name); the runner 2-unpacks these and
            # feeds (cid, name) back through add_tool_results. Returning
            # anything richer breaks the batch with
            # "too many values to unpack (expected 2)".
            calls = [(c.id, c.function.name) for c in (msg.tool_calls or [])]
            return calls, bool(msg.content)

    _Provider.__name__ = f"{name_}_provider"
    return _Provider


GeminiNativeProvider = _mk_oa_compat(
    "gemini_native", "GEMINI_API_KEY",
    "https://generativelanguage.googleapis.com/v1beta/openai/",
    "Google AI Studio key; vendor's documented OpenAI-compatible surface",
)
DeepSeekNativeProvider = _mk_oa_compat(
    "deepseek_native", "DEEPSEEK_API_KEY",
    "https://api.deepseek.com",
    "DeepSeek platform key; v4-flash non-thinking (thinking disabled below)",
    extra_body={"thinking": {"type": "disabled"}},
)
LlamaTogetherProvider = _mk_oa_compat(
    "llama_together", "TOGETHER_API_KEY",
    "https://api.together.xyz/v1",
    "PROVIDER-DIRECT, not vendor-native (no first-party Llama API exists)",
)
LlamaGroqProvider = _mk_oa_compat(
    "llama_groq", "GROQ_API_KEY",
    "https://api.groq.com/openai/v1",
    "PROVIDER-DIRECT, not vendor-native (no first-party Llama API exists); "
    "Groq serves Llama on its own LPU inference stack -- a second independent "
    "serving path, which is the point",
)

NATIVE_PROVIDERS = {
    "gemini_native": GeminiNativeProvider,
    "deepseek_native": DeepSeekNativeProvider,
    "llama_together": LlamaTogetherProvider,
    "llama_groq": LlamaGroqProvider,
}
NATIVE_DEFAULT_MODELS = {
    "gemini_native": "gemini-3.5-flash",  # 2.5-flash deprecated 2026
    "deepseek_native": "deepseek-v4-flash",  # deepseek-chat alias retired; v4-flash non-thinking
    "llama_together": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    "llama_groq": "llama-3.3-70b-versatile",  # VERIFY via GET /models before battery
}