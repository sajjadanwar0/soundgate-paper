import argparse, json, time

from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command
from langgraph.checkpoint.memory import MemorySaver as Saver

try:
except ImportError:
    from langgraph.checkpoint.memory import InMemorySaver as Saver
from typing_extensions import TypedDict

LOG = []

class S(TypedDict, total=False):
    x: int

def make_node(name, role):
    if role == "gate":
        def gate_node(state: S):
            LOG.append((name, "gate_pre", time.monotonic()))
            LOG.append((name, "gate_post", time.monotonic()))

            return {}

        return gate_node

    kind = "effect" if role == "effect" else "read"

    def node(state: S):
        LOG.append((name, kind, time.monotonic()))
        return {}
    return node

def build(spec):
    g = StateGraph(S)

    for name, role in spec["roles"].items():
        g.add_node(name, make_node(name, role))
    children = set()

    for name, par in spec["parent"].items():
        g.add_edge(START if par == "START" else par, name)
        if par != "START":
            children.add(par)

    for name in spec["roles"]:
        if name not in {p for p in spec["parent"].values()}:
            g.add_edge(name, END)

    return g.compile(checkpointer=Saver())

def paused(result, graph, cfg):

    if isinstance(result, dict) and "__interrupt__" in result:
        return True
    st = graph.get_state(cfg)

    return bool(getattr(st, "next", ()))

def run_one(spec):
    LOG.clear()
    graph = build(spec)
    cfg = {"configurable": {"thread_id": f"g{spec['id']}"}}
    r1 = graph.invoke({"x": 0}, cfg)
    l1 = list(LOG)
    was_paused = paused(r1, graph, cfg)

    if was_paused:
        graph.invoke(Command(resume="approve"), cfg)
    l2 = list(LOG)
    gp = [t for (n, k, t) in l1 if k == "gate_pre"]
    t_gate = gp[0] if gp else None

    rec = {"id": spec["id"], "paused": was_paused,
           "gate_runs": sum(1 for (n, k, _) in l2 if k == "gate_pre"),
           "effects": {}}

    for e in spec["effects"]:
        in_l1 = [t for (n, k, t) in l1 if n == e and k == "effect"]
        in_l2 = [t for (n, k, t) in l2 if n == e and k == "effect"]
        rec["effects"][e] = {
            "relation": spec["relation"][e],
            "during_pause": bool(in_l1),
            "dt_vs_gate_ms": (round((in_l1[0] - t_gate) * 1000, 3)
                              if in_l1 and t_gate is not None else None),
            "executions_total": len(in_l2),
        }

    return rec

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--specs", default="specs.jsonl")
    ap.add_argument("--out", default="results_fwa.jsonl")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    n = 0

    with open(a.specs) as f, open(a.out, "w") as out:
        for line in f:
            spec = json.loads(line)
            out.write(json.dumps(run_one(spec)) + "\n")
            n += 1
            if a.limit and n >= a.limit:
                break
    print(f"ran {n} graphs -> {a.out}")

if __name__ == "__main__":
    main()