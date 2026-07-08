//! loom_gate_test.rs -- concurrent-Rust model checking of the real Gate (D2).
//!
//! The three verification tiers check a *model*: Verus (sequential), TLC
//! (finite concurrent interleavings of the abstract Next), TLAPS (unbounded
//! induction). The differential harness cross-checks deployed code vs. model
//! over random sequences. What none of them do is model-check the *actual Rust
//! concurrency*. `loom` fills that: it exhaustively explores the legal thread
//! interleavings of a small concurrent program under the C11 memory model and
//! fails if any reachable state violates an assertion -- run here against the
//! deployed `Gate`, not a re-model.
//!
//! The Gate core is plain `&mut self` over std collections with no internal
//! locks, so the only shared-state access is through the mutex the server
//! serializes on; loom explores every ordering of that mutex's acquisition.
//! Ids are numeric strings because `conformance_snapshot()` parses them.
//!
//! BUILD/RUN (default builds are untouched -- loom is cfg-gated):
//!   RUSTFLAGS="--cfg loom" cargo test --release --test loom_gate_test
//!
//! Domains are kept tiny (loom is exponential in schedule points): 1--2 runs,
//! 1 key, 2 threads -- enough to hit the fence and double-release races the
//! TLC 2x2 model covers, now on the real type.

#![cfg(loom)]

use loom::sync::{Arc, Mutex};
use loom::thread;
use soundgate::{Admission, Effect, Gate};

fn eff(run: &str, key: &str, needs_approval: bool) -> Effect {
    Effect { run_id: run.into(), effect_key: key.into(), needs_approval }
}

/// The three-part safety invariant the paper's tiers target, read off the real
/// Gate's observable state. Must hold in EVERY loom interleaving.
fn assert_invariants(g: &Gate) {
    let (released, rejected, pending, cancelled, closed) = g.conformance_snapshot();
    // I1: released and rejected identities are disjoint.
    for id in &released {
        assert!(!rejected.contains(id), "I1: {id:?} both released and rejected");
    }
    // I3 (fence compaction): a cancelled or closed run retains no per-identity
    // state -- the load-bearing conjunct that closes the zombie-after-close race.
    for (r, _) in &pending {
        assert!(!cancelled.contains(r), "I3: cancelled run {r} retains a pending id");
        assert!(!closed.contains(r), "I3: closed run {r} retains a pending id");
    }
    for (r, _) in &released {
        assert!(!closed.contains(r), "I3: closed run {r} retains a released id");
    }
}

/// Race a held effect's approval decision against a cancel of its run. Under
/// every ordering, the structural invariant holds: if approval landed before
/// the cancel the effect may be released (correct); if the cancel landed first
/// the fence refuses it -- but never can the state end inconsistent.
#[test]
fn submit_decide_cancel_race_preserves_invariants() {
    loom::model(|| {
        let gate = Arc::new(Mutex::new(Gate::new()));

        // Pre-hold (r1,k1) so both threads race a real pending entry.
        gate.lock().unwrap().submit(eff("1", "1", /*needs_approval=*/ true));

        let g1 = gate.clone();
        let t1 = thread::spawn(move || {
            // Approver decides the held effect.
            g1.lock().unwrap().decide("1", "1", /*approved=*/ true);
        });

        let g2 = gate.clone();
        let t2 = thread::spawn(move || {
            // Cancel arrives concurrently, then a late zombie resubmission.
            let mut g = g2.lock().unwrap();
            g.cancel("1");
            g.submit(eff("1", "1", false)); // must never slip past the fence
        });

        t1.join().unwrap();
        t2.join().unwrap();
        assert_invariants(&gate.lock().unwrap());
    });
}

/// Two approvers race to decide the SAME held identity. The "no identity
/// released twice" property (the double-release bug the randomized harness
/// first caught) means exactly one decide returns Release; the other must see
/// the identity already released and return RefusedDuplicate -- in every
/// interleaving.
#[test]
fn concurrent_decides_release_at_most_once() {
    loom::model(|| {
        let gate = Arc::new(Mutex::new(Gate::new()));
        gate.lock().unwrap().submit(eff("1", "1", true)); // held

        let g1 = gate.clone();
        let t1 = thread::spawn(move || g1.lock().unwrap().decide("1", "1", true));
        let g2 = gate.clone();
        let t2 = thread::spawn(move || g2.lock().unwrap().decide("1", "1", true));

        let v1 = t1.join().unwrap();
        let v2 = t2.join().unwrap();

        let releases = [&v1, &v2].iter().filter(|v| ***v == Admission::Release).count();
        assert_eq!(releases, 1, "double release: {v1:?} / {v2:?}");
        // The non-releasing decide is refused as a duplicate, never a reject
        // (which would break released/rejected disjointness).
        assert!(
            v1 == Admission::RefusedDuplicate || v2 == Admission::RefusedDuplicate,
            "expected one RefusedDuplicate, got {v1:?} / {v2:?}",
        );
        assert_invariants(&gate.lock().unwrap());
    });
}

/// Cross-run key reuse under concurrency: two runs submit the SAME key at once.
/// Scoping is per (run,key), so both must release independently -- neither run's
/// verdict may collaterally refuse the other's.
#[test]
fn cross_run_key_reuse_is_independent() {
    loom::model(|| {
        let gate = Arc::new(Mutex::new(Gate::new()));

        let g1 = gate.clone();
        let t1 = thread::spawn(move || g1.lock().unwrap().submit(eff("1", "1", false)));
        let g2 = gate.clone();
        let t2 = thread::spawn(move || g2.lock().unwrap().submit(eff("2", "1", false)));

        let v1 = t1.join().unwrap();
        let v2 = t2.join().unwrap();
        assert_eq!(v1, Admission::Release, "run 1 collaterally refused: {v1:?}");
        assert_eq!(v2, Admission::Release, "run 2 collaterally refused: {v2:?}");
        assert_invariants(&gate.lock().unwrap());
    });
}