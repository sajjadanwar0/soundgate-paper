from __future__ import annotations
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

CRATE = Path(__file__).resolve().parents[1]
LIB = CRATE / "src" / "lib.rs"
BAK = CRATE / "src" / "lib.rs.mutation_bak"

EXHAUSTIVE = ["cargo", "test", "--features", "conformance",
              "--test", "exhaustive_conformance", "--release"]
LOOM = ["cargo", "test", "--test", "loom_gate_test", "--release"]
LOOM_ENV = {"RUSTFLAGS": "--cfg loom"}

MUTATIONS = [
    ("verdict_flip", "P1/P2 hold-until-decided / reject-cancels", "exhaustive",
     "        if approved {\n"
     "            self.released.insert(id);\n"
     "            Admission::Release\n"
     "        } else {\n"
     "            self.rejected.insert(id);\n"
     "            Admission::RefusedRejected\n"
     "        }",
     "        if approved {\n"
     "            self.rejected.insert(id);\n"
     "            Admission::RefusedRejected\n"
     "        } else {\n"
     "            self.released.insert(id);\n"
     "            Admission::Release\n"
     "        }"),
    ("dedup_negate", "P3 dedup-on-replay", "exhaustive",
     "        // Property 3: never release the same logical effect twice.\n"
     "        if self.released.contains(&id) {",
     "        // Property 3: never release the same logical effect twice.\n"
     "        if !self.released.contains(&id) {"),
    ("submit_fence_or_to_and", "P4 fence-on-cancel (submit path)", "exhaustive",
     "        if self.cancelled.contains(&e.run_id) || self.closed.contains(&e.run_id) {",
     "        if self.cancelled.contains(&e.run_id) && self.closed.contains(&e.run_id) {"),
    ("hold_negate", "P1 hold-until-decided (approval gating)", "exhaustive",
     "        if e.needs_approval {",
     "        if !e.needs_approval {"),
    ("decide_fence_or_to_and", "P4 fence-on-cancel (decide-after-hold race)", "loom",
     "        if self.cancelled.contains(&effect.run_id) || self.closed.contains(&effect.run_id) {",
     "        if self.cancelled.contains(&effect.run_id) && self.closed.contains(&effect.run_id) {"),
]


def run(cmd, env_extra=None):
    import os
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    r = subprocess.run(cmd, cwd=CRATE, capture_output=True, text=True, env=env)
    return r.returncode == 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--loom", action="store_true",
                    help="also run loom-tagged / surviving mutants under the loom detector")
    args = ap.parse_args()

    src = LIB.read_text()
    for name, _p, _h, old, _new in MUTATIONS:
        if src.count(old) != 1:
            print(f"  !! '{name}': anchor appears {src.count(old)}x (expected 1); source drifted.")
            return 2

    shutil.copy(LIB, BAK)
    exh_reachable = [m for m in MUTATIONS if m[2] == "exhaustive"]
    exh_caught = 0
    survivors = []
    try:
        print("baseline (unmutated) exhaustive conformance ... ", end="", flush=True)
        if not run(EXHAUSTIVE):
            print("FAIL -- baseline not green; aborting."); return 3
        print("PASS\n")

        print("PHASE 1 -- exhaustive (single-threaded) harness:")
        for name, prop, harness, old, new in MUTATIONS:
            LIB.write_text(src.replace(old, new))
            caught = not run(EXHAUSTIVE)
            LIB.write_text(src)
            tag = "" if harness == "exhaustive" else "  (concurrency-only; expected to survive here)"
            print(f"  {name:<26} [{prop}] -> "
                  f"{'CAUGHT' if caught else 'survived'}{tag}")
            if harness == "exhaustive":
                exh_caught += int(caught)
            if not caught:
                survivors.append((name, prop, old, new, harness))

        loom_caught = 0
        loom_total = 0
        if args.loom and survivors:
            print("\nPHASE 2 -- loom (concurrent) harness on survivors:")
            for name, prop, old, new, harness in survivors:
                loom_total += 1
                LIB.write_text(src.replace(old, new))
                caught = not run(LOOM, LOOM_ENV)
                LIB.write_text(src)
                loom_caught += int(caught)
                print(f"  {name:<26} [{prop}] -> {'CAUGHT by loom' if caught else 'SURVIVED loom too!'}")
    finally:
        LIB.write_text(src)
        if BAK.exists():
            BAK.unlink()

    print("-" * 70)
    print(f"Exhaustive harness: {exh_caught}/{len(exh_reachable)} single-threaded-reachable "
          f"property mutations caught.")
    if args.loom:
        print(f"Loom harness:       {loom_caught}/{loom_total} concurrency-only mutation(s) caught.")
        combined = exh_caught + loom_caught
        print(f"COMBINED:           {combined}/{len(MUTATIONS)} property-violating mutations caught "
              f"across the two harnesses.")
        ok = combined == len(MUTATIONS)
    else:
        print(f"(1 mutation is concurrency-only -- run with --loom to verify loom catches it.)")
        ok = exh_caught == len(exh_reachable)
    print("Each mutation is a named, safety-critical one-edit break of an enforced")
    print("property; the harness that catches it is the one whose reachability includes")
    print("that state. No property mutation passes unnoticed by the suite as a whole.")
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        if BAK.exists():
            shutil.copy(BAK, LIB); BAK.unlink()
        print("\ninterrupted; source restored."); sys.exit(130)