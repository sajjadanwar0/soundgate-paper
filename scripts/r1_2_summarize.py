#!/usr/bin/env python3
"""Regenerate the R1-2 extension receipts from the committed per-run records.

The jsonl files under soundgate/results/ are the single source of truth
(probe + capped full runs, appended). This tool recomputes every aggregate
from them and writes canonical receipts to soundgate/evidence/, so the paper,
the receipts, and the raw records can never drift apart. ORIGINAL_ARM_CONS is
the original two-model arm's consequential-batch count (0/71 benign-sibling),
pooled here for the combined null."""
import glob, json, math, pathlib, sys

ORIGINAL_ARM_CONS = 71  # original arm: 431 tool turns, two models, 0/71

def wilson_hi(x, n, z=1.96):
    if n == 0:
        return 0.0
    p = x / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return min(1.0, c + h)

def main() -> int:
    root = pathlib.Path(__file__).resolve().parents[1] / "soundgate"
    res, ev = root / "results", root / "evidence"
    ev.mkdir(exist_ok=True)
    files = sorted(res.glob("taubench_ext_*.jsonl"))
    if len(files) != 4:
        print(f"expected 4 taubench_ext jsonl files, found {len(files)}", file=sys.stderr)
        return 1
    tot_t = tot_c = tot_b = tot_s = 0
    lines = ["# R1-2 extension summary -- recomputed from committed jsonl records"]
    for f in files:
        rows = [json.loads(l) for l in open(f)]
        cons = [r for r in rows if r["is_cons_batch"]]
        ben = sum(1 for r in cons if r["benign_sibling"])
        sib = sum(1 for r in cons if r.get("cons_sibling"))
        tot_t += len(rows); tot_c += len(cons); tot_b += ben; tot_s += sib
        rec = ev / (f.stem + ".txt")
        rec.write_text(
            "# tau-bench ecological exposure receipt (R1-2 extension; probe+full,\n"
            f"# recomputed from {f.name} by r1_2_summarize.py)\n"
            f"# tool-call turns: {len(rows)}\n"
            f"# consequential batches: {len(cons)}\n"
            f"# benign-sibling | consequential: {ben}/{len(cons)}\n"
            f"# cons-sibling (>=2 writes) | consequential: {sib}/{len(cons)}\n")
        lines.append(f"# {f.stem}: turns={len(rows)} cons={len(cons)} "
                     f"benign_sib={ben}/{len(cons)} cons_sib={sib}/{len(cons)}")
    pooled_n = tot_c + ORIGINAL_ARM_CONS
    lines += [
        f"# POOLED extension: turns={tot_t} cons={tot_c} "
        f"benign_sib={tot_b}/{tot_c} cons_sib={tot_s}/{tot_c}",
        f"# POOLED with original arm (0/{ORIGINAL_ARM_CONS}): "
        f"benign_sib={tot_b}/{pooled_n} "
        f"(upper95={wilson_hi(tot_b, pooled_n):.3f})",
    ]
    depth = res / "naturalistic_depth_gpt4o.jsonl"
    if depth.exists():
        rows = [json.loads(l) for l in open(depth)]
        runs = {}
        for r in rows:
            runs.setdefault((r["task_id"], r["run_idx"]), []).append(r)
        dang = sum(1 for v in runs.values() if any(x["dangerous_sibling"] for x in v))
        pre = sorted({r.get("preamble_turns") for r in rows})
        (ev / "naturalistic_depth_gpt4o.txt").write_text(
            "# naturalistic depth arm receipt (recomputed from jsonl)\n"
            f"# runs: {len(runs)}  dangerous (>=2 distinct writes, one turn): {dang}/{len(runs)}\n"
            f"# preamble_turns: {pre}\n")
        lines.append(f"# DEPTH: dangerous={dang}/{len(runs)} preamble_turns={pre}")
    else:
        lines.append("# DEPTH: records missing")
    (ev / "r1_2_summary.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0

if __name__ == "__main__":
    sys.exit(main())
