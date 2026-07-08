#!/usr/bin/env python3
"""triage_corpus.py -- turn the 130-entry queue into a defensible triage.

Snippets (700-char og:descriptions) support TRIAGE, not a final incident
count. This script sorts every candidate into:
  DIRECT?   -- the snippet describes a stop-primitive FAILURE OCCURRING
               (effect during pause / resume double-exec / cancel orphan /
               timeout zombie). These MUST be read in full before counting.
  ADJACENT  -- same root cause but the item is a fix / RFC / feature ask /
               design discussion (the failure is proposed-against, not shown).
  CONTEXT   -- question, how-to, perf, tangential, or unconfirmable.
Conservative by construction: if the snippet does not clearly show the failure
occurring, it is NOT DIRECT.
"""
import re, sys, json

md = open(sys.argv[1] if len(sys.argv) > 1 else "classify_queue.md").read()

# split into entries
entries = []
for block in re.split(r"\n## ", md)[1:]:
    m = re.match(r"\d+\.\s+\[([^\]]+)\]\(([^)]+)\).*?axis_hint=(\w*)", block)
    if not m:
        continue
    slug, url, axis = m.group(1), m.group(2), m.group(3)
    title = ""
    tm = re.search(r"\*\*(.+?)\*\*", block)
    if tm:
        title = tm.group(1)
    bm = re.search(r"\n> (.+?)\n\nsuggestion", block, re.S)
    body = bm.group(1) if bm else ""
    entries.append({"slug": slug, "url": url, "axis": axis,
                    "title": title, "text": (title + " " + body).lower()})

# ---- rubric patterns ----
# "the failure occurred" verbs, per axis
OCCUR = {
    "A1": [r"lost (every|the|all).{0,20}(tool )?call", r"lose.{0,20}tool call",
           r"executed while.{0,20}(pause|approval)", r"ran during.{0,20}pause",
           r"sibling.{0,30}(executed|ran|fired)", r"both.{0,20}branches.{0,20}ran",
           r"parallel.{0,30}approval.{0,30}(lost|dropped|duplicat|executed)"],
    "A2": [r"restart(s|ed)? (instead of|from)", r"re-?execut", r"re-?run",
           r"runs? again", r"executed twice", r"duplicate (payment|email|tool|call|charge|message)",
           r"resume.{0,30}(again|twice|duplicate|from the (beginning|start))",
           r"tool.{0,20}(runs|executes).{0,20}again"],
    "A3": [r"still (running|executes|runs)", r"orphan", r"not (cancel|stop|propagate|abort)",
           r"keeps (running|executing)", r"continues? (after|to run)",
           r"effect.{0,20}(after|still).{0,20}cancel", r"cancel.{0,30}(no-?op|ignored|doesn'?t)"],
    "A4": [r"after (the )?timeout", r"zombie", r"still.{0,20}(complete|execut|run)",
           r"deadline.{0,30}(ignored|exceeded|still)", r"timeout.{0,30}(still|effect|complete)"],
}
# feature-request / discussion markers -> adjacent, not direct
ADJ = [r"\brfc\b", r"\bproposal\b", r"feature request", r"\[feature\]",
       r"would (it|be).{0,20}(nice|possible|good)", r"is there a way",
       r"add (a |support )", r"\bhook\b.{0,20}(request|proposal)",
       r"enhancement", r"design (doc|discussion)", r"should (we|langgraph|it)"]
# question / how-to -> context
CTX = [r"how (do|can|to) i", r"how do you", r"\?$", r"question:", r"help wanted",
       r"not sure (how|if|whether)", r"is this expected", r"am i (doing|missing)"]

def classify(e):
    t = e["text"]
    axis = e["axis"] if e["axis"] in OCCUR else None
    axes = [axis] if axis else list(OCCUR)
    occurred = any(re.search(p, t) for ax in axes for p in OCCUR[ax])
    is_adj = any(re.search(p, t) for p in ADJ)
    is_ctx = any(re.search(p, t) for p in CTX)
    # DIRECT only if a failure verb fires AND it is not framed as a request/question
    if occurred and not is_adj:
        return "DIRECT?"
    if occurred or is_adj:
        return "ADJACENT"
    return "CONTEXT"

for e in entries:
    e["triage"] = classify(e)

order = {"DIRECT?": 0, "ADJACENT": 1, "CONTEXT": 2}
entries.sort(key=lambda e: (order[e["triage"]], e["slug"]))

from collections import Counter
c = Counter(e["triage"] for e in entries)
print(f"triage of {len(entries)}: DIRECT?={c['DIRECT?']}  "
      f"ADJACENT={c['ADJACENT']}  CONTEXT={c['CONTEXT']}", file=sys.stderr)

# emit shortlist for full-read + a machine-readable map
short = [e for e in entries if e["triage"] == "DIRECT?"]
print("\n=== SHORTLIST: read these full threads before counting any 'direct' ===",
      file=sys.stderr)
for e in short:
    num = re.search(r"#(\d+)", e["slug"]).group(1)
    repo = e["slug"].split("#")[0]
    print(f"{e['slug']}  [{e['axis']}]  {e['url']}", file=sys.stderr)

json.dump([{"slug": e["slug"], "repo": e["slug"].split("#")[0],
            "num": re.search(r"#(\d+)", e["slug"]).group(1),
            "axis": e["axis"], "url": e["url"], "title": e["title"],
            "triage": e["triage"]} for e in entries],
          open("triage_map.json", "w"), indent=0)
print(f"\nwrote triage_map.json ({len(entries)} entries)", file=sys.stderr)