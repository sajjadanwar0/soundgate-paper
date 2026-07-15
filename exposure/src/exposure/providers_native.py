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
            self._extra_body = extra_body or {}

        def turn(self, messages: list[dict], tools: list[dict], run_idx: int):
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
    "gemini_native": "gemini-3.5-flash",
    "deepseek_native": "deepseek-v4-flash",
    "llama_together": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    "llama_groq": "llama-3.3-70b-versatile",
}