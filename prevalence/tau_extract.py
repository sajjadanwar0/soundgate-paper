import argparse, json, os, pathlib, subprocess, sys, types
from tau_bench.envs.retail.tasks_test import TASKS_TEST as retail
from tau_bench.envs.airline.tasks_test import TASKS as airline

RETAIL_WRITES = {
    "cancel_pending_order", "exchange_delivered_order_items",
    "modify_pending_order_address", "modify_pending_order_items",
    "modify_pending_order_payment", "modify_user_address",
    "return_delivered_order_items",
}
AIRLINE_WRITES = {
    "book_reservation", "cancel_reservation", "send_certificate",
    "update_reservation_baggages", "update_reservation_flights",
    "update_reservation_passengers",
}
PIN = "59a200c"


def load_tasks(tb: pathlib.Path):
    sys.modules.setdefault(
        "litellm", types.SimpleNamespace(completion=None, provider_list=[]))
    sys.path.insert(0, str(tb))

    return retail, airline

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tau-bench", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    here = pathlib.Path(__file__).resolve().parent
    out = pathlib.Path(a.out) if a.out else here
    candidates = [a.tau_bench, os.environ.get("TAU_BENCH_DIR"),
                  here / "tau-bench", here.parent / "tau-bench",
                  here.parent.parent / "tau-bench"]
    tb = next((pathlib.Path(c) for c in candidates
               if c and (pathlib.Path(c) / "tau_bench").is_dir()), None)

    if tb is None:
        tb = here / "tau-bench"
        subprocess.run(["git", "clone", "--quiet", "--depth=1",
                        "https://github.com/sierra-research/tau-bench.git",
                        str(tb)], check=True)
    print(f"[tau_extract] using tau-bench at: {tb}")

    commit = subprocess.run(["git", "-C", str(tb), "rev-parse", "--short", "HEAD"],
                            capture_output=True, text=True).stdout.strip()

    retail, airline = load_tasks(tb)
    lines = [f"R2 multi-effect prevalence (tau-bench test splits, "
             f"commit {commit}; classification rule verified at {PIN})", ""]
    labels = ["tool,domain,label"]

    for name, tasks, W in [("retail", retail, RETAIL_WRITES),
                           ("airline", airline, AIRLINE_WRITES)]:
        rows, ge2, adj, dist = [], 0, 0, {}

        for i, t in enumerate(tasks):
            names = [ac.name for ac in t.actions]
            writes = [n for n in names if n in W]
            adjacent = any(names[j] in W and names[j + 1] in W
                           for j in range(len(names) - 1))
            dist[len(writes)] = dist.get(len(writes), 0) + 1
            ge2 += len(writes) >= 2
            adj += adjacent
            rows.append({"index": i, "user_id": getattr(t, "user_id", None),
                         "n_gold_actions": len(t.actions),
                         "write_actions": writes, "n_writes": len(writes),
                         "ge2_writes": len(writes) >= 2,
                         "adjacent_write_pair": adjacent})

        with open(out / f"{name}_tasks.jsonl", "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        lines.append(f"{name}: {ge2}/{len(tasks)} gold tasks contain >=2 "
                     f"consequential writes")
        lines.append(f"{name}: {adj}/{len(tasks)} contain an adjacent "
                     f"(consecutive) consequential-write pair")
        lines.append(f"  write-count distribution: {dict(sorted(dist.items()))}")
        lines.append(f"  write tools ({len(W)}): {', '.join(sorted(W))}")
        lines.append("")
        tooldir = tb / "tau_bench" / "envs" / name / "tools"

        for f2 in sorted(tooldir.glob("*.py")):
            if f2.stem != "__init__":
                labels.append(f"{f2.stem},{name},"
                              f"{'write' if f2.stem in W else 'read'}")
    (out / "tool_labels.csv").write_text("\n".join(labels) + "\n")
    (out / "metrics.txt").write_text("\n".join(lines))

    try:
        print("\n".join(lines))
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())


if __name__ == "__main__":
    main()