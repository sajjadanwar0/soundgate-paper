"""E-EXPOSURE analysis: rates + Wilson 95% CIs from runner JSONL output.

Reports, per (model, task) and aggregated per model (overall and per class):
  called_rate           = k_called / n            (consequential emitted)
  exposure_given_called = k_exposed / k_called    (PRIMARY)
with Wilson score intervals (z=1.96). Errors are excluded from denominators
and reported separately -- an API failure is not evidence about plan shapes.

DEDUPLICATION: records are deduplicated by (provider, model, task_id,
run_idx), keeping the FIRST non-error record; later duplicates (e.g. a smoke
run and a battery run appending to the same file, or a re-run overlapping a
resume) are dropped and counted. A key whose only records are errors keeps
one error record for the error report.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    """Return (point, lo, hi). Undefined (n=0) -> (nan, nan, nan)."""
    if n == 0:
        return (math.nan, math.nan, math.nan)
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (p, max(0.0, center - half), min(1.0, center + half))


def fmt(k: int, n: int) -> str:
    p, lo, hi = wilson(k, n)
    if math.isnan(p):
        return "--"
    return f"{p:.2f} [{lo:.2f},{hi:.2f}] ({k}/{n})"


def main() -> None:
    ap = argparse.ArgumentParser(description="Analyze E-EXPOSURE JSONL files")
    ap.add_argument("inputs", nargs="+", help="JSONL file(s) from exposure-run")
    ap.add_argument("--out", default=None, help="also write the markdown table here")
    args = ap.parse_args()

    raw = []
    for path in args.inputs:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    raw.append(json.loads(line))
                except json.JSONDecodeError:
                    pass  # torn final line from a hard kill

    # Deduplicate: first non-error record wins per identity key.
    first_ok: dict[tuple, dict] = {}
    first_err: dict[tuple, dict] = {}
    dropped = 0
    for r in raw:
        key = (r.get("provider"), r.get("model"), r.get("task_id"), r.get("run_idx"))
        if r.get("error"):
            first_err.setdefault(key, r)
            continue
        if key in first_ok:
            dropped += 1
        else:
            first_ok[key] = r
    ok = list(first_ok.values())
    errs = [r for k, r in first_err.items() if k not in first_ok]
    if dropped:
        print(f"DEDUPED: dropped {dropped} duplicate record(s) "
              f"(same provider/model/task/run_idx)\n")

    per_task: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for r in ok:
        per_task[(f'{r["provider"]}:{r["model"]}', r["task_class"], r["task_id"])].append(r)

    lines = ["| model | class | task | n | called_rate | exposure_given_called |",
             "|---|---|---|---|---|---|"]
    agg: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for (model, klass, task), rs in sorted(per_task.items()):
        n = len(rs)
        called = [r for r in rs if r["consequential_called"]]
        exposed = [r for r in called if r["parallel_exposure"]]
        lines.append(f"| {model} | {klass} | {task} | {n} | {fmt(len(called), n)} | "
                     f"{fmt(len(exposed), len(called))} |")
        agg[(model, klass)].append({"n": n, "k1": len(called), "k2": len(exposed)})
        agg[(model, "ALL")].append({"n": n, "k1": len(called), "k2": len(exposed)})

    lines.append("")
    lines.append("| model | scope | n | called_rate | exposure_given_called |")
    lines.append("|---|---|---|---|---|")
    for (model, scope), parts in sorted(agg.items()):
        n = sum(p["n"] for p in parts)
        k1 = sum(p["k1"] for p in parts)
        k2 = sum(p["k2"] for p in parts)
        lines.append(f"| {model} | {scope} | {n} | {fmt(k1, n)} | {fmt(k2, k1)} |")

    if errs:
        lines.append("")
        by = defaultdict(int)
        for r in errs:
            by[(f'{r["provider"]}:{r["model"]}', r["task_id"])] += 1
        lines.append(f"EXCLUDED ERRORS: {len(errs)} run(s): "
                     + ", ".join(f"{m}/{t}x{c}" for (m, t), c in sorted(by.items())))

    table = "\n".join(lines)
    print(table)
    if args.out:
        Path(args.out).write_text(table + "\n")
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()