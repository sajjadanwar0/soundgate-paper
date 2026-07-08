"""providers_v2.py -- OpenRouter exposure provider for the v2 study.

ONE key, ONE endpoint, EVERY model. OpenRouter (https://openrouter.ai/api/v1)
is an OpenAI-compatible proxy. This slots into runner.py's Provider protocol by
reusing OpenAIProvider's tool_schema / init_messages / add_tool_results verbatim
and overriding only client construction and turn().

TOOL-ROUTING SAFETY (configurable). OpenRouter can silently forward a request
to a provider that ignores unsupported params -- for a tool-calling study that
risks measuring nothing. We guard against it, but with a knob, because being
TOO strict causes the opposite failure ("404 No endpoints found"): if the
cheapest provider for a valid slug doesn't advertise `tools`, hard-strict
routing REFUSES instead of trying a provider that does.

  OPENROUTER_REQUIRE_PARAMS=1  (default): require_parameters=true. OpenRouter
     routes only to providers honoring the tool schema, or errors loudly. Use
     this once you've confirmed a slug has a tool-capable provider.
  OPENROUTER_REQUIRE_PARAMS=0            : relax strict routing (rarely
     needed now). The usual cause of a 404 on a VALID tool-capable slug was
     the `seed` parameter -- OpenRouter required one provider supporting
     tools+seed together, which many don't. This provider no longer sends
     seed (see turn()), so strict mode (default) works for tool-capable
     slugs. Keep it ON unless a specific model still 404s.

Either way we NEVER set parallel_tool_calls: each model's native parallel-tool
default is preserved (the validity basis of the metric).

FINDING VALID SLUGS: run list_models.py (ships alongside) to print current
tool-capable slugs, or browse https://openrouter.ai/models. Slugs are
provider/model and DRIFT over time -- e.g. anthropic/claude-sonnet-4.6 (NOT
claude-sonnet-4), deepseek/deepseek-v3.2, google/gemini-2.0-flash-001,
meta-llama/llama-3.3-70b-instruct. A missing or stale slug -> 404.

PREFLIGHT one call before 500:
  export OPENROUTER_API_KEY=sk-or-...
  uv run python -m exposure.runner --provider openrouter --model <slug> --runs 1
  (one clean record with error=null means the slug + routing work.)

USAGE:
  export OPENROUTER_API_KEY=sk-or-...
  uv run python -m exposure.runner --provider openrouter --model <slug> --runs 100 --out results/or_<name>.jsonl
"""
from __future__ import annotations

import os


def _OpenAIProvider():
    from .runner import OpenAIProvider
    return OpenAIProvider


class OpenRouterProvider(_OpenAIProvider()):
    name = "openrouter"

    def __init__(self, model: str, temperature: float):
        from openai import OpenAI
        from .runner import CLIENT_MAX_RETRIES, CLIENT_TIMEOUT_S

        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise SystemExit("OPENROUTER_API_KEY not set (keys start with sk-or-)")
        if not key.startswith("sk-or-"):
            print("WARNING: OPENROUTER_API_KEY does not start with 'sk-or-'; "
                  "a plain OpenAI key will not route through OpenRouter.")
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=key,
            timeout=CLIENT_TIMEOUT_S,
            max_retries=CLIENT_MAX_RETRIES,
            default_headers={
                "HTTP-Referer": "https://github.com/USERNAME/soundgate",
                "X-Title": "SoundGate exposure study",
            },
        )
        self.model = model
        self.temperature = temperature
        # Strict tool routing on by default; set OPENROUTER_REQUIRE_PARAMS=0 to relax.
        self.require_params = os.environ.get("OPENROUTER_REQUIRE_PARAMS", "1") != "0"

    def _provider_pref(self) -> dict:
        if self.require_params:
            # Only providers that honor the tool schema, or error loudly.
            return {"require_parameters": True}
        # Relaxed: don't hard-require, but keep routing deterministic and
        # correctness-first (no silent quantized/degraded fallbacks).
        return {"require_parameters": False, "allow_fallbacks": True}

    def turn(self, messages: list[dict], tools: list[dict], run_idx: int):
        # NOTE ON SEED: we do NOT send `seed` on OpenRouter. Seed determinism
        # was always best-effort and does NOT hold across OpenRouter's many
        # upstream providers; worse, requiring a provider that supports
        # tools+seed together is what makes require_parameters=true return
        # "404 No endpoints found" for models whose providers expose tools but
        # not seed (Claude/Gemini/DeepSeek/Llama). Dropping seed lets strict
        # tool-routing stay ON (tools alone IS satisfiable), so the tool-schema
        # safety is preserved. temperature=1.0 sampling is non-deterministic
        # regardless, and the metric averages over N runs -- seed was never
        # load-bearing. run_idx is still the per-run index used for logging.
        _ = run_idx
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools,
            temperature=self.temperature,
            # parallel_tool_calls deliberately NOT set: model's native default.
            extra_body={"provider": self._provider_pref()},
        )
        msg = resp.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))
        calls = [(c.id, c.function.name) for c in (msg.tool_calls or [])]
        return calls, bool(msg.content)


NEW_PROVIDERS = {"openrouter": OpenRouterProvider}
NEW_DEFAULT_MODELS = {"openrouter": "openai/gpt-4o"}