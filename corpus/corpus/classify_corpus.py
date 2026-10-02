import argparse, json, os, sys, time, urllib.request, urllib.error, re

API = "https://api.github.com/repos/{repo}/issues/{num}"

HINTS = {
    "A1": ["during pause", "while paused", "parallel", "sibling", "await approval",
           "lost tool call", "loses tool call", "batch"],
    "A2": ["resume", "restart", "re-execute", "re-run", "twice", "duplicate",
           "again from the beginning", "idempoten"],
    "A3": ["cancel", "stop", "abort", "orphan", "still running", "not propagate"],
    "A4": ["timeout", "deadline", "zombie", "after the timeout"],
}

def fetch(repo, num, token):
    req = urllib.request.Request(API.format(repo=repo, num=num))
    req.add_header("Accept", "application/vnd.github+json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            remaining = r.headers.get("X-RateLimit-Remaining")
            return json.load(r), remaining
    except urllib.error.HTTPError as e:
        if e.code == 403 and "rate limit" in e.read().decode(errors="ignore").lower():
            print("!! rate limited -- set GITHUB_TOKEN or wait; partial queue written",
                  file=sys.stderr)
            return None, "0"
        return {"_error": f"HTTP {e.code}"}, None
    except Exception as e:
        return {"_error": str(e)}, None

def suggest(text, axis_hint):
    t = (text or "").lower()
    scores = {ax: sum(t.count(k) for k in kws) for ax, kws in HINTS.items()}
    top = max(scores, key=scores.get) if any(scores.values()) else axis_hint
    # crude: strong failure verbs present -> suggest 'direct?' else 'adjacent/context?'
    failure = any(w in t for w in ("during the pause", "while paused", "executed twice",
                                   "duplicate payment", "duplicate email", "still ran",
                                   "landed after", "after cancel", "after the timeout"))
    return top, ("direct?" if failure else "adjacent/context?")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sweep")
    ap.add_argument("--out", required=True)
    ap.add_argument("--sleep", type=float, default=0.8,
                    help="seconds between calls (raise if unauthenticated)")
    a = ap.parse_args()
    token = os.environ.get("GITHUB_TOKEN")
    rows = [json.loads(l) for l in open(a.sweep) if l.strip()]
    # dedup per (repo, number)
    seen, uniq = set(), []
    for r in rows:
        k = (r["repo"], r["number"])
        if k not in seen:
            seen.add(k); uniq.append(r)
    print(f"{len(uniq)} unique candidates", file=sys.stderr)

    out = ["# Corpus classification queue -- SET EVERY VERDICT BY HAND",
           "", f"Generated from {a.sweep}. Rubric in the script header. "
               "Suggestions are heuristic and NOT authoritative; the paper's "
               "direct/adjacent/context counts update only after you confirm each.",
           ""]
    tally = {"direct": 0, "adjacent": 0, "context": 0, "UNSET": len(uniq)}
    for i, r in enumerate(uniq, 1):
        data, remaining = fetch(r["repo"], r["number"], token)
        body = ""
        if data and "_error" not in data:
            body = (data.get("body") or "")[:1500]
            state = data.get("state", r.get("state", "?"))
        else:
            state = r.get("state", "?")
            body = f"[body unavailable: {data.get('_error') if data else 'rate-limited'} " \
                   f"-- read the page manually]"
        ax, sug = suggest(r.get("title", "") + " " + body, r.get("axis_hint", ""))
        out += [
            f"## {i}. [{r['repo']}#{r['number']}]({r['html_url']})  "
            f"axis_hint={r.get('axis_hint','')} suggest={ax} state={state}",
            f"**{r.get('title','')}**",
            "",
            f"> {body.strip()[:700].replace(chr(10),' ')}",
            "",
            f"suggestion: **{sug}**   (heuristic only)",
            "",
            "**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->",
            "**why:** ",
            "",
            "---",
        ]
        if remaining is not None and remaining.isdigit() and int(remaining) < 2:
            out.append(f"\n<!-- stopped at {i}/{len(uniq)}: rate limit. "
                       f"Re-run with GITHUB_TOKEN to continue. -->")
            break
        time.sleep(a.sleep)

    open(a.out, "w").write("\n".join(out))
    print(f"wrote {a.out}", file=sys.stderr)
    print("Now: read each entry, replace UNSET, then recount with:", file=sys.stderr)
    print("  grep -c 'VERDICT:.*direct'   " + a.out, file=sys.stderr)
    print("  grep -c 'VERDICT:.*adjacent' " + a.out, file=sys.stderr)
    print("  grep -c 'VERDICT:.*context'  " + a.out, file=sys.stderr)

if __name__ == "__main__":
    main()