#![cfg(loom)]

use loom::sync::{Arc, Mutex};
use loom::thread;
use soundgate::{Admission, Effect, Gate};

fn eff(run: &str, key: &str, needs_approval: bool) -> Effect {
    Effect { run_id: run.into(), effect_key: key.into(), needs_approval }
}

fn assert_invariants(g: &Gate) {
    let (released, rejected, pending, cancelled, closed) = g.conformance_snapshot();
    // I1: released and rejected identities are disjoint.
    for id in &released {
        assert!(!rejected.contains(id), "I1: {id:?} both released and rejected");
    }

    for (r, _) in &pending {
        assert!(!cancelled.contains(r), "I3: cancelled run {r} retains a pending id");
        assert!(!closed.contains(r), "I3: closed run {r} retains a pending id");
    }
    for (r, _) in &released {
        assert!(!closed.contains(r), "I3: closed run {r} retains a released id");
    }
}

#[test]
fn submit_decide_cancel_race_preserves_invariants() {
    loom::model(|| {
        let gate = Arc::new(Mutex::new(Gate::new()));

        gate.lock().unwrap().submit(eff("1", "1", /*needs_approval=*/ true));

        let g1 = gate.clone();
        let t1 = thread::spawn(move || {
            g1.lock().unwrap().decide("1", "1", /*approved=*/ true);
        });

        let g2 = gate.clone();

        let t2 = thread::spawn(move || {
            let mut g = g2.lock().unwrap();
            g.cancel("1");
            g.submit(eff("1", "1", false));
        });

        t1.join().unwrap();
        t2.join().unwrap();
        assert_invariants(&gate.lock().unwrap());
    });
}

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

        assert!(
            v1 == Admission::RefusedDuplicate || v2 == Admission::RefusedDuplicate,
            "expected one RefusedDuplicate, got {v1:?} / {v2:?}",
        );
        assert_invariants(&gate.lock().unwrap());
    });
}

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