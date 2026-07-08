# formal/ -- three-tier mechanized verification of the SoundGate admission core

The reviewers' single most-repeated demand was a mechanized correctness
argument for the gate. This directory provides three complementary tiers, each
proving something the others cannot:

| Tier | Tool | Proves | Over |
|------|------|--------|------|
| 1 | **Verus** (`verus/gate_model.rs`) | the four safety properties for the sequential admission logic, tied line-by-line to `soundgate/src/lib.rs` | unbounded runs/keys, SMT-checked |
| 2 | **TLA+ / TLC** (`tla/SoundGate.tla`) | the same invariants hold under **all concurrent interleavings** (submit while cancel/close in flight -- the zombie-after-close race) | a finite model (2 runs x 2 keys), exhaustive |
| 3 | **TLA+ / TLAPS** (`tla/SoundGate_Proofs.tla`) | the invariants are **inductive** and hold for **unbounded** runs/keys | machine-checked proof, all sizes |

Why three: Verus proves the *real Rust logic* is safe when run one op at a
time (which the reference gate guarantees via a mutex). TLC then shows the
protocol stays safe when operations *interleave* -- but only for small finite
domains. TLAPS closes that gap by proving the interleaved invariant inductively
for any number of runs and keys. Together: the implementation is safe, the
concurrency is safe, and the safety does not depend on problem size.

All three target the **same three-conjunct invariant** (disjointness of
released/rejected; pending is undecided; and the fence-compaction invariant
"a closed run retains no per-identity state"), so a reader can check that the
tiers agree by construction.

## What is proved (and what is not)

Proved (safety): no rejected effect releases (P2); no identity releases twice
(P3); a fenced -- cancelled or closed -- run never releases, including a late
"zombie" submission arriving after close (P4); and a gated effect holds rather
than releasing until an explicit approval (P1). The fence-compaction invariant
is the formal answer to the reviewers' zombie-after-close question: closure is
monotone and checked before any per-identity lookup, and a closed run provably
carries no per-identity state, so a stale submission refuses via the fence
regardless of arrival order.

Not proved here (scope, stated honestly): **liveness** (every held effect is
eventually decided or fenced) is not mechanized -- it depends on the approver
and the framework, not the gate. Durability of the WAL and authentication of
decisions are deployment obligations (see the paper's failure-model section),
not part of this core. The Verus tier verifies an abstract model whose
transitions mirror `lib.rs`; it is not a push-button proof of the exact
`HashSet` code (Verus cannot see std-collection internals), and the
transition-to-line mapping in the file header is the audited bridge.

## Tier 1 -- Verus

```bash
cd verus
verus gate_model.rs        # expect: verification successful (0 errors)
```
Tested against Verus 0.2026.05.03 (rustc 1.95). If a lemma fails on a newer
Verus, build it up incrementally (see "If something breaks" below) -- the
proof structure is standard (an inductive invariant plus one preservation
lemma per transition, then the four safety theorems).

## The finding this directory already produced

On its first run, TLC found a **real defect in the gate**: a late
`decide(reject)` on an identity that had already released recorded a
contradictory rejection (the id ended up in both `released` and `rejected`,
violating invariant I1). Verus flagged the same root cause
(`decide_preserves` failed), so two independent tiers agreed. The fix (in
`soundgate/src/lib.rs::decide` and mirrored in both models) checks
`released` before recording a not-pending reject and reports
`RefusedDuplicate`; it is pinned by the `i1_late_reject_of_released_is_duplicate`
unit test and by invariant 4 in both randomized harnesses. This is the second
real bug found by escalating verification tiers (the randomized harness found
the first, a double-release via stale pending state).

## Tier 2 -- TLA+ / TLC (model checking)

With your alias `tlc="java -cp $HOME/tla2tools.jar tlc2.TLC"`:
```bash
cd tla
tlc SoundGate.tla          # reads SoundGate.cfg; expect: no error, N states, 0 violations
```
Enlarge the domains in `SoundGate.cfg` (e.g. `Runs = {r1, r2, r3}`) for a
bigger exhaustive check; the state graph grows quickly but stays finite. A
violation, if any existed, would print the exact interleaving that breaks an
invariant -- that is the point of this tier.

## Tier 3 -- TLA+ / TLAPS (theorem proving)

```bash
cd tla
tlapm SoundGate_Proofs.tla   # expect: all obligations proved
```
(Or open it in the TLA+ Toolbox and run the prover.) This proves
`Spec => []Safety` by the standard inductive argument, so the guarantee is
size-independent.

## If something breaks (version drift)
All three tiers have been executed: Verus (`verus gate_model.rs` -> 11 verified,
0 errors; output: verus/verus.txt), TLC (2x2: 729 distinct states, 0 violations,
tla/tlc_2x2.txt; enlarged 3x3: 804,357 distinct states, 0 violations,
tla/tlc_3x3.txt), and TLAPS (`tlapm SoundGate_Proofs.tla` -> all 68 obligations
proved; output: tla/tlapm.txt). If a re-run on a newer tool version errors: