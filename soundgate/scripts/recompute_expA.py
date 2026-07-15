import json, glob, collections
tot, per = collections.Counter(), {}

for f in sorted(glob.glob("results/expA_*.jsonl")):
    c = collections.Counter()
    for line in open(f):
        line = line.strip()
        if not line: continue
        try: r = json.loads(line)
        except json.JSONDecodeError: continue
        if r.get("error"): c["error_rows"] += 1; continue
        c["runs"] += 1
        c["emitted"] += int(bool(r.get("emitted")))
        c["leak_unmed"] += int(r.get("leaked_unmediated") is True)
        c["leak_med"]   += int(r.get("leaked_mediated") is True)
    per[f] = c
    for k, v in c.items(): tot[k] += v

for f, c in per.items():
    print(f"  {f.split('/')[-1]:<40} runs={c['runs']:>4} emit={c['emitted']:>4} "
          f"leak_unmed={c['leak_unmed']:>4} leak_med={c['leak_med']:>3}")
print("-" * 92)
print(f"  {'POOLED':<40} runs={tot['runs']:>4} emit={tot['emitted']:>4} "
      f"leak_unmed={tot['leak_unmed']:>4} leak_med={tot['leak_med']:>3}")
pge = tot['leak_unmed'] / max(tot['emitted'], 1)
print(f"\n  ABSTRACT/§4.2 numbers:  unmediated {tot['leak_unmed']}/{tot['runs']}  ;  "
      f"mediated {tot['leak_med']}/{tot['runs']}  ;  P(leak|emit)={pge:.3f}")