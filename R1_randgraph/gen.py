#!/usr/bin/env python3
"""R1 -- random-workflow generator for the barrier witness sweep.

Generates seeded random out-tree workflows (in-degree <= 1, rooted at START)
containing exactly one approval gate, k effect nodes, and read nodes. In-degree
is capped at 1 deliberately: multi-parent joins change trigger semantics per
framework and would confound the sweep (a follow-up axis, not this one).

Each spec precomputes the structural relation of every effect node to the gate:
  ancestor    -- effect is on the gate's own path, runs before the pause exists
  descendant  -- effect is downstream of the gate (gated by topology)
  conc_earlier / conc_same / conc_later -- concurrent branch, wave (= depth
                from START) earlier than / equal to / later than the gate's

The sweep's question: which structural classes execute during the pause?
Paper's mechanism (Sec. 3.3) predicts conc_same leaks; descendant holds.
conc_later is the open cell the sweep charts.

Usage: python3 gen.py --n 1000 --seed 7 --out specs.jsonl
"""
import argparse, json, random


def gen_one(rng, gid, n_min=3, n_max=8, k_max=3):
    n = rng.randint(n_min, n_max)
    nodes = [f"n{i}" for i in range(n)]
    parent = {}
    for j, node in enumerate(nodes):
        if j == 0 or rng.random() < 0.30:
            parent[node] = "START"          # extra roots -> parallel branches
        else:
            parent[node] = nodes[rng.randrange(j)]
    # roles: one gate anywhere, 1..k effects among the rest, remainder reads
    gate = rng.choice(nodes)
    rest = [x for x in nodes if x != gate]
    effects = rng.sample(rest, rng.randint(1, min(k_max, len(rest))))
    roles = {x: ("gate" if x == gate else "effect" if x in effects else "read")
             for x in nodes}
    # structure
    depth = {x: (1 if parent[x] == "START" else None) for x in nodes}
    for x in nodes:                          # parents precede children in list
        if depth[x] is None:
            depth[x] = depth[parent[x]] + 1
    def ancestors(x):
        out = set()
        while parent[x] != "START":
            x = parent[x]; out.add(x)
        return out
    children = {}
    for x in nodes:
        children.setdefault(parent[x], []).append(x)
    def descendants(x):
        out, stack = set(), list(children.get(x, []))
        while stack:
            y = stack.pop(); out.add(y); stack.extend(children.get(y, []))
        return out
    anc_g, desc_g, wg = ancestors(gate), descendants(gate), depth[gate]
    relation = {}
    for e in effects:
        if e in anc_g:      relation[e] = "ancestor"
        elif e in desc_g:   relation[e] = "descendant"
        elif depth[e] < wg: relation[e] = "conc_earlier"
        elif depth[e] == wg: relation[e] = "conc_same"
        else:               relation[e] = "conc_later"
    return {"id": gid, "n": n, "parent": parent, "roles": roles,
            "gate": gate, "gate_wave": wg, "depth": depth,
            "effects": effects, "relation": relation}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="specs.jsonl")
    a = ap.parse_args()
    rng = random.Random(a.seed)
    with open(a.out, "w") as f:
        for i in range(a.n):
            f.write(json.dumps(gen_one(rng, i)) + "\n")
    print(f"wrote {a.n} specs to {a.out} (seed={a.seed})")


if __name__ == "__main__":
    main()
