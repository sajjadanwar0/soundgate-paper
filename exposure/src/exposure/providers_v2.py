from __future__ import annotations
import os
from .runner import OpenAIProvider
from openai import OpenAI
from .runner import CLIENT_MAX_RETRIES, CLIENT_TIMEOUT_S

def _OpenAIProvider():
    return OpenAIProvider

class OpenRouterProvider(_OpenAIProvider()):
    name = "openrouter"
    def __init__(self, model: str, temperature: float):
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
        self.require_params = os.environ.get("OPENROUTER_REQUIRE_PARAMS", "1") != "0"

    def _provider_pref(self) -> dict:
        if self.require_params:
            return {"require_parameters": True}

        return {"require_parameters": False, "allow_fallbacks": True}

    def turn(self, messages: list[dict], tools: list[dict], run_idx: int):
        _ = run_idx

        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools,
            temperature=self.temperature,
            extra_body={"provider": self._provider_pref()},
        )

        msg = resp.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))
        calls = [(c.id, c.function.name) for c in (msg.tool_calls or [])]
        return calls, bool(msg.content)

NEW_PROVIDERS = {"openrouter": OpenRouterProvider}
NEW_DEFAULT_MODELS = {"openrouter": "openai/gpt-4o"}