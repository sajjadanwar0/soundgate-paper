import os
import sys
import time
import traceback

from openai import OpenAI

key = os.environ.get("OPENROUTER_API_KEY")
if not key:
    sys.exit("OPENROUTER_API_KEY not set")

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=key,
    timeout=90,
    max_retries=0,
)

print("Attempting ONE bare call to deepseek/deepseek-v3.2 via OpenRouter...")

t0 = time.time()

try:
    resp = client.chat.completions.create(
        model="deepseek/deepseek-v3.2",
        messages=[{"role": "user", "content": "Say OK."}],
        temperature=1.0,
        extra_body={"provider": {"require_parameters": True}},
    )
    print(f"SUCCESS in {time.time()-t0:.1f}s: {resp.choices[0].message.content!r}")
except Exception as e:
    print(f"FAILED after {time.time()-t0:.1f}s")
    print(f"Exception type: {type(e).__module__}.{type(e).__name__}")
    print(f"Exception str:  {e}")
    cause = e.__cause__
    depth = 0

    while cause is not None and depth < 5:
        print(f"  caused by [{depth}]: {type(cause).__module__}.{type(cause).__name__}: {cause}")
        cause = cause.__cause__
        depth += 1
    print("\nFull traceback:")
    traceback.print_exc()