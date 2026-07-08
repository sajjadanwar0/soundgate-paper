#!/usr/bin/env python3
"""list_models.py -- query OpenRouter's LIVE model catalog and print slugs that
support tool calling, so you never guess a stale slug again.

The 404 "No endpoints found that can handle the requested parameters" means
either (a) the slug doesn't exist, or (b) with require_parameters=true no
provider for that slug supports your tool schema. This script rules out (a)
and flags (b): it lists real, current slugs and marks which advertise the
"tools" parameter.

Usage:
  export OPENROUTER_API_KEY=sk-or-...
  uv run python list_models.py                 # all tool-capable models
  uv run python list_models.py gpt             # filter slug/name by substring
  uv run python list_models.py claude
  uv run python list_models.py deepseek
No key strictly required for the public /models list, but sending it is fine.
"""
import json
import os
import sys
import urllib.request

def main():
    filt = (sys.argv[1].lower() if len(sys.argv) > 1 else "")
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/models",
        headers={"Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY','')}"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)["data"]

    rows = []
    for m in data:
        slug = m.get("id", "")
        name = m.get("name", "")
        params = m.get("supported_parameters") or []
        tools = "tools" in params
        if filt and filt not in slug.lower() and filt not in name.lower():
            continue
        if not tools:
            continue
        # price per 1M input tokens, best-effort
        pin = m.get("pricing", {}).get("prompt", "?")
        try:
            pin = f"${float(pin)*1_000_000:.2f}/M"
        except (TypeError, ValueError):
            pin = "?"
        rows.append((slug, pin, name[:48]))

    rows.sort()
    print(f"{'SLUG (use this in --model)':52s} {'IN $/M':10s} NAME")
    print("-" * 100)
    for slug, pin, name in rows:
        print(f"{slug:52s} {pin:10s} {name}")
    print(f"\n{len(rows)} tool-capable models" + (f" matching '{filt}'" if filt else ""))
    print("Pick one slug per family; paste it verbatim into --model.")

if __name__ == "__main__":
    main()