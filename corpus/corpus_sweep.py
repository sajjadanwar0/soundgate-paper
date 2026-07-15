"""
Usage:
  python3 corpus_sweep.py --chunk 1   # first half of the query matrix
  python3 corpus_sweep.py --chunk 2   # second half
  python3 corpus_sweep.py --report    # summarize sweep_results.jsonl

Committed outputs: results/sweep_results.jsonl, results/SWEEP.md
"""
import argparse
import json
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

REPOS = [
    "langchain-ai/langgraph",
    "langchain-ai/langgraphjs",
    "run-llama/llama_index",
    "microsoft/agent-framework",
    "openai/openai-agents-python",
    "crewAIInc/crewAI",
]

QUERIES = [
    ("A1", "interrupt parallel"),
    ("A1", "human approval parallel"),
    ("A2", "resume duplicate"),
    ("A2", "resume executes again"),
    ("A3", "cancel still running"),
    ("A4", "timeout effect completed"),
]

OUT = Path(__file__).resolve().parent / "results"
OUT.mkdir(exist_ok=True)
RESULTS = OUT / "sweep_results.jsonl"
PACE_S = 6.3


def search(repo: str, words: str):
    q = urllib.parse.quote(f"repo:{repo} is:issue {words}")
    url = (f"https://api.github.com/search/issues?q={q}"
           f"&per_page=20&sort=created&order=desc")
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "soundgate-corpus-sweep",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def run_chunk(chunk: int) -> None:
    pairs = [(r, a, w) for r in REPOS for a, w in QUERIES]
    half = len(pairs) // 2
    todo = pairs[:half] if chunk == 1 else pairs[half:]
    seen = set()
    if RESULTS.exists():
        for line in RESULTS.open():
            rec = json.loads(line)
            seen.add((rec["repo"], rec["axis_hint"], rec["query"],
                      rec["number"]))
    with RESULTS.open("a") as out:
        for repo, axis, words in todo:
            try:
                data = search(repo, words)
                items = data.get("items", [])
                total = data.get("total_count", 0)
            except Exception as e:
                print(f"{repo:<34} [{axis}] '{words}': ERROR {e}")
                time.sleep(PACE_S)
                continue
            fresh = 0
            for it in items:
                key = (repo, axis, words, it["number"])
                if key in seen:
                    continue
                seen.add(key)
                fresh += 1
                out.write(json.dumps({
                    "repo": repo, "axis_hint": axis, "query": words,
                    "number": it["number"], "state": it.get("state"),
                    "created_at": it.get("created_at"),
                    "title": it.get("title"),
                    "labels": [l["name"] for l in it.get("labels", [])],
                    "html_url": it.get("html_url"),
                }) + "\n")
            print(f"{repo:<34} [{axis}] '{words}': total={total} "
                  f"kept_new={fresh}")
            time.sleep(PACE_S)


def report() -> None:
    rows = [json.loads(l) for l in RESULTS.open()] if RESULTS.exists() else []
    by_repo = defaultdict(set)
    by_repo_axis = defaultdict(lambda: defaultdict(set))
    for r in rows:
        by_repo[r["repo"]].add(r["number"])
        by_repo_axis[r["repo"]][r["axis_hint"]].add(r["number"])
    lines = ["# Six-tracker corpus sweep -- CANDIDATES (pending manual "
             "verification)", "",
             f"Generated {time.strftime('%Y-%m-%d')}. Queries: "
             + "; ".join(f"[{a}] '{w}'" for a, w in QUERIES) + ".",
             "Unauthenticated GitHub search, 20 hits/query cap, "
             "deduplicated per (repo, axis, query, issue).", "",
             "| repo | unique candidate issues | A1 | A2 | A3 | A4 |",
             "|---|---|---|---|---|---|"]
    for repo in REPOS:
        ax = by_repo_axis[repo]
        lines.append(
            f"| {repo} | {len(by_repo[repo])} | {len(ax['A1'])} "
            f"| {len(ax['A2'])} | {len(ax['A3'])} | {len(ax['A4'])} |")
    lines += ["", "Every row above is a CANDIDATE: the corpus's conservative "
                  "DIRECT/ADJACENT/CONTEXT classification requires reading each "
                  "issue (seeds.py protocol) and is not performed by this tool.",
              "", f"Raw hits: {len(rows)} records in sweep_results.jsonl."]
    (OUT / "SWEEP.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunk", type=int, choices=[1, 2])
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    if a.chunk:
        run_chunk(a.chunk)
    if a.report:
        report()