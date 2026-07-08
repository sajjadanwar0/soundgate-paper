# `formal/` — mechanized verification

The gate's four properties, verified over a model in three tiers sharing one
specification, plus a Verus model. Receipts are committed and audited by
`../reproduce.sh`.

## Layout
- `tla/SoundGate.tla` + `SoundGate*.cfg` — the TLA⁺ specification and TLC configs.
- `tla/SoundGate_Proofs.tla` — the TLAPS proof (unbounded induction).
- `tla/tlc_2x2.txt`, `tlc_3x3.txt`, `tlc_4x3.txt` — **committed TLC receipts**.
- `tla/tlapm.txt` — **committed TLAPS receipt**.
- `verus/gate_model.rs` + `verus.txt` — the Verus model and its receipt.

## What each tier establishes
- **Verus** — the four properties over a sequential model mirroring the Rust core.
- **TLA⁺/TLC** — all concurrent interleavings, exhaustively, at increasing bounds:
  2×2 = **729** states, 3×3 = **804,357**, 4×3 = **74,805,201** (all complete searches).
- **TLAPS** — the invariant is *inductive* → holds for unbounded runs and keys
  (**68/68** obligations proved).
- **Loom** (in `../soundgate/tests/loom_gate_test.rs`) — the *deployed* concurrent
  Rust at bounded interleavings.
  The model↔code bridge is the differential + bounded-exhaustive conformance in
  `../soundgate/` — refinement *evidence*, not a mechanized refinement proof.

## Re-run (best-effort; tools optional)
```bash
java -cp /path/to/tla2tools.jar tlc2.TLC -config tla/SoundGate.cfg tla/SoundGate.tla
tlapm tla/SoundGate_Proofs.tla
verus verus/gate_model.rs
```
`../reproduce.sh --formal` wires these up and skips cleanly if a tool is absent.