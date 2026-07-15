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