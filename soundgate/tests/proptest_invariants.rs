//! Full proptest-based randomized invariant suite.
//!
//! This is the heavyweight companion to the dependency-free
//! `randomized_invariants_hold` unit test in lib.rs. It requires the
//! `proptest` dev-dependency and a modern toolchain (proptest 1.x pulls
//! crates needing edition2024 / rustc >= 1.85). It is therefore behind a
//! feature so the default `cargo test` stays dependency-light and builds on
//! older toolchains.
//!
//! Enable and run (one command; the feature activates the optional
//! proptest dependency automatically):
//!   cargo test --features proptest-tests
//!
//! proptest drives thousands of randomized op sequences and, on failure,
//! SHRINKS to a minimal counterexample -- which is exactly how the
//! resubmit-of-held double-release (fixed in lib.rs::submit) was
//! characterized. Keeping this suite lets a maintainer re-run adversarial
//! search after any change to the admission logic.
#![cfg(feature = "proptest-tests")]

use proptest::prelude::*;
use soundgate::{Admission, Effect, Gate};
use std::collections::HashSet;

type Id = (String, String);

#[derive(Clone, Debug)]
enum Op {
    Submit { run: u8, key: u8, approval: bool },
    Decide { run: u8, key: u8, approve: bool },
    Cancel { run: u8 },
    Close { run: u8 },
}

fn op_strategy() -> impl Strategy<Value = Op> {
    // 3 runs x 3 keys keeps collisions frequent (the interesting regime).
    prop_oneof![
        (0u8..3, 0u8..3, any::<bool>()).prop_map(|(run, key, approval)| Op::Submit { run, key, approval }),
        (0u8..3, 0u8..3, any::<bool>()).prop_map(|(run, key, approve)| Op::Decide { run, key, approve }),
        (0u8..3).prop_map(|run| Op::Cancel { run }),
        (0u8..3).prop_map(|run| Op::Close { run }),
    ]
}

fn eff(run: u8, key: u8, approval: bool) -> Effect {
    Effect { run_id: format!("r{run}"), effect_key: format!("k{key}"), needs_approval: approval }
}

proptest! {
    #![proptest_config(ProptestConfig { cases: 4000, max_shrink_iters: 10_000, ..ProptestConfig::default() })]

    #[test]
    fn invariants_hold(ops in prop::collection::vec(op_strategy(), 1..60)) {
        let mut g = Gate::new();
        let mut ever_released: HashSet<Id> = HashSet::new();
        let mut fenced: HashSet<String> = HashSet::new();

        for op in ops {
            match op {
                Op::Submit { run, key, approval } => {
                    let rid = format!("r{run}");
                    let id = (rid.clone(), format!("k{key}"));
                    let v = g.submit(eff(run, key, approval));
                    if v == Admission::Release {
                        // INV-1: fenced runs never release.
                        prop_assert!(!fenced.contains(&rid), "released from fenced run {}", rid);
                        // INV-2: no identity releases twice.
                        prop_assert!(!ever_released.contains(&id), "double release (submit) {:?}", id);
                        ever_released.insert(id);
                    }
                }
                Op::Decide { run, key, approve } => {
                    let rid = format!("r{run}");
                    let id = (rid.clone(), format!("k{key}"));
                    let v = g.decide(&rid, &format!("k{key}"), approve);
                    // INV-4 (TLC-found): a decision on an already-released
                    // identity never records a rejection.
                    if ever_released.contains(&id) {
                        prop_assert!(!matches!(v, Admission::RefusedRejected),
                            "late reject recorded on released {:?}", id);
                    }
                    if v == Admission::Release {
                        prop_assert!(!fenced.contains(&rid), "decide-released fenced run {}", rid);
                        prop_assert!(!ever_released.contains(&id), "double release (decide) {:?}", id);
                        ever_released.insert(id);
                    }
                }
                Op::Cancel { run } => {
                    let rid = format!("r{run}");
                    g.cancel(&rid);
                    fenced.insert(rid);
                }
                Op::Close { run } => {
                    let rid = format!("r{run}");
                    g.close_run(&rid);
                    // INV-3: closed runs retain no per-identity state.
                    prop_assert_eq!(g.state_len_for(&rid), 0, "closed run {} left state", rid);
                    fenced.insert(rid);
                }
            }
        }
    }
}