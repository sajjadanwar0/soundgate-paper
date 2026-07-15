import argparse, json, math
from collections import defaultdict

def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))

    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d

    return (max(0.0, c - h), min(1.0, c + h))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="results_fwa.jsonl")
    a = ap.parse_args()
    buckets = defaultdict(lambda: [0, 0])
    dts = defaultdict(list)
    reexec = defaultdict(int)
    gate_runs = defaultdict(int)
    graphs = paused = 0

    for line in open(a.results):
        r = json.loads(line)
        graphs += 1
        paused += r["paused"]
        gate_runs[r["gate_runs"]] += 1

        for e, d in r["effects"].items():
            buckets[d["relation"]][1] += 1
            buckets[d["relation"]][0] += d["during_pause"]
            if d["dt_vs_gate_ms"] is not None:
                dts[d["relation"]].append(d["dt_vs_gate_ms"])
            reexec[d["executions_total"]] += 1
    print(f"graphs={graphs}  paused_at_gate={paused}")
    print(f"gate node body executions (resume replay check): {dict(gate_runs)}")
    print(f"effect execution counts (dedup check): {dict(sorted(reexec.items()))}")
    print("\n-- B1 scope (pause exists during/after the node's scheduling opportunity) --")
    print(f"{'relation':<14}{'leak / n':>14}   rate   Wilson 95% CI      median dt vs gate")

    for rel in ["conc_same", "conc_later", "descendant"]:
        if rel not in buckets:
            continue
        k, n = buckets[rel]
        lo, hi = wilson(k, n)
        med = (sorted(dts[rel])[len(dts[rel]) // 2] if dts[rel] else float("nan"))
        print(f"{rel:<14}{f'{k}/{n}':>14}   {k/n if n else 0:.3f}  [{lo:.3f}, {hi:.3f}]   {med:+.3f} ms" if dts[rel]
              else f"{rel:<14}{f'{k}/{n}':>14}   {k/n if n else 0:.3f}  [{lo:.3f}, {hi:.3f}]   (never in L1)")
    print("\n-- pre-gate (execute before the gate node is entered; outside B1) --")

    for rel in ["conc_earlier", "ancestor"]:
        if rel not in buckets:
            continue
        k, n = buckets[rel]
        med = sorted(dts[rel])[len(dts[rel]) // 2] if dts[rel] else float("nan")
        neg = all(x < 0 for x in dts[rel]) if dts[rel] else True
        print(f"{rel:<14}{f'{k}/{n}':>14}   executed pre-invoke-return; all dt<0: {neg}; median {med:+.3f} ms")
    print("\nLaTeX rows:")

    for rel in ["conc_same", "conc_later", "descendant", "conc_earlier", "ancestor"]:
        if rel in buckets:
            k, n = buckets[rel]
            lo, hi = wilson(k, n)
            print(f"{rel.replace('_','\\_')} & {k}/{n} & "
                  f"{k/n if n else 0:.2f} & [{lo:.2f}, {hi:.2f}] \\\\")

if __name__ == "__main__":
    main()